#include "models/ocr.hpp"

#include <algorithm>
#include <array>
#include <fstream>
#include <iostream>
#include <stdexcept>

#include <opencv2/imgproc.hpp>

namespace lapi {

namespace {

std::string strip(const std::string& s) {
    const auto first = s.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return "";
    const auto last = s.find_last_not_of(" \t\r\n");
    return s.substr(first, last - first + 1);
}

// Noyau de netteté appliqué à l'une des variantes de prétraitement
const cv::Mat kSharpenKernel =
    (cv::Mat_<float>(3, 3) << -1, -1, -1, -1, 9, -1, -1, -1, -1);

// Égalisation adaptative du contraste (CLAHE) sur le canal de luminance.
cv::Mat apply_clahe(const cv::Mat& img) {
    cv::Mat lab;
    cv::cvtColor(img, lab, cv::COLOR_BGR2Lab);
    std::vector<cv::Mat> ch;
    cv::split(lab, ch);
    cv::createCLAHE(3.0, cv::Size(8, 8))->apply(ch[0], ch[0]);
    cv::merge(ch, lab);
    cv::Mat out;
    cv::cvtColor(lab, out, cv::COLOR_Lab2BGR);
    return out;
}

// CLAHE + RGB + resize + normalisation [-1, 1], complété à droite par des zéros.
std::vector<float> to_input_tensor(const cv::Mat& img, int resized_w) {
    cv::Mat rgb;
    cv::cvtColor(apply_clahe(img), rgb, cv::COLOR_BGR2RGB);
    cv::resize(rgb, rgb, cv::Size(resized_w, OCR_INPUT_HEIGHT));
    cv::Mat f;
    rgb.convertTo(f, CV_32F, 1.0 / 255.0);
    f = (f - cv::Scalar::all(0.5)) / 0.5;  // Scalar::all : les 3 canaux

    std::vector<float> tensor(
        static_cast<size_t>(OCR_INPUT_CHANNELS) * OCR_INPUT_HEIGHT * OCR_INPUT_WIDTH,
        0.f);
    for (int y = 0; y < OCR_INPUT_HEIGHT; ++y) {
        const cv::Vec3f* row = f.ptr<cv::Vec3f>(y);
        for (int x = 0; x < resized_w; ++x)
            for (int c = 0; c < OCR_INPUT_CHANNELS; ++c)
                tensor[(static_cast<size_t>(c) * OCR_INPUT_HEIGHT + y) *
                           OCR_INPUT_WIDTH + x] = row[x][c];
    }
    return tensor;
}

}  // namespace

std::vector<std::string> load_chars(const std::string& chars_path) {
    std::ifstream f(chars_path);
    if (!f) throw std::runtime_error("Dictionnaire OCR introuvable : " + chars_path);
    std::vector<std::string> chars = {""};  // index 0 = blank CTC
    std::string line;
    while (std::getline(f, line)) {
        const std::string c = strip(line);
        if (!c.empty()) chars.push_back(c);
    }
    return chars;
}

OcrModel load_ocr(const std::string& model_path, const std::string& chars_path,
                  Ort::Env& env) {
    OcrModel model;
    Ort::SessionOptions opts;
#ifdef _WIN32
    std::wstring wpath(model_path.begin(), model_path.end());
    model.session = std::make_unique<Ort::Session>(env, wpath.c_str(), opts);
#else
    model.session = std::make_unique<Ort::Session>(env, model_path.c_str(), opts);
#endif
    Ort::AllocatorWithDefaultOptions alloc;
    model.input_name = model.session->GetInputNameAllocated(0, alloc).get();
    model.chars = load_chars(chars_path);
    std::cout << "OCR  : " << model.chars.size() << " chars\n";
    return model;
}

std::string decode_ocr(const float* preds, int seq_len, int num_classes,
                       const std::vector<std::string>& chars) {
    std::string text;
    int prev = -1;
    for (int i = 0; i < seq_len; ++i) {
        const float* row = preds + static_cast<size_t>(i) * num_classes;
        int c = 0;
        for (int j = 1; j < num_classes; ++j)
            if (row[j] > row[c]) c = j;
        if (c != 0 && c != prev && c < static_cast<int>(chars.size()))
            text += chars[c];
        prev = c;
    }
    return text;
}

std::string run_ocr(OcrModel& model, const cv::Mat& plate) {
    if (plate.empty()) return "";

    const int h = plate.rows, w = plate.cols;
    const int resized_w = std::min(
        static_cast<int>(OCR_INPUT_HEIGHT * w / static_cast<double>(h)),
        OCR_INPUT_WIDTH);

    // Trois variantes (originale, inversée, accentuée), résultat le plus long
    // conservé — en cas d'égalité, la première, comme max(key=len) Python.
    std::array<cv::Mat, 3> variants;
    variants[0] = plate;
    cv::bitwise_not(plate, variants[1]);
    cv::filter2D(plate, variants[2], -1, kSharpenKernel);

    const std::array<int64_t, 4> dims = {1, OCR_INPUT_CHANNELS,
                                         OCR_INPUT_HEIGHT, OCR_INPUT_WIDTH};
    Ort::MemoryInfo mem = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    const char* in_names[] = {model.input_name.c_str()};
    const Ort::AllocatorWithDefaultOptions alloc;
    const std::string out_name = model.session->GetOutputNameAllocated(0, alloc).get();
    const char* out_names[] = {out_name.c_str()};

    std::string best;
    for (const auto& variant : variants) {
        std::vector<float> tensor = to_input_tensor(variant, resized_w);
        Ort::Value input = Ort::Value::CreateTensor<float>(
            mem, tensor.data(), tensor.size(), dims.data(), dims.size());
        auto outputs = model.session->Run(Ort::RunOptions{nullptr}, in_names,
                                          &input, 1, out_names, 1);
        const auto shape = outputs[0].GetTensorTypeAndShapeInfo().GetShape();
        const std::string text =
            decode_ocr(outputs[0].GetTensorData<float>(),
                       static_cast<int>(shape[1]), static_cast<int>(shape[2]),
                       model.chars);
        if (text.size() > best.size()) best = text;
    }
    return best;
}

}  // namespace lapi
