#include "pipeline.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <iostream>

namespace lapi {

bool Pipeline::init(const PipelineConfig& config) {
    config_ = config;

    if (!car_detector_.init(config.car_engine_path)) {
        std::cerr << "[Pipeline] Failed to load car detector" << std::endl;
        return false;
    }

    if (!plate_detector_.init(config.plate_engine_path)) {
        std::cerr << "[Pipeline] Failed to load plate detector" << std::endl;
        return false;
    }

    if (!ocr_.init(config.ocr_engine_path, config.ocr_dict_path)) {
        std::cerr << "[Pipeline] Failed to load OCR" << std::endl;
        return false;
    }

    return true;
}

void Pipeline::preprocess_clahe(const uint8_t* bgr, int w, int h, uint8_t* out) {
    // Simplified CLAHE on luminance channel
    // Full implementation uses CUDA or OpenCV; here we do a basic local histogram eq
    std::memcpy(out, bgr, w * h * 3);

    constexpr int TILE = 8;
    int tw = w / TILE, th = h / TILE;
    if (tw == 0 || th == 0) return;

    // Convert to luminance, equalize tiles, write back
    // For production: use cv::cuda::CLAHE or custom CUDA kernel
    for (int ty = 0; ty < TILE; ++ty) {
        for (int tx = 0; tx < TILE; ++tx) {
            int x0 = tx * tw, y0 = ty * th;
            int x1 = (tx == TILE - 1) ? w : x0 + tw;
            int y1 = (ty == TILE - 1) ? h : y0 + th;

            // Compute histogram of luminance
            int hist[256] = {};
            int count = 0;
            for (int y = y0; y < y1; ++y) {
                for (int x = x0; x < x1; ++x) {
                    int idx = (y * w + x) * 3;
                    int lum = (bgr[idx] * 29 + bgr[idx + 1] * 150 + bgr[idx + 2] * 77) >> 8;
                    hist[lum]++;
                    count++;
                }
            }

            // Clip histogram (clip_limit = 3.0 * avg)
            int clip_limit = static_cast<int>(3.0f * count / 256);
            int excess = 0;
            for (int i = 0; i < 256; ++i) {
                if (hist[i] > clip_limit) {
                    excess += hist[i] - clip_limit;
                    hist[i] = clip_limit;
                }
            }
            int bonus = excess / 256;
            for (int i = 0; i < 256; ++i)
                hist[i] += bonus;

            // Build CDF
            int cdf[256];
            cdf[0] = hist[0];
            for (int i = 1; i < 256; ++i)
                cdf[i] = cdf[i - 1] + hist[i];

            int cdf_min = 0;
            for (int i = 0; i < 256; ++i) {
                if (cdf[i] > 0) { cdf_min = cdf[i]; break; }
            }

            // Apply equalization
            float scale = 255.0f / std::max(1, count - cdf_min);
            for (int y = y0; y < y1; ++y) {
                for (int x = x0; x < x1; ++x) {
                    int idx = (y * w + x) * 3;
                    for (int c = 0; c < 3; ++c) {
                        int val = out[idx + c];
                        int eq = static_cast<int>((cdf[val] - cdf_min) * scale);
                        out[idx + c] = static_cast<uint8_t>(std::clamp(eq, 0, 255));
                    }
                }
            }
        }
    }
}

void Pipeline::warp_plate(const uint8_t* car_crop, int cw, int ch,
                          const std::array<Point2f, 4>& kpts,
                          uint8_t* plate_out, int pw, int ph) {
    // Order points: TL, TR, BR, BL
    std::array<Point2f, 4> pts = kpts;
    // Sort by sum(x+y) for TL/BR, diff(x-y) for TR/BL
    std::array<float, 4> sums, diffs;
    for (int i = 0; i < 4; ++i) {
        sums[i] = pts[i].x + pts[i].y;
        diffs[i] = pts[i].x - pts[i].y;
    }
    Point2f tl = pts[std::distance(sums.begin(), std::min_element(sums.begin(), sums.end()))];
    Point2f br = pts[std::distance(sums.begin(), std::max_element(sums.begin(), sums.end()))];
    Point2f tr = pts[std::distance(diffs.begin(), std::max_element(diffs.begin(), diffs.end()))];
    Point2f bl = pts[std::distance(diffs.begin(), std::min_element(diffs.begin(), diffs.end()))];

    // Compute perspective transform matrix (3x3)
    // src: tl, tr, br, bl → dst: (0,0), (pw-1,0), (pw-1,ph-1), (0,ph-1)
    float src[8] = {tl.x, tl.y, tr.x, tr.y, br.x, br.y, bl.x, bl.y};
    float dst[8] = {0, 0, static_cast<float>(pw - 1), 0,
                    static_cast<float>(pw - 1), static_cast<float>(ph - 1),
                    0, static_cast<float>(ph - 1)};

    // Solve 8x8 system for homography (simplified)
    // Using direct formula for 4-point correspondences
    // For production: use OpenCV or custom solver
    // Here: bilinear interpolation with inverse mapping approximation
    float inv_pw = 1.0f / (pw - 1);
    float inv_ph = 1.0f / (ph - 1);

    for (int y = 0; y < ph; ++y) {
        float v = y * inv_ph;
        for (int x = 0; x < pw; ++x) {
            float u = x * inv_pw;

            // Bilinear interpolation of source coords
            float sx = (1 - u) * (1 - v) * tl.x + u * (1 - v) * tr.x +
                       u * v * br.x + (1 - u) * v * bl.x;
            float sy = (1 - u) * (1 - v) * tl.y + u * (1 - v) * tr.y +
                       u * v * br.y + (1 - u) * v * bl.y;

            int sx_i = std::clamp(static_cast<int>(sx), 0, cw - 1);
            int sy_i = std::clamp(static_cast<int>(sy), 0, ch - 1);

            int src_idx = (sy_i * cw + sx_i) * 3;
            int dst_idx = (y * pw + x) * 3;
            plate_out[dst_idx] = car_crop[src_idx];
            plate_out[dst_idx + 1] = car_crop[src_idx + 1];
            plate_out[dst_idx + 2] = car_crop[src_idx + 2];
        }
    }
}

std::vector<TrackOutput> Pipeline::process_frame(const uint8_t* bgr_data, int width, int height) {
    frame_count_++;

    // 1. Detect vehicles
    auto detections = car_detector_.detect(bgr_data, width, height,
                                           config_.car_conf_thresh, config_.car_iou_thresh);

    // 2. Update tracker (predict + associate + update Kalman)
    auto tracks = tracker_.update(detections, frame_count_);

    // 3. For each matched detection, try plate detection + OCR
    for (auto& det : detections) {
        int x1 = std::max(0, static_cast<int>(det.box.x1));
        int y1 = std::max(0, static_cast<int>(det.box.y1));
        int x2 = std::min(width, static_cast<int>(det.box.x2));
        int y2 = std::min(height, static_cast<int>(det.box.y2));

        int cw = x2 - x1, ch = y2 - y1;
        if (cw <= 0 || ch <= 0) continue;

        // Extract car crop
        std::vector<uint8_t> crop(cw * ch * 3);
        for (int row = 0; row < ch; ++row) {
            std::memcpy(crop.data() + row * cw * 3,
                        bgr_data + ((y1 + row) * width + x1) * 3,
                        cw * 3);
        }

        // Plate detection on crop
        PlateDetection plate;
        if (!plate_detector_.detect(crop.data(), cw, ch, plate, config_.plate_conf_thresh))
            continue;

        // Warp plate for OCR
        constexpr int PLATE_W = 480, PLATE_H = 96;
        std::vector<uint8_t> plate_img(PLATE_W * PLATE_H * 3);

        // Apply CLAHE before OCR
        std::vector<uint8_t> enhanced(cw * ch * 3);
        preprocess_clahe(crop.data(), cw, ch, enhanced.data());

        warp_plate(enhanced.data(), cw, ch, plate.keypoints, plate_img.data(), PLATE_W, PLATE_H);

        // OCR
        std::string text = ocr_.recognize(plate_img.data(), PLATE_W, PLATE_H);

        // Store plate result back into tracker
        // (The tracker exposes internal state for plate updates)
        if (!text.empty()) {
            PlateDetection abs_plate = plate.to_absolute(static_cast<float>(x1), static_cast<float>(y1));
            // Find matching track and update plate info
            for (auto& tout : tracks) {
                float iou_val = compute_iou(det.box, tout.vehicle_box);
                if (iou_val > 0.5f) {
                    tout.has_plate = true;
                    tout.plate_keypoints = abs_plate.keypoints;
                    tout.plate_box = abs_plate.to_box();
                    if (tout.plate_text.empty())
                        tout.plate_text = text;
                    break;
                }
            }
        }
    }

    return tracks;
}

}  // namespace lapi
