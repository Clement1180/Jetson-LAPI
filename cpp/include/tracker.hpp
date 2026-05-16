#pragma once

#include "types.hpp"
#include <unordered_map>
#include <vector>

namespace lapi {

constexpr int MAX_AGE = 30;
constexpr int MIN_HITS = 5;
constexpr float IOU_THRESHOLD = 0.3f;
constexpr float DISTANCE_THRESHOLD = 1.0f;

float compute_iou(const BBox& a, const BBox& b);

KalmanState8D create_kalman_vehicle(const BBox& box);
KalmanState8D kalman_predict_vehicle(const KalmanState8D& state);
KalmanState8D kalman_update_vehicle(const KalmanState8D& state, float cx, float cy, float w, float h);
BBox kalman_to_box_vehicle(const KalmanState8D& state);

KalmanState4D create_kalman_plate(const BBox& plate_box, const BBox& vehicle_box);
KalmanState4D kalman_predict_plate(const KalmanState4D& state);
KalmanState4D kalman_update_plate(const KalmanState4D& state, float dx, float dy, float pw, float ph);
BBox kalman_to_box_plate(const KalmanState4D& state, const BBox& vehicle_box);

class Tracker {
public:
    Tracker() = default;

    std::vector<TrackOutput> update(const std::vector<Detection>& detections, int frame_count);

private:
    struct Match {
        int track_id;
        int det_idx;
    };

    void associate(const std::vector<Detection>& detections,
                   std::vector<Match>& matches,
                   std::vector<int>& unmatched_dets,
                   std::vector<int>& unmatched_tracks);

    std::unordered_map<int, TrackState> tracks_;
    int next_id_ = 1;
};

}  // namespace lapi
