#include "models/yolo.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>

#include <opencv2/dnn.hpp>
#include <opencv2/imgproc.hpp>

#include "config.hpp"

namespace lapi {

namespace {

// TensorRT → CUDA → CPU, comme _select_providers() en Python : on tente chaque
// provider et on retombe silencieusement sur le suivant s'il est absent.
Ort::SessionOptions make_session_options() {
    Ort::SessionOptions opts;
    try {
        OrtTensorRTProviderOptions trt{};
        opts.AppendExecutionProvider_TensorRT(trt);
    } catch (const Ort::Exception&) {
        std::cerr << "TensorRT indisponible, fallback CUDA/CPU\n";
    }
    try {
        OrtCUDAProviderOptions cuda{};
        opts.AppendExecutionProvider_CUDA(cuda);
    } catch (const Ort::Exception&) {
        std::cerr << "CUDA indisponible, fallback CPU\n";
    }
    return opts;
}

// Binarise le masque et l'approxime par un polygone convexe (≤ 4 points).
// Retourne false si aucun contour.
bool mask_to_polygon(cv::Mat& crop, const cv::Size& blur_size,
                     std::vector<cv::Point>& poly) {
    cv::blur(crop, crop, blur_size);
    cv::Mat binary;
    cv::compare(crop, 0.5, binary, cv::CMP_GT);  // 0/255
    binary /= 255;                               // 0/1 uint8, comme (crop > 0.5).astype(uint8)
    crop = binary;

    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(binary.clone(), contours, cv::RETR_EXTERNAL,
                     cv::CHAIN_APPROX_SIMPLE);
    if (contours.empty()) return false;

    // Enveloppe convexe sur TOUS les contours (pas seulement le plus grand)
    std::vector<cv::Point> all_points;
    for (const auto& c : contours)
        all_points.insert(all_points.end(), c.begin(), c.end());
    std::vector<cv::Point> hull;
    cv::convexHull(all_points, hull);

    // Augmente epsilon jusqu'à obtenir au plus 4 sommets
    double epsilon = 0.02 * cv::arcLength(hull, true);
    while (true) {
        cv::approxPolyDP(hull, poly, epsilon, true);
        if (poly.size() <= 4) break;
        epsilon *= 1.1;
    }
    return true;
}

// Force le polygone à exactement 4 points (requis par le filtre de Kalman).
Quad force_quadrilateral(const std::vector<cv::Point2f>& poly) {
    Quad q;
    if (poly.size() < 4) {
        const cv::RotatedRect rect = cv::minAreaRect(poly);
        cv::Point2f box[4];
        rect.points(box);
        for (int i = 0; i < 4; ++i) q[i] = box[i];
    } else {
        for (int i = 0; i < 4; ++i) q[i] = poly[i];  // > 4 : on tronque
    }
    return q;
}

// round(x, 3) Python : moitié vers le pair.
float round3(float v) {
    return static_cast<float>(std::nearbyint(static_cast<double>(v) * 1000.0) /
                              1000.0);
}

std::vector<Detection> extract_detections(
    const std::vector<cv::Vec4f>& boxes, const std::vector<float>& scores,
    const std::vector<int>& class_ids, const cv::Mat& mask_preds,
    const float* proto, int num_m, int mask_h, int mask_w,
    int img_h, int img_w) {
    // masques d'instance = sigmoid(coeffs (K×32) × proto (32×(mh·mw)))
    const cv::Mat proto_mat(num_m, mask_h * mask_w, CV_32F,
                            const_cast<float*>(proto));
    cv::Mat masks = mask_preds * proto_mat;
    for (int i = 0; i < masks.rows; ++i) {
        float* row = masks.ptr<float>(i);
        for (int j = 0; j < masks.cols; ++j)
            row[j] = 1.f / (1.f + std::exp(-row[j]));
    }

    // Boîtes exprimées dans le repère (basse résolution) des masques
    const double rx = static_cast<double>(mask_w) / img_w;
    const double ry = static_cast<double>(mask_h) / img_h;
    const cv::Size blur_size(img_w / mask_w, img_h / mask_h);

    std::vector<Detection> detections;
    for (size_t i = 0; i < boxes.size(); ++i) {
        const int x1 = static_cast<int>(std::floor(boxes[i][0]));
        const int y1 = static_cast<int>(std::floor(boxes[i][1]));
        const int x2 = static_cast<int>(std::ceil(boxes[i][2]));
        const int y2 = static_cast<int>(std::ceil(boxes[i][3]));
        // float32 * float32(r), comme boxes_mask en NumPy
        const int mx1 = static_cast<int>(std::floor(boxes[i][0] * static_cast<float>(rx)));
        const int my1 = static_cast<int>(std::floor(boxes[i][1] * static_cast<float>(ry)));
        const int mx2 = static_cast<int>(std::ceil(boxes[i][2] * static_cast<float>(rx)));
        const int my2 = static_cast<int>(std::ceil(boxes[i][3] * static_cast<float>(ry)));

        // Slicing NumPy : bornes clampées aux dimensions du masque
        const int cx1 = std::clamp(mx1, 0, mask_w), cx2 = std::clamp(mx2, 0, mask_w);
        const int cy1 = std::clamp(my1, 0, mask_h), cy2 = std::clamp(my2, 0, mask_h);
        if (cx2 <= cx1 || cy2 <= cy1) continue;

        cv::Mat crop = cv::Mat(mask_h, mask_w, CV_32F, masks.ptr<float>(static_cast<int>(i)))(
            cv::Range(cy1, cy2), cv::Range(cx1, cx2));
        cv::resize(crop, crop, cv::Size(x2 - x1, y2 - y1), 0, 0, cv::INTER_CUBIC);

        std::vector<cv::Point> poly_int;
        if (!mask_to_polygon(crop, blur_size, poly_int)) continue;

        std::vector<cv::Point2f> poly;
        for (const auto& p : poly_int)
            poly.emplace_back(static_cast<float>(p.x + x1),
                              static_cast<float>(p.y + y1));

        Detection det;
        det.klass = config::LABELS[class_ids[i]];
        det.score = round3(scores[i]);
        det.box = cv::Rect(x1, y1, x2 - x1, y2 - y1);
        det.polygon = force_quadrilateral(poly);
        det.mask = crop;  // binaire 0/1, taille de la boîte
        detections.push_back(std::move(det));
    }
    return detections;
}

}  // namespace

YoloModel load_yolo(const std::string& model_path, Ort::Env& env) {
    YoloModel model;
    auto opts = make_session_options();
#ifdef _WIN32
    std::wstring wpath(model_path.begin(), model_path.end());
    model.session = std::make_unique<Ort::Session>(env, wpath.c_str(), opts);
#else
    model.session = std::make_unique<Ort::Session>(env, model_path.c_str(), opts);
#endif

    Ort::AllocatorWithDefaultOptions alloc;
    model.input_name = model.session->GetInputNameAllocated(0, alloc).get();
    auto shape = model.session->GetInputTypeInfo(0).GetTensorTypeAndShapeInfo().GetShape();
    model.input_height = static_cast<int>(shape[2]);
    model.input_width = static_cast<int>(shape[3]);
    return model;
}

std::vector<Ort::Value> run_yolo(YoloModel& model, const cv::Mat& frame) {
    // BGR→RGB, resize (bilinéaire), /255 calculé en double puis float32, NCHW.
    cv::Mat img;
    cv::cvtColor(frame, img, cv::COLOR_BGR2RGB);
    cv::resize(img, img, cv::Size(model.input_width, model.input_height));
    cv::Mat f;
    img.convertTo(f, CV_32F, 1.0 / 255.0);

    const int h = model.input_height, w = model.input_width;
    std::vector<float> tensor(static_cast<size_t>(3) * h * w);
    std::vector<cv::Mat> channels(3);
    for (int c = 0; c < 3; ++c)
        channels[c] = cv::Mat(h, w, CV_32F, tensor.data() + static_cast<size_t>(c) * h * w);
    cv::split(f, channels);

    const std::array<int64_t, 4> dims = {1, 3, h, w};
    Ort::MemoryInfo mem = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    Ort::Value input = Ort::Value::CreateTensor<float>(
        mem, tensor.data(), tensor.size(), dims.data(), dims.size());

    const char* in_names[] = {model.input_name.c_str()};
    const Ort::AllocatorWithDefaultOptions alloc;
    std::vector<std::string> out_name_strs;
    std::vector<const char*> out_names;
    const size_t n_out = model.session->GetOutputCount();
    for (size_t i = 0; i < n_out; ++i)
        out_name_strs.push_back(model.session->GetOutputNameAllocated(i, alloc).get());
    for (const auto& s : out_name_strs) out_names.push_back(s.c_str());

    return model.session->Run(Ort::RunOptions{nullptr}, in_names, &input, 1,
                              out_names.data(), out_names.size());
}

std::vector<Detection> parse_yolo(const YoloModel& model,
                                  const std::vector<Ort::Value>& outputs,
                                  int img_h, int img_w) {
    // box_output : (1, 4 + nc + 32, N) ; mask_output : (1, 32, mh, mw)
    const auto box_shape = outputs[0].GetTensorTypeAndShapeInfo().GetShape();
    const auto mask_shape = outputs[1].GetTensorTypeAndShapeInfo().GetShape();
    const float* box_data = outputs[0].GetTensorData<float>();
    const float* mask_data = outputs[1].GetTensorData<float>();

    const int n_attrs = static_cast<int>(box_shape[1]);
    const int n_preds = static_cast<int>(box_shape[2]);
    const int num_classes = n_attrs - model.num_mask_coeffs - 4;
    auto attr = [&](int a, int j) { return box_data[static_cast<size_t>(a) * n_preds + j]; };

    // Filtrage par confiance
    std::vector<int> kept;
    std::vector<float> scores;
    std::vector<int> class_ids;
    for (int j = 0; j < n_preds; ++j) {
        float best = attr(4, j);
        int best_c = 0;
        for (int c = 1; c < num_classes; ++c)
            if (attr(4 + c, j) > best) { best = attr(4 + c, j); best_c = c; }
        if (best > config::CONF) {
            kept.push_back(j);
            scores.push_back(best);
            class_ids.push_back(best_c);
        }
    }
    if (kept.empty()) return {};

    // (cx, cy, w, h) réseau → (x1, y1, x2, y2) image, clampé
    const float sx = static_cast<float>(static_cast<double>(img_w) / model.input_width);
    const float sy = static_cast<float>(static_cast<double>(img_h) / model.input_height);
    std::vector<cv::Vec4f> boxes;
    for (int j : kept) {
        const float cx = attr(0, j), cy = attr(1, j);
        const float w = attr(2, j), h = attr(3, j);
        boxes.emplace_back(
            std::clamp((cx - w / 2) * sx, 0.f, static_cast<float>(img_w)),
            std::clamp((cy - h / 2) * sy, 0.f, static_cast<float>(img_h)),
            std::clamp((cx + w / 2) * sx, 0.f, static_cast<float>(img_w)),
            std::clamp((cy + h / 2) * sy, 0.f, static_cast<float>(img_h)));
    }

    // NMS — comme le Python, les boîtes (x1,y1,x2,y2) sont passées telles
    // quelles à NMSBoxes qui les interprète (x,y,w,h). Quirk préservé : même
    // entrée, mêmes indices en sortie.
    std::vector<cv::Rect2d> nms_boxes;
    for (const auto& b : boxes)
        nms_boxes.emplace_back(b[0], b[1], b[2], b[3]);
    std::vector<int> indices;
    cv::dnn::NMSBoxes(nms_boxes, scores, config::CONF, config::IOU, indices);
    if (indices.empty()) return {};

    std::vector<cv::Vec4f> sel_boxes;
    std::vector<float> sel_scores;
    std::vector<int> sel_ids;
    cv::Mat sel_coeffs(static_cast<int>(indices.size()), model.num_mask_coeffs, CV_32F);
    for (size_t k = 0; k < indices.size(); ++k) {
        const int i = indices[k];
        sel_boxes.push_back(boxes[i]);
        sel_scores.push_back(scores[i]);
        sel_ids.push_back(class_ids[i]);
        for (int m = 0; m < model.num_mask_coeffs; ++m)
            sel_coeffs.at<float>(static_cast<int>(k), m) =
                attr(4 + num_classes + m, kept[i]);
    }

    return extract_detections(sel_boxes, sel_scores, sel_ids, sel_coeffs,
                              mask_data, static_cast<int>(mask_shape[1]),
                              static_cast<int>(mask_shape[2]),
                              static_cast<int>(mask_shape[3]), img_h, img_w);
}

}  // namespace lapi
