// Configuration centrale — miroir de src/config.py.
#pragma once

#include <array>
#include <string>

#include <opencv2/core.hpp>

namespace lapi::config {

// Chemins par défaut, relatifs à la racine du dépôt (surchargeables en CLI).
inline const std::string YOLO_MODEL  = "src/models_weight/best.onnx";
inline const std::string OCR_MODEL   = "src/models_weight/ocr_model.onnx";
inline const std::string CHARS_PATH  = "src/models_weight/en_dict.txt";
inline const std::string INPUT_VIDEO = "exemples/inputs/rush_2.avi";
inline const std::string OUTPUT_VIDEO = "exemples/outputs/rush_2.avi";

// ── Inférence ─────────────────────────────────────────────────────────────
inline constexpr float CONF = 0.5f;  // seuil de confiance YOLO
inline constexpr float IOU  = 0.5f;  // seuil IoU pour la NMS

inline const std::array<std::string, 2> LABELS = {"day", "night"};
// BGR, comme en Python. NB : viz utilise toujours COLORS[0] (anomalie préservée).
inline const std::array<cv::Scalar, 2> COLORS = {cv::Scalar(0, 255, 0),
                                                 cv::Scalar(0, 0, 255)};

// L'OCR n'est exécuté qu'une frame sur N ; entre deux exécutions, le filtre de
// Kalman suit la plaque et le dernier texte reconnu est conservé.
inline constexpr int OCR_FRAME_INTERVAL = 3;

}  // namespace lapi::config
