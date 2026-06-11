// Miroir de src/pipeline/kalman.py — filtre 16×8 sur le quadrilatère plaque.
#pragma once

#include <array>

#include <opencv2/core.hpp>
#include <opencv2/video/tracking.hpp>

namespace lapi {

using Quad = std::array<cv::Point2f, 4>;

// Filtre 16 états (4 points × (x, y, vx, vy)) / 8 mesures, initialisé sur le polygone.
cv::KalmanFilter make_kalman_quad(const Quad& polygon);

Quad kalman_predict_quad(cv::KalmanFilter& kf);

Quad kalman_update_quad(cv::KalmanFilter& kf, const Quad& polygon);

}  // namespace lapi
