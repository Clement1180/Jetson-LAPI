#include "inference.hpp"
#include <NvInfer.h>
#include <cuda_runtime.h>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <numeric>

namespace lapi {

class Logger : public nvinfer1::ILogger {
public:
    void log(Severity severity, const char* msg) noexcept override {
        if (severity <= Severity::kWARNING)
            std::cerr << "[TRT] " << msg << std::endl;
    }
};

static Logger g_logger;

TRTEngine::~TRTEngine() {
    if (buffers_[0]) cudaFree(buffers_[0]);
    if (buffers_[1]) cudaFree(buffers_[1]);
    if (stream_) cudaStreamDestroy(stream_);
    delete context_;
    delete engine_;
    delete runtime_;
}

bool TRTEngine::load(const std::string& engine_path) {
    std::ifstream file(engine_path, std::ios::binary);
    if (!file.good()) {
        std::cerr << "[TRT] Cannot open: " << engine_path << std::endl;
        return false;
    }

    file.seekg(0, std::ios::end);
    size_t size = file.tellg();
    file.seekg(0, std::ios::beg);

    std::vector<char> data(size);
    file.read(data.data(), size);

    runtime_ = nvinfer1::createInferRuntime(g_logger);
    engine_ = runtime_->deserializeCudaEngine(data.data(), size);
    if (!engine_) {
        std::cerr << "[TRT] Failed to deserialize engine" << std::endl;
        return false;
    }

    context_ = engine_->createExecutionContext();

    // Get input/output dimensions
    auto input_name = engine_->getIOTensorName(0);
    auto output_name = engine_->getIOTensorName(1);
    auto in_dims = engine_->getTensorShape(input_name);
    auto out_dims = engine_->getTensorShape(output_name);

    input_size_ = 1;
    for (int i = 0; i < in_dims.nbDims; ++i) {
        input_dims_.push_back(in_dims.d[i]);
        input_size_ *= in_dims.d[i];
    }

    output_size_ = 1;
    for (int i = 0; i < out_dims.nbDims; ++i) {
        output_dims_.push_back(out_dims.d[i]);
        output_size_ *= out_dims.d[i];
    }

    cudaMalloc(&buffers_[0], input_size_ * sizeof(float));
    cudaMalloc(&buffers_[1], output_size_ * sizeof(float));
    cudaStreamCreate(&stream_);

    context_->setTensorAddress(input_name, buffers_[0]);
    context_->setTensorAddress(output_name, buffers_[1]);

    return true;
}

bool TRTEngine::infer(const float* input, float* output) {
    cudaMemcpyAsync(buffers_[0], input, input_size_ * sizeof(float),
                    cudaMemcpyHostToDevice, stream_);

    if (!context_->enqueueV3(stream_)) {
        std::cerr << "[TRT] Inference failed" << std::endl;
        return false;
    }

    cudaMemcpyAsync(output, buffers_[1], output_size_ * sizeof(float),
                    cudaMemcpyDeviceToHost, stream_);
    cudaStreamSynchronize(stream_);
    return true;
}

// ============================================================
// YOLO Car Detector
// ============================================================

bool YOLOCarDetector::init(const std::string& engine_path) {
    if (!engine_.load(engine_path)) return false;
    input_buf_.resize(engine_.input_size());
    output_buf_.resize(engine_.output_size());
    return true;
}

static void preprocess_640(const uint8_t* bgr, int w, int h, float* out) {
    // Resize to 640x640, BGR→RGB, normalize [0,1], CHW layout
    // Simple bilinear resize
    const int T = 640;
    float sx = static_cast<float>(w) / T;
    float sy = static_cast<float>(h) / T;

    for (int y = 0; y < T; ++y) {
        for (int x = 0; x < T; ++x) {
            int src_x = std::min(static_cast<int>(x * sx), w - 1);
            int src_y = std::min(static_cast<int>(y * sy), h - 1);
            int src_idx = (src_y * w + src_x) * 3;

            // BGR → RGB + normalize
            float r = bgr[src_idx + 2] / 255.0f;
            float g = bgr[src_idx + 1] / 255.0f;
            float b = bgr[src_idx + 0] / 255.0f;

            out[0 * T * T + y * T + x] = r;
            out[1 * T * T + y * T + x] = g;
            out[2 * T * T + y * T + x] = b;
        }
    }
}

static void nms(std::vector<Detection>& dets, float iou_thresh) {
    std::sort(dets.begin(), dets.end(),
              [](const Detection& a, const Detection& b) {
                  return a.confidence > b.confidence;
              });

    std::vector<bool> suppressed(dets.size(), false);
    for (size_t i = 0; i < dets.size(); ++i) {
        if (suppressed[i]) continue;
        for (size_t j = i + 1; j < dets.size(); ++j) {
            if (suppressed[j]) continue;
            if (compute_iou(dets[i].box, dets[j].box) > iou_thresh) {
                suppressed[j] = true;
            }
        }
    }

    std::vector<Detection> result;
    for (size_t i = 0; i < dets.size(); ++i) {
        if (!suppressed[i]) result.push_back(dets[i]);
    }
    dets = std::move(result);
}

std::vector<Detection> YOLOCarDetector::detect(
    const uint8_t* bgr_data, int width, int height,
    float conf_thresh, float iou_thresh) {

    preprocess_640(bgr_data, width, height, input_buf_.data());
    engine_.infer(input_buf_.data(), output_buf_.data());

    // YOLOv8 output: [1, 84, 8400] transposed to [8400, 84]
    const int num_preds = 8400;
    const int num_classes = 80;
    const float* raw = output_buf_.data();

    // Vehicle class indices in COCO: bus=5, car=2, motorcycle=3, truck=7
    const int vehicle_classes[] = {2, 3, 5, 7};

    std::vector<Detection> results;
    float sx = static_cast<float>(width) / 640.0f;
    float sy = static_cast<float>(height) / 640.0f;

    for (int i = 0; i < num_preds; ++i) {
        // Output layout: [84, 8400] → index as raw[attr * 8400 + i]
        float best_score = 0.0f;
        for (int cls : vehicle_classes) {
            float score = raw[(4 + cls) * num_preds + i];
            best_score = std::max(best_score, score);
        }

        if (best_score < conf_thresh) continue;

        float cx = raw[0 * num_preds + i];
        float cy = raw[1 * num_preds + i];
        float w = raw[2 * num_preds + i];
        float h = raw[3 * num_preds + i];

        Detection det;
        det.box.x1 = (cx - w * 0.5f) * sx;
        det.box.y1 = (cy - h * 0.5f) * sy;
        det.box.x2 = (cx + w * 0.5f) * sx;
        det.box.y2 = (cy + h * 0.5f) * sy;
        det.confidence = best_score;
        det.class_id = 0;
        results.push_back(det);
    }

    nms(results, iou_thresh);
    return results;
}

// ============================================================
// YOLO Plate Detector (Pose model - 4 keypoints)
// ============================================================

bool YOLOPlateDetector::init(const std::string& engine_path) {
    if (!engine_.load(engine_path)) return false;
    input_buf_.resize(engine_.input_size());
    output_buf_.resize(engine_.output_size());
    return true;
}

bool YOLOPlateDetector::detect(
    const uint8_t* bgr_data, int width, int height,
    PlateDetection& out, float conf_thresh) {

    preprocess_640(bgr_data, width, height, input_buf_.data());
    engine_.infer(input_buf_.data(), output_buf_.data());

    // YOLOv8-pose output: [1, 18, 8400] (4 box + 1 conf + 4*3 keypoints)
    // Keypoints: x, y, confidence for each of 4 points
    const int num_preds = 8400;
    const float* raw = output_buf_.data();

    float sx = static_cast<float>(width) / 640.0f;
    float sy = static_cast<float>(height) / 640.0f;

    // Find best detection by average keypoint confidence
    int best_idx = -1;
    float best_conf = 0.0f;

    for (int i = 0; i < num_preds; ++i) {
        // Keypoint confidences at indices 8, 11, 14, 17 (offset by *num_preds)
        float avg_conf = 0.0f;
        for (int k = 0; k < 4; ++k) {
            avg_conf += raw[(6 + k * 3 + 2) * num_preds + i];
        }
        avg_conf *= 0.25f;

        if (avg_conf > best_conf) {
            best_conf = avg_conf;
            best_idx = i;
        }
    }

    if (best_idx < 0 || best_conf < conf_thresh) return false;

    // Extract keypoints
    constexpr float MIN_PLATE_W = 48.0f;
    constexpr float MIN_PLATE_H = 24.0f;

    for (int k = 0; k < 4; ++k) {
        out.keypoints[k].x = raw[(6 + k * 3) * num_preds + best_idx] * sx;
        out.keypoints[k].y = raw[(6 + k * 3 + 1) * num_preds + best_idx] * sy;
    }
    out.confidence = best_conf;

    BBox plate_box = out.to_box();
    if (plate_box.w() < MIN_PLATE_W || plate_box.h() < MIN_PLATE_H)
        return false;

    return true;
}

// ============================================================
// PP-OCRv4 Recognizer
// ============================================================

bool PPOCRRecognizer::init(const std::string& engine_path, const std::string& dict_path) {
    if (!engine_.load(engine_path)) return false;
    input_buf_.resize(engine_.input_size());
    output_buf_.resize(engine_.output_size());

    chars_.push_back("blank");
    std::ifstream f(dict_path);
    std::string line;
    while (std::getline(f, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        chars_.push_back(line);
    }
    chars_.push_back(" ");
    return true;
}

std::string PPOCRRecognizer::recognize(const uint8_t* bgr_data, int width, int height) {
    // PP-OCRv4: input [1, 3, 48, 320], normalize to [-1, 1]
    constexpr int IMG_H = 48;
    constexpr int IMG_W = 320;

    float ratio = static_cast<float>(width) / height;
    int resized_w = std::min(static_cast<int>(IMG_H * ratio), IMG_W);

    std::fill(input_buf_.begin(), input_buf_.end(), 0.0f);

    float sx = static_cast<float>(width) / resized_w;
    float sy = static_cast<float>(height) / IMG_H;

    for (int y = 0; y < IMG_H; ++y) {
        for (int x = 0; x < resized_w; ++x) {
            int src_x = std::min(static_cast<int>(x * sx), width - 1);
            int src_y = std::min(static_cast<int>(y * sy), height - 1);
            int src_idx = (src_y * width + src_x) * 3;

            // BGR → RGB, normalize to [-1, 1]
            float r = (bgr_data[src_idx + 2] / 255.0f - 0.5f) * 2.0f;
            float g = (bgr_data[src_idx + 1] / 255.0f - 0.5f) * 2.0f;
            float b = (bgr_data[src_idx + 0] / 255.0f - 0.5f) * 2.0f;

            input_buf_[0 * IMG_H * IMG_W + y * IMG_W + x] = r;
            input_buf_[1 * IMG_H * IMG_W + y * IMG_W + x] = g;
            input_buf_[2 * IMG_H * IMG_W + y * IMG_W + x] = b;
        }
    }

    engine_.infer(input_buf_.data(), output_buf_.data());

    // CTC decode: output shape [1, W/4, num_chars]
    int seq_len = IMG_W / 4;  // 80
    int num_chars = static_cast<int>(chars_.size());

    std::string result;
    int prev_idx = 0;

    for (int t = 0; t < seq_len; ++t) {
        int best_idx = 0;
        float best_val = output_buf_[t * num_chars];
        for (int c = 1; c < num_chars; ++c) {
            float val = output_buf_[t * num_chars + c];
            if (val > best_val) {
                best_val = val;
                best_idx = c;
            }
        }

        if (best_idx != 0 && best_idx != prev_idx) {
            if (best_idx < static_cast<int>(chars_.size()))
                result += chars_[best_idx];
        }
        prev_idx = best_idx;
    }

    return result;
}

}  // namespace lapi
