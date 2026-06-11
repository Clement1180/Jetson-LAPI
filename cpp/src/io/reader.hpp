// Miroir de src/io/reader.py — sources vidéo (fichier, caméra CSI Jetson).
#pragma once

#include <string>

#include <opencv2/videoio.hpp>

namespace lapi {

struct VideoMeta {
    int fps = 30;
    int width = 0;
    int height = 0;
    int total = 0;
};

// Ouvre un fichier vidéo ; lève std::runtime_error si introuvable.
cv::VideoCapture open_video(const std::string& path);

// Caméra CSI Jetson via GStreamer (nvarguscamerasrc → BGR appsink),
// pipeline identique à frames_from_gstreamer.
cv::VideoCapture open_gstreamer(int width = 1280, int height = 720, int fps = 30,
                                int sensor_id = 0, int flip = 0);

VideoMeta get_video_meta(const std::string& path);

}  // namespace lapi
