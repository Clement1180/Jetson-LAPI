#include "io/writer.hpp"

#include <filesystem>
#include <stdexcept>

#include <opencv2/highgui.hpp>

namespace lapi {

cv::VideoWriter open_video_writer(const std::string& path, int fps,
                                  int width, int height) {
    const auto parent = std::filesystem::path(path).parent_path();
    if (!parent.empty()) std::filesystem::create_directories(parent);
    cv::VideoWriter handle(path, cv::VideoWriter::fourcc('m', 'p', '4', 'v'),
                           fps, cv::Size(width, height));
    if (!handle.isOpened())
        throw std::runtime_error("Impossible d'ouvrir le writer : " + path);
    return handle;
}

bool display(const std::string& window, const cv::Mat& frame) {
    cv::imshow(window, frame);
    return (cv::waitKey(1) & 0xFF) != 'q';
}

void close_display() { cv::destroyAllWindows(); }

}  // namespace lapi
