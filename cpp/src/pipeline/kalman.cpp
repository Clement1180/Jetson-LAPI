#include "pipeline/kalman.hpp"

#include <stdexcept>

namespace lapi {

cv::KalmanFilter make_kalman_quad(const Quad& /*polygon*/) {
    // TODO étape 2 : reprendre matrices F/H/Q/R exactes de kalman.py
    // (cv::KalmanFilter(16, 8), état = 4 points × (x, y, vx, vy)).
    throw std::logic_error("make_kalman_quad : non porté (étape 2)");
}

Quad kalman_predict_quad(cv::KalmanFilter& /*kf*/) {
    throw std::logic_error("kalman_predict_quad : non porté (étape 2)");
}

Quad kalman_update_quad(cv::KalmanFilter& /*kf*/, const Quad& /*polygon*/) {
    throw std::logic_error("kalman_update_quad : non porté (étape 2)");
}

}  // namespace lapi
