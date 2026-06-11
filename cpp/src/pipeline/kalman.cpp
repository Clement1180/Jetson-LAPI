#include "pipeline/kalman.hpp"

namespace lapi {

namespace {

// Troncature vers zéro, comme ndarray.astype(int).
Quad state_to_quad(const cv::Mat& x) {
    Quad q;
    for (int i = 0; i < 4; ++i) {
        q[i].x = static_cast<float>(static_cast<int>(x.at<double>(2 * i, 0)));
        q[i].y = static_cast<float>(static_cast<int>(x.at<double>(2 * i + 1, 0)));
    }
    return q;
}

cv::Mat quad_to_measurement(const Quad& polygon) {
    cv::Mat z(8, 1, CV_64F);
    for (int i = 0; i < 4; ++i) {
        // float32 puis double, comme np.array(polygon, dtype=np.float32)
        z.at<double>(2 * i, 0) = static_cast<double>(polygon[i].x);
        z.at<double>(2 * i + 1, 0) = static_cast<double>(polygon[i].y);
    }
    return z;
}

}  // namespace

KalmanQuad make_kalman_quad(const Quad& polygon) {
    KalmanQuad kf;
    kf.F = cv::Mat::eye(16, 16, CV_64F);
    for (int i = 0; i < 8; ++i)
        kf.F.at<double>(i, i + 8) = 1.0;

    kf.H = cv::Mat::zeros(8, 16, CV_64F);
    for (int i = 0; i < 8; ++i)
        kf.H.at<double>(i, i) = 1.0;

    kf.R = cv::Mat::eye(8, 8, CV_64F) * 2.0;     // confiance accordée à YOLO
    kf.P = cv::Mat::eye(16, 16, CV_64F);         // incertitude initiale
    kf.Q = cv::Mat::eye(16, 16, CV_64F) * 0.01;  // mouvement supposé régulier

    kf.x = cv::Mat::zeros(16, 1, CV_64F);
    quad_to_measurement(polygon).copyTo(kf.x.rowRange(0, 8));
    return kf;
}

void kalman_predict(KalmanQuad& kf) {
    kf.x = kf.F * kf.x;
    kf.P = kf.F * kf.P * kf.F.t() + kf.Q;
}

Quad kalman_predict_quad(KalmanQuad& kf) {
    kalman_predict(kf);
    return state_to_quad(kf.x);
}

Quad kalman_update_quad(KalmanQuad& kf, const Quad& polygon) {
    // Équations de filterpy, forme de Joseph pour P.
    const cv::Mat z = quad_to_measurement(polygon);
    const cv::Mat y = z - kf.H * kf.x;
    const cv::Mat PHT = kf.P * kf.H.t();
    const cv::Mat S = kf.H * PHT + kf.R;
    const cv::Mat K = PHT * S.inv(cv::DECOMP_LU);
    kf.x = kf.x + K * y;
    const cv::Mat I_KH = cv::Mat::eye(16, 16, CV_64F) - K * kf.H;
    kf.P = I_KH * kf.P * I_KH.t() + K * kf.R * K.t();
    return state_to_quad(kf.x);
}

}  // namespace lapi
