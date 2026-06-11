// Miroir de src/io/viz.py — annotation des frames (masque, polygone, boîte, label).
#pragma once

#include <vector>

#include <opencv2/core.hpp>

#include "detection.hpp"

namespace lapi {

// NB : utilise toujours COLORS[0] quel que soit le label (anomalie préservée).
cv::Mat draw(const cv::Mat& frame, const std::vector<Detection>& detections,
             int frame_count);

}  // namespace lapi
