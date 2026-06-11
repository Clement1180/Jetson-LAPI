#include "pipeline/core.hpp"

#include <chrono>

#include "config.hpp"
#include "pipeline/detect.hpp"

namespace lapi {

namespace {

double seconds_since(std::chrono::steady_clock::time_point t0) {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - t0)
        .count();
}

std::vector<Detection> detect_plates(YoloModel& yolo, const cv::Mat& frame) {
    auto outputs = run_yolo(yolo, frame);
    return parse_yolo(yolo, outputs, frame.rows, frame.cols);
}

// Lisse le polygone de la première détection avec le filtre de Kalman.
// Sans détection, le filtre continue de prédire jusqu'à max_missed frames,
// puis est réinitialisé.
void smooth_with_kalman(std::vector<Detection>& detections,
                        PipelineState& state) {
    if (!detections.empty()) {
        const Quad polygon = detections[0].polygon;
        if (!state.kalman)
            state.kalman = make_kalman_quad(polygon);
        kalman_predict(*state.kalman);
        detections[0].polygon = kalman_update_quad(*state.kalman, polygon);
        state.missed = 0;
    } else {
        state.missed += 1;
        if (state.kalman && state.missed <= state.max_missed)
            kalman_predict(*state.kalman);
        else
            state.kalman.reset();
    }
}

// Renseigne det.text : OCR une frame sur OCR_FRAME_INTERVAL ; entre deux
// exécutions, le dernier texte reconnu est réutilisé.
void read_plate_texts(const cv::Mat& frame, std::vector<Detection>& detections,
                      PipelineState& state, OcrModel& ocr) {
    for (auto& det : detections) {
        const bool ocr_due =
            state.frame_count % config::OCR_FRAME_INTERVAL == 0 ||
            state.last_ocr_text.empty();
        if (ocr_due) {
            const cv::Mat plate = extract_plate_crop(frame, det);
            det.text = clean_plate(run_ocr(ocr, plate));
            state.last_ocr_text = det.text;
        } else {
            det.text = state.last_ocr_text;
        }
    }
}

}  // namespace

PipelineState make_initial_state() { return PipelineState{}; }

PipelineResult run_pipeline(const cv::Mat& frame, PipelineState& state,
                            YoloModel& yolo, OcrModel& ocr) {
    PipelineResult res;
    state.frame_count += 1;

    // ── 1. Stabilisation — désactivée, clé conservée pour le benchmark ──
    auto t0 = std::chrono::steady_clock::now();
    res.times["stabilization"] = seconds_since(t0);

    // ── 2. Détection YOLO ───────────────────────────────────────────────
    t0 = std::chrono::steady_clock::now();
    res.detections = detect_plates(yolo, frame);
    res.times["yolo_inference"] = seconds_since(t0);

    // ── 3. Lissage Kalman ───────────────────────────────────────────────
    t0 = std::chrono::steady_clock::now();
    smooth_with_kalman(res.detections, state);
    res.times["kalman_postproc"] = seconds_since(t0);

    // ── 4. OCR (cadencé) ────────────────────────────────────────────────
    t0 = std::chrono::steady_clock::now();
    read_plate_texts(frame, res.detections, state, ocr);
    res.times["ocr"] = seconds_since(t0);

    return res;
}

}  // namespace lapi
