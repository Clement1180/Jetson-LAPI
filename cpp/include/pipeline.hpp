#pragma once

#include "inference.hpp"
#include "tracker.hpp"
#include "types.hpp"
#include <string>
#include <vector>

namespace lapi {

struct PipelineConfig {
    std::string car_engine_path;
    std::string plate_engine_path;
    std::string ocr_engine_path;
    std::string ocr_dict_path;

    float car_conf_thresh = 0.5f;
    float car_iou_thresh = 0.45f;
    float plate_conf_thresh = 0.4f;
};

class Pipeline {
public:
    bool init(const PipelineConfig& config);
    std::vector<TrackOutput> process_frame(const uint8_t* bgr_data, int width, int height);
    int frame_count() const { return frame_count_; }

private:
    void preprocess_clahe(const uint8_t* bgr, int w, int h, uint8_t* out);
    void warp_plate(const uint8_t* car_crop, int cw, int ch,
                    const std::array<Point2f, 4>& kpts,
                    uint8_t* plate_out, int pw, int ph);

    YOLOCarDetector car_detector_;
    YOLOPlateDetector plate_detector_;
    PPOCRRecognizer ocr_;
    Tracker tracker_;

    PipelineConfig config_;
    int frame_count_ = 0;
};

}  // namespace lapi
