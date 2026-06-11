// Miroir de src/pipeline/core.py — état persistant et boucle YOLO → Kalman → OCR.
#pragma once

#include <map>
#include <optional>
#include <string>
#include <vector>

#include <opencv2/core.hpp>
#include <opencv2/video/tracking.hpp>

#include "detection.hpp"
#include "models/ocr.hpp"
#include "models/yolo.hpp"

namespace lapi {

// État persistant entre deux frames. La stabilisation (stabilize.py) n'est pas
// portée : déjà désactivée dans run_pipeline côté Python.
struct PipelineState {
    std::optional<cv::KalmanFilter> kalman;  // créé à la 1re détection
    int missed = 0;                          // frames consécutives sans détection
    int max_missed = 10;                     // au-delà, filtre réinitialisé
    int frame_count = 0;
    std::string last_ocr_text;               // réutilisé entre deux OCR
};

PipelineState make_initial_state();

struct PipelineResult {
    std::vector<Detection> detections;
    // Clés identiques au Python : stabilization, yolo_inference, kalman_postproc, ocr
    std::map<std::string, double> times;
};

// Pipeline complet sur une frame ; `state` est modifié en place (contrairement
// au Python qui copie — pas de partage d'état entre appelants en C++).
PipelineResult run_pipeline(const cv::Mat& frame, PipelineState& state,
                            YoloModel& yolo, OcrModel& ocr);

}  // namespace lapi
