#pragma once

#include <array>
#include <string>
#include <tuple>
#include <vector>

namespace lapi {

struct BBox {
    float x1, y1, x2, y2;

    float cx() const { return (x1 + x2) * 0.5f; }
    float cy() const { return (y1 + y2) * 0.5f; }
    float w() const { return x2 - x1; }
    float h() const { return y2 - y1; }
};

struct Detection {
    BBox box;
    float confidence;
    int class_id;
};

struct Point2f {
    float x, y;
};

struct PlateDetection {
    std::array<Point2f, 4> keypoints;
    float confidence;

    BBox to_box() const {
        float min_x = keypoints[0].x, max_x = keypoints[0].x;
        float min_y = keypoints[0].y, max_y = keypoints[0].y;
        for (int i = 1; i < 4; ++i) {
            min_x = std::min(min_x, keypoints[i].x);
            max_x = std::max(max_x, keypoints[i].x);
            min_y = std::min(min_y, keypoints[i].y);
            max_y = std::max(max_y, keypoints[i].y);
        }
        return {min_x, min_y, max_x, max_y};
    }

    PlateDetection to_absolute(float dx, float dy) const {
        PlateDetection abs;
        abs.confidence = confidence;
        for (int i = 0; i < 4; ++i) {
            abs.keypoints[i] = {keypoints[i].x + dx, keypoints[i].y + dy};
        }
        return abs;
    }
};

struct KalmanState8D {
    std::array<float, 8> mean;
    std::array<float, 8> cov_diag;
    std::array<float, 8> Q_diag;
    std::array<float, 4> R_diag;
};

struct KalmanState4D {
    std::array<float, 4> mean;
    std::array<float, 4> cov_diag;
    std::array<float, 4> Q_diag;
    std::array<float, 4> R_diag;
};

struct TrackState {
    int track_id;
    KalmanState8D vehicle_kalman;
    int hits;
    int misses;
    int age;
    int birth_frame;

    bool has_plate;
    std::array<Point2f, 4> plate_keypoints;
    KalmanState4D plate_kalman;
    int plate_hits;
    int plate_misses;
    std::vector<std::string> ocr_history;
};

struct TrackOutput {
    int id;
    BBox vehicle_box;
    float vx, vy;
    bool has_plate;
    BBox plate_box;
    std::array<Point2f, 4> plate_keypoints;
    std::string plate_text;
    int track_age;
    int detection_hits;
    bool is_confirmed;
};

}  // namespace lapi
