// Point d'entrée — miroir de src/mainvideo.py (vidéo annotée + benchmark).
// Étape 1 : smoke test — charge modèles + dict, ouvre la vidéo, boucle.
// La boucle complète s'activera quand run_pipeline sera porté (étape 2).
#include <iostream>

#include "config.hpp"
#include "io/reader.hpp"
#include "io/viz.hpp"
#include "io/writer.hpp"
#include "models/ocr.hpp"
#include "models/yolo.hpp"
#include "pipeline/core.hpp"

int main(int argc, char** argv) {
    using namespace lapi;

    // lapi [video] [yolo.onnx] [ocr.onnx] [en_dict.txt]
    const std::string video_path = argc > 1 ? argv[1] : config::INPUT_VIDEO;
    const std::string yolo_path = argc > 2 ? argv[2] : config::YOLO_MODEL;
    const std::string ocr_path = argc > 3 ? argv[3] : config::OCR_MODEL;
    const std::string chars_path = argc > 4 ? argv[4] : config::CHARS_PATH;

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
        PipelineState state = make_initial_state();
        cv::Mat frame;
        int n = 0;
        while (cap.read(frame)) {
            PipelineResult res = run_pipeline(frame, state, yolo, ocr);
            cv::Mat annotated = draw(frame, res.detections, state.frame_count);
            (void)annotated;
            ++n;
        }
        std::cout << n << " frames traitées\n";
    } catch (const std::logic_error& e) {
        // Stubs étape 2 pas encore portés : le smoke test s'arrête ici.
        std::cout << "Squelette OK, port incomplet : " << e.what() << "\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Erreur : " << e.what() << "\n";
        return 1;
    }
    return 0;
}
