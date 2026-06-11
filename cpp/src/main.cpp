// Point d'entrée — miroir de src/mainvideo.py : pipeline complet sur la vidéo,
// temps moyen par étape en sortie.
#include <iostream>
#include <map>

#include "config.hpp"
#include "io/reader.hpp"
#include "io/viz.hpp"
#include "io/writer.hpp"
#include "models/ocr.hpp"
#include "models/yolo.hpp"
#include "pipeline/core.hpp"

int main(int argc, char** argv) {
    using namespace lapi;

    // lapi [video] [yolo.onnx] [ocr.onnx] [en_dict.txt] [sortie.mp4]
    const std::string video_path = argc > 1 ? argv[1] : config::INPUT_VIDEO;
    const std::string yolo_path = argc > 2 ? argv[2] : config::YOLO_MODEL;
    const std::string ocr_path = argc > 3 ? argv[3] : config::OCR_MODEL;
    const std::string chars_path = argc > 4 ? argv[4] : config::CHARS_PATH;
    const std::string output_path = argc > 5 ? argv[5] : "";

    try {
        Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "lapi");
        YoloModel yolo = load_yolo(yolo_path, env);
        std::cout << "YOLO : entrée " << yolo.input_width << "x"
                  << yolo.input_height << "\n";
        OcrModel ocr = load_ocr(ocr_path, chars_path, env);

        const VideoMeta meta = get_video_meta(video_path);
        std::cout << "Vidéo : " << meta.width << "x" << meta.height << " @ "
                  << meta.fps << " fps, " << meta.total << " frames\n";

        cv::VideoCapture cap = open_video(video_path);
        cv::VideoWriter writer;
        if (!output_path.empty())
            writer = open_video_writer(output_path, meta.fps, meta.width,
                                       meta.height);

        PipelineState state = make_initial_state();
        std::map<std::string, double> totals;
        cv::Mat frame;
        int n = 0;
        while (cap.read(frame)) {
            PipelineResult res = run_pipeline(frame, state, yolo, ocr);
            for (const auto& [step, t] : res.times) totals[step] += t;
            if (writer.isOpened())
                writer.write(draw(frame, res.detections, state.frame_count));
            ++n;
        }
        if (writer.isOpened()) writer.release();

        std::cout << n << " frames traitées\n";
        double total = 0;
        for (const auto& [step, t] : totals) total += t;
        for (const auto& [step, t] : totals)
            std::cout << "  " << step << " : " << t / n * 1000 << " ms/frame\n";
        if (n > 0 && total > 0)
            std::cout << "  total : " << total / n * 1000 << " ms/frame ("
                      << n / total << " FPS)\n";
    } catch (const std::exception& e) {
        std::cerr << "Erreur : " << e.what() << "\n";
        return 1;
    }
    return 0;
}
