#include "pipeline/detect.hpp"

#include <stdexcept>

#include <opencv2/imgproc.hpp>

namespace lapi {

Quad order_points(const Quad& /*pts*/) {
    // TODO étape 2 : même tri que detect.py (somme min/max, diff min/max).
    throw std::logic_error("order_points : non porté (étape 2)");
}

cv::Mat warp_plate(const cv::Mat& /*frame*/, const Quad& /*polygon*/,
                   int /*out_w*/, int /*out_h*/) {
    // TODO étape 2 : cv::getPerspectiveTransform + cv::warpPerspective.
    throw std::logic_error("warp_plate : non porté (étape 2)");
}

cv::Mat extract_plate_crop(const cv::Mat& /*frame*/, const Detection& /*det*/) {
    throw std::logic_error("extract_plate_crop : non porté (étape 2)");
}

std::string apply_mask(const std::string& /*text*/, const std::string& /*mask*/) {
    throw std::logic_error("apply_mask : non porté (étape 2)");
}

std::string clean_plate(const std::string& /*text*/) {
    // TODO étape 2 : masques L/D + format 6 chars (std::regex), copie exacte
    // de la version refactorisée — PAS celle du legacy inference_video_ocr.py.
    throw std::logic_error("clean_plate : non porté (étape 2)");
}

}  // namespace lapi
