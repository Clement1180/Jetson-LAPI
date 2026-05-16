#pragma once

#include "types.hpp"
#include <NvInfer.h>
#include <cuda_runtime.h>
#include <memory>
#include <string>
#include <vector>

namespace lapi {

class TRTEngine {
public:
    TRTEngine() = default;
    ~TRTEngine();

    bool load(const std::string& engine_path);
    bool infer(const float* input, float* output);

    int input_size() const { return input_size_; }
    int output_size() const { return output_size_; }
    std::vector<int> input_dims() const { return input_dims_; }
    std::vector<int> output_dims() const { return output_dims_; }

private:
    nvinfer1::IRuntime* runtime_ = nullptr;
    nvinfer1::ICudaEngine* engine_ = nullptr;
    nvinfer1::IExecutionContext* context_ = nullptr;
    void* buffers_[2] = {nullptr, nullptr};
    int input_size_ = 0;
    int output_size_ = 0;
    std::vector<int> input_dims_;
    std::vector<int> output_dims_;
    cudaStream_t stream_ = nullptr;
};

class YOLOCarDetector {
public:
    bool init(const std::string& engine_path);
    std::vector<Detection> detect(const uint8_t* bgr_data, int width, int height,
                                  float conf_thresh = 0.5f, float iou_thresh = 0.45f);

private:
    TRTEngine engine_;
    std::vector<float> input_buf_;
    std::vector<float> output_buf_;
};

class YOLOPlateDetector {
public:
    bool init(const std::string& engine_path);
    bool detect(const uint8_t* bgr_data, int width, int height,
                PlateDetection& out, float conf_thresh = 0.4f);

private:
    TRTEngine engine_;
    std::vector<float> input_buf_;
    std::vector<float> output_buf_;
};

class PPOCRRecognizer {
public:
    bool init(const std::string& engine_path, const std::string& dict_path);
    std::string recognize(const uint8_t* bgr_data, int width, int height);

private:
    TRTEngine engine_;
    std::vector<float> input_buf_;
    std::vector<float> output_buf_;
    std::vector<std::string> chars_;
};

}  // namespace lapi
