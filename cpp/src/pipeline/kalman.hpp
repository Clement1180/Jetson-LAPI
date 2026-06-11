// Miroir de src/pipeline/kalman.py — filtre 16×8 sur le quadrilatère plaque.
// Implémentation manuelle en double (CV_64F) pour coller à filterpy
// (cv::KalmanFilter travaille en float32 et n'utilise pas la forme de Joseph).
#pragma once

#include <opencv2/core.hpp>

#include "detection.hpp"

namespace lapi {

struct KalmanQuad {
    cv::Mat x;  // état 16×1 : 4 points (x, y) puis leurs vitesses
    cv::Mat P;  // covariance 16×16
    cv::Mat F;  // transition : position += vitesse
    cv::Mat H;  // observation : les 8 coordonnées de position
    cv::Mat Q;  // bruit de processus (×0.01)
    cv::Mat R;  // bruit de mesure (×2)
};

KalmanQuad make_kalman_quad(const Quad& polygon);

// x = Fx ; P = FPFᵀ + Q
void kalman_predict(KalmanQuad& kf);

// Polygone prédit, coordonnées tronquées en int comme astype(int) NumPy.
Quad kalman_predict_quad(KalmanQuad& kf);

// Met à jour avec le polygone mesuré — retourne le polygone lissé (int).
Quad kalman_update_quad(KalmanQuad& kf, const Quad& polygon);

}  // namespace lapi
