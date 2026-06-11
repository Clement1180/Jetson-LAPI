// Miroir de src/make_oracle.py — dump JSON des sorties pipeline sur N frames,
// à comparer à oracle/oracle_40frames.json via tools/compare_oracle.py.
// Usage : lapi_oracle <video> <yolo.onnx> <ocr.onnx> <en_dict.txt> <out.json> [n_frames]
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>

#include "config.hpp"
#include "io/reader.hpp"
#include "models/ocr.hpp"
#include "models/yolo.hpp"
#include "pipeline/core.hpp"

namespace {

void write_detection(std::ostream& os, const lapi::Detection& det) {
    os << "{\"class\": \"" << det.klass << "\", \"score\": " << det.score
       << ", \"box\": [" << det.box.x << ", " << det.box.y << ", "
       << det.box.x + det.box.width << ", " << det.box.y + det.box.height
       << "], \"polygon\": [";
    for (int i = 0; i < 4; ++i) {
        if (i) os << ", ";
        os << "[" << det.polygon[i].x << ", " << det.polygon[i].y << "]";
    }
    os << "], \"text\": \"" << det.text << "\", \"mask_shape\": ["
       << det.mask.rows << ", " << det.mask.cols << "]}";
}

}  // namespace

int main(int argc, char** argv) {
    using namespace lapi;
    if (argc < 6) {
        std::cerr << "Usage : lapi_oracle <video> <yolo.onnx> <ocr.onnx> "
                     "<en_dict.txt> <out.json> [n_frames=40]\n";
        return 2;
    }
    const std::string video_path = argv[1];
    const int n_frames = argc > 6 ? std::stoi(argv[6]) : 40;

    try {
        Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "lapi");
        YoloModel yolo = load_yolo(argv[2], env);
        OcrModel ocr = load_ocr(argv[3], argv[4], env);

        cv::VideoCapture cap = open_video(video_path);
        PipelineState state = make_initial_state();

        std::ofstream out(argv[5]);
        out << std::setprecision(std::numeric_limits<double>::max_digits10);
        out << "{\"video\": \"" << video_path << "\", \"n_frames\": " << n_frames
            << ", \"conf\": " << config::CONF << ", \"iou\": " << config::IOU
            << ", \"ocr_frame_interval\": " << config::OCR_FRAME_INTERVAL
            << ", \"frames\": [";

        cv::Mat frame;
        int n = 0;
        int total_det = 0;
        for (; n < n_frames && cap.read(frame); ++n) {
            PipelineResult res = run_pipeline(frame, state, yolo, ocr);
            if (n) out << ", ";
            out << "{\"frame\": " << n << ", \"detections\": [";
            for (size_t i = 0; i < res.detections.size(); ++i) {
                if (i) out << ", ";
                write_detection(out, res.detections[i]);
            }
            out << "]}";
            total_det += static_cast<int>(res.detections.size());
        }
        out << "]}\n";
        std::cout << "Oracle C++ écrit : " << argv[5] << " (" << n
                  << " frames, " << total_det << " détections)\n";
    } catch (const std::exception& e) {
        std::cerr << "Erreur : " << e.what() << "\n";
        return 1;
    }
    return 0;
}
