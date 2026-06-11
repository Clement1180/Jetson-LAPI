#include "pipeline/core.hpp"

#include <chrono>
#include <stdexcept>

namespace lapi {

PipelineState make_initial_state() { return PipelineState{}; }

PipelineResult run_pipeline(const cv::Mat& /*frame*/, PipelineState& state,
                            YoloModel& /*yolo*/, OcrModel& /*ocr*/) {
    state.frame_count += 1;
    // TODO étape 2, même ordre que core.py :
    //   1. stabilization  — no-op chronométré (désactivée, clé conservée)
    //   2. yolo_inference — run_yolo + parse_yolo
    //   3. kalman_postproc — _smooth_with_kalman (missed/max_missed, reset)
    //   4. ocr            — 1 frame sur OCR_FRAME_INTERVAL, sinon last_ocr_text
    throw std::logic_error("run_pipeline : non porté (étape 2)");
}

}  // namespace lapi
