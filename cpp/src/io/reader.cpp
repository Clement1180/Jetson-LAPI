#include "io/reader.hpp"

#include <sstream>
#include <stdexcept>

namespace lapi {

cv::VideoCapture open_video(const std::string& path) {
    cv::VideoCapture cap(path);
    if (!cap.isOpened())
        throw std::runtime_error("Vidéo introuvable : " + path);
    return cap;
}

cv::VideoCapture open_gstreamer(int width, int height, int fps,
                                int sensor_id, int flip) {
    std::ostringstream p;
    p << "nvarguscamerasrc sensor-id=" << sensor_id << " ! "
      << "video/x-raw(memory:NVMM), width=" << width << ", height=" << height
      << ", format=NV12, framerate=" << fps << "/1 ! "
      << "nvvidconv flip-method=" << flip << " ! "
      << "video/x-raw, format=BGRx ! "
      << "videoconvert ! video/x-raw, format=BGR ! appsink";
    cv::VideoCapture cap(p.str(), cv::CAP_GSTREAMER);
    if (!cap.isOpened())
        throw std::runtime_error("GStreamer indisponible");
    return cap;
}

VideoMeta get_video_meta(const std::string& path) {
    cv::VideoCapture cap(path);
    VideoMeta meta;
    const int fps = static_cast<int>(cap.get(cv::CAP_PROP_FPS));
    meta.fps = fps > 0 ? fps : 30;
    meta.width = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_WIDTH));
    meta.height = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_HEIGHT));
    meta.total = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_COUNT));
    cap.release();
    return meta;
}

}  // namespace lapi
