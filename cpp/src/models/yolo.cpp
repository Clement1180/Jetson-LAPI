#include "models/yolo.hpp"

#include <iostream>
#include <stdexcept>

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

std::vector<Ort::Value> run_yolo(YoloModel& /*model*/, const cv::Mat& /*frame*/) {
    // TODO étape 2 : letterbox + BGR→RGB + normalisation /255 + NCHW float32,
    // identique au preprocess Python (source n°1 d'écarts, cf. ROADMAP_CPP).
    throw std::logic_error("run_yolo : non porté (étape 2)");
}

std::vector<Detection> parse_yolo(const YoloModel& /*model*/,
                                  const std::vector<Ort::Value>& /*outputs*/,
                                  int /*frame_height*/, int /*frame_width*/) {
    // TODO étape 2 : filtre CONF, NMS IoU, décodage proto-masques (NumPy → cv::Mat),
    // polygone 4 points, remap letterbox → coordonnées image.
    throw std::logic_error("parse_yolo : non porté (étape 2)");
}

}  // namespace lapi
