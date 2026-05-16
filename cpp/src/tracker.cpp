#include "tracker.hpp"
#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <unordered_set>

namespace lapi {

float compute_iou(const BBox& a, const BBox& b) {
    float xi1 = std::max(a.x1, b.x1);
    float yi1 = std::max(a.y1, b.y1);
    float xi2 = std::min(a.x2, b.x2);
    float yi2 = std::min(a.y2, b.y2);

    float inter_w = std::max(0.0f, xi2 - xi1);
    float inter_h = std::max(0.0f, yi2 - yi1);
    float inter = inter_w * inter_h;

    float area_a = a.w() * a.h();
    float area_b = b.w() * b.h();
    float uni = area_a + area_b - inter;

    return uni > 0 ? inter / uni : 0.0f;
}

// ============================================================
// Kalman Vehicle (8D: cx, cy, w, h, vx, vy, vw, vh)
// ============================================================

KalmanState8D create_kalman_vehicle(const BBox& box) {
    KalmanState8D s{};
    float cx = box.cx(), cy = box.cy(), w = box.w(), h = box.h();

    s.mean = {cx, cy, w, h, 0.0f, 0.0f, 0.0f, 0.0f};
    s.cov_diag = {w * 0.1f, h * 0.1f, w * 0.1f, h * 0.1f,
                  100.0f, 100.0f, 100.0f, 100.0f};
    s.Q_diag = {0.1f, 0.1f, 0.1f, 0.1f, 1.0f, 1.0f, 0.5f, 0.5f};
    s.R_diag = {w * 0.05f, h * 0.05f, w * 0.05f, h * 0.05f};
    return s;
}

KalmanState8D kalman_predict_vehicle(const KalmanState8D& state) {
    KalmanState8D s = state;
    // x_pred = F * x  (constant velocity model)
    s.mean[0] += s.mean[4];  // cx += vx
    s.mean[1] += s.mean[5];  // cy += vy
    s.mean[2] += s.mean[6];  // w += vw
    s.mean[3] += s.mean[7];  // h += vh

    // P_pred = F*P*F' + Q (diagonal approximation)
    for (int i = 0; i < 4; ++i)
        s.cov_diag[i] += s.cov_diag[i + 4] + s.Q_diag[i];
    for (int i = 4; i < 8; ++i)
        s.cov_diag[i] += s.Q_diag[i];

    return s;
}

KalmanState8D kalman_update_vehicle(const KalmanState8D& state, float cx, float cy, float w, float h) {
    KalmanState8D s = state;
    float z[4] = {cx, cy, w, h};

    for (int i = 0; i < 4; ++i) {
        float innovation = z[i] - s.mean[i];
        float S = s.cov_diag[i] + s.R_diag[i];
        float K = s.cov_diag[i] / S;

        s.mean[i] += K * innovation;
        s.mean[i + 4] += K * innovation;  // velocity correction
        s.cov_diag[i] *= (1.0f - K);
    }

    return s;
}

BBox kalman_to_box_vehicle(const KalmanState8D& state) {
    float cx = state.mean[0], cy = state.mean[1];
    float w = state.mean[2], h = state.mean[3];
    return {cx - w * 0.5f, cy - h * 0.5f, cx + w * 0.5f, cy + h * 0.5f};
}

// ============================================================
// Kalman Plate (4D: dx, dy, pw, ph relative to vehicle)
// ============================================================

KalmanState4D create_kalman_plate(const BBox& plate_box, const BBox& vehicle_box) {
    KalmanState4D s{};
    float v_cx = vehicle_box.cx(), v_cy = vehicle_box.cy();
    float p_cx = plate_box.cx(), p_cy = plate_box.cy();

    s.mean = {p_cx - v_cx, p_cy - v_cy, plate_box.w(), plate_box.h()};
    s.cov_diag = {vehicle_box.w() * 0.1f, vehicle_box.h() * 0.1f,
                  plate_box.w() * 0.1f, plate_box.h() * 0.1f};
    s.Q_diag = {5.0f, 5.0f, 2.0f, 2.0f};
    s.R_diag = {10.0f, 10.0f, 5.0f, 5.0f};
    return s;
}

KalmanState4D kalman_predict_plate(const KalmanState4D& state) {
    KalmanState4D s = state;
    for (int i = 0; i < 4; ++i)
        s.cov_diag[i] += s.Q_diag[i];
    return s;
}

KalmanState4D kalman_update_plate(const KalmanState4D& state, float dx, float dy, float pw, float ph) {
    KalmanState4D s = state;
    float z[4] = {dx, dy, pw, ph};

    for (int i = 0; i < 4; ++i) {
        float innovation = z[i] - s.mean[i];
        float S = s.cov_diag[i] + s.R_diag[i];
        float K = s.cov_diag[i] / S;
        s.mean[i] += K * innovation;
        s.cov_diag[i] *= (1.0f - K);
    }
    return s;
}

BBox kalman_to_box_plate(const KalmanState4D& state, const BBox& vehicle_box) {
    float v_cx = vehicle_box.cx(), v_cy = vehicle_box.cy();
    float p_cx = v_cx + state.mean[0], p_cy = v_cy + state.mean[1];
    float pw = state.mean[2], ph = state.mean[3];
    return {p_cx - pw * 0.5f, p_cy - ph * 0.5f, p_cx + pw * 0.5f, p_cy + ph * 0.5f};
}

// ============================================================
// Tracker
// ============================================================

void Tracker::associate(
    const std::vector<Detection>& detections,
    std::vector<Match>& matches,
    std::vector<int>& unmatched_dets,
    std::vector<int>& unmatched_tracks) {

    matches.clear();
    unmatched_dets.clear();
    unmatched_tracks.clear();

    if (tracks_.empty()) {
        for (int i = 0; i < static_cast<int>(detections.size()); ++i)
            unmatched_dets.push_back(i);
        return;
    }

    if (detections.empty()) {
        for (auto& [id, _] : tracks_)
            unmatched_tracks.push_back(id);
        return;
    }

    // Build cost matrix
    struct CostEntry {
        int det_idx;
        int track_id;
        float cost;
    };
    std::vector<CostEntry> costs;

    for (int i = 0; i < static_cast<int>(detections.size()); ++i) {
        for (auto& [track_id, track] : tracks_) {
            BBox pred_box = kalman_to_box_vehicle(track.vehicle_kalman);
            float iou = compute_iou(detections[i].box, pred_box);

            // Distance cost
            float dx = pred_box.cx() - detections[i].box.cx();
            float dy = pred_box.cy() - detections[i].box.cy();
            float dist = std::sqrt(dx * dx + dy * dy);
            float norm_dist = dist / std::sqrt(pred_box.w() * pred_box.h());

            if (iou > IOU_THRESHOLD && norm_dist < DISTANCE_THRESHOLD) {
                float cost = 1.0f - iou + norm_dist * 0.1f;
                costs.push_back({i, track_id, cost});
            }
        }
    }

    // Greedy assignment sorted by cost
    std::sort(costs.begin(), costs.end(),
              [](const CostEntry& a, const CostEntry& b) { return a.cost < b.cost; });

    std::unordered_set<int> used_dets;
    std::unordered_set<int> used_tracks;

    for (auto& c : costs) {
        if (used_dets.count(c.det_idx) || used_tracks.count(c.track_id))
            continue;
        matches.push_back({c.track_id, c.det_idx});
        used_dets.insert(c.det_idx);
        used_tracks.insert(c.track_id);
    }

    for (int i = 0; i < static_cast<int>(detections.size()); ++i) {
        if (!used_dets.count(i))
            unmatched_dets.push_back(i);
    }

    for (auto& [id, _] : tracks_) {
        if (!used_tracks.count(id))
            unmatched_tracks.push_back(id);
    }
}

std::vector<TrackOutput> Tracker::update(const std::vector<Detection>& detections, int frame_count) {
    // Predict all existing tracks
    for (auto& [id, track] : tracks_) {
        track.vehicle_kalman = kalman_predict_vehicle(track.vehicle_kalman);
        if (track.has_plate)
            track.plate_kalman = kalman_predict_plate(track.plate_kalman);
        track.age++;
    }

    // Associate
    std::vector<Match> matches;
    std::vector<int> unmatched_dets;
    std::vector<int> unmatched_tracks_ids;
    associate(detections, matches, unmatched_dets, unmatched_tracks_ids);

    // Update matched tracks
    for (auto& m : matches) {
        auto& track = tracks_[m.track_id];
        auto& det = detections[m.det_idx];
        float cx = det.box.cx(), cy = det.box.cy();
        float w = det.box.w(), h = det.box.h();
        track.vehicle_kalman = kalman_update_vehicle(track.vehicle_kalman, cx, cy, w, h);
        track.hits++;
        track.misses = 0;
    }

    // Handle unmatched tracks
    for (int id : unmatched_tracks_ids) {
        tracks_[id].misses++;
        if (tracks_[id].misses > MAX_AGE)
            tracks_.erase(id);
    }

    // Create new tracks for unmatched detections
    for (int i : unmatched_dets) {
        TrackState t{};
        t.track_id = next_id_++;
        t.vehicle_kalman = create_kalman_vehicle(detections[i].box);
        t.hits = 1;
        t.misses = 0;
        t.age = 1;
        t.birth_frame = frame_count;
        t.has_plate = false;
        t.plate_hits = 0;
        t.plate_misses = 0;
        tracks_[t.track_id] = t;
    }

    // Generate output
    std::vector<TrackOutput> output;
    for (auto& [id, track] : tracks_) {
        if (track.hits < MIN_HITS && track.age < MIN_HITS * 2)
            continue;

        TrackOutput out{};
        out.id = track.track_id;
        out.vehicle_box = kalman_to_box_vehicle(track.vehicle_kalman);
        out.vx = track.vehicle_kalman.mean[4];
        out.vy = track.vehicle_kalman.mean[5];
        out.has_plate = track.has_plate;
        out.track_age = track.age;
        out.detection_hits = track.hits;
        out.is_confirmed = track.hits >= MIN_HITS;

        if (track.has_plate) {
            out.plate_box = kalman_to_box_plate(track.plate_kalman, out.vehicle_box);
            out.plate_keypoints = track.plate_keypoints;
            if (!track.ocr_history.empty()) {
                // Most frequent OCR result
                std::unordered_map<std::string, int> counts;
                for (auto& s : track.ocr_history) counts[s]++;
                int best_count = 0;
                for (auto& [text, cnt] : counts) {
                    if (cnt > best_count) {
                        best_count = cnt;
                        out.plate_text = text;
                    }
                }
            }
        }

        output.push_back(out);
    }

    return output;
}

}  // namespace lapi
