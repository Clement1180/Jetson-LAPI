// Miroir de src/models/yolo.py — session ONNX YOLO-seg et parsing des sorties.
#pragma once

#include <memory>
#include <string>
#include <vector>

#include <onnxruntime_cxx_api.h>
#include <opencv2/core.hpp>

#include "detection.hpp"

namespace lapi {

struct YoloModel {
    std::unique_ptr<Ort::Session> session;
    std::string input_name;
    int input_height = 0;
    int input_width = 0;
    int num_mask_coeffs = 32;
};

// Crée la session avec TensorRT → CUDA → CPU selon disponibilité (cf. config.py).
YoloModel load_yolo(const std::string& model_path, Ort::Env& env);

// Letterbox + normalisation + inférence. Retourne les tenseurs de sortie bruts.
std::vector<Ort::Value> run_yolo(YoloModel& model, const cv::Mat& frame);

// NMS + décodage des proto-masques → détections aux coordonnées image (h × w).
std::vector<Detection> parse_yolo(const YoloModel& model,
                                  const std::vector<Ort::Value>& outputs,
                                  int frame_height, int frame_width);

}  // namespace lapi
