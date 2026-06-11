#include "pipeline/detect.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <vector>

#include <opencv2/imgproc.hpp>

namespace lapi {

namespace {

// Longueur attendue d'une plaque et formats acceptés (L = lettre, D = chiffre)
constexpr int PLATE_LENGTH = 6;
const std::array<std::string, 5> PLATE_MASKS = {
    "LLLDDD",  // ABC123
    "DDDLLL",  // 123ABC
    "LDDLLL",  // A12BCD
    "LLLDDL",  // AAK70N
    "DDLLLL",  // 23AAGP
};

}  // namespace

Quad order_points(const Quad& pts) {
    // argmin/argmax de la somme et de la différence (y - x), comme np.diff.
    int i_min_s = 0, i_max_s = 0, i_min_d = 0, i_max_d = 0;
    for (int i = 1; i < 4; ++i) {
        const float s = pts[i].x + pts[i].y;
        const float d = pts[i].y - pts[i].x;
        if (s < pts[i_min_s].x + pts[i_min_s].y) i_min_s = i;
        if (s > pts[i_max_s].x + pts[i_max_s].y) i_max_s = i;
        if (d < pts[i_min_d].y - pts[i_min_d].x) i_min_d = i;
        if (d > pts[i_max_d].y - pts[i_max_d].x) i_max_d = i;
    }
    return {pts[i_min_s], pts[i_min_d], pts[i_max_s], pts[i_max_d]};
}

cv::Mat warp_plate(const cv::Mat& frame, const Quad& polygon,
                   int out_w, int out_h) {
    const Quad src = order_points(polygon);
    const std::array<cv::Point2f, 4> dst = {
        cv::Point2f(0.f, 0.f),
        cv::Point2f(static_cast<float>(out_w - 1), 0.f),
        cv::Point2f(static_cast<float>(out_w - 1), static_cast<float>(out_h - 1)),
        cv::Point2f(0.f, static_cast<float>(out_h - 1)),
    };
    const cv::Mat m = cv::getPerspectiveTransform(src.data(), dst.data());
    cv::Mat out;
    cv::warpPerspective(frame, out, m, cv::Size(out_w, out_h), cv::INTER_CUBIC);
    return out;
}

cv::Mat extract_plate_crop(const cv::Mat& frame, const Detection& det) {
    // Le polygone C++ fait toujours 4 points → toujours la voie perspective
    // (la branche crop-boîte du Python ne sert que si le polygone est dégénéré).
    return warp_plate(frame, det.polygon);
}

std::string apply_mask(const std::string& text, const std::string& mask) {
    std::string result;
    const size_t n = std::min(text.size(), mask.size());
    for (size_t i = 0; i < n; ++i) {
        const unsigned char c = static_cast<unsigned char>(text[i]);
        if ((mask[i] == 'L' && std::isalpha(c)) ||
            (mask[i] == 'D' && std::isdigit(c)))
            result += text[i];
        else
            result += '_';
    }
    return result;
}

std::string clean_plate(const std::string& text) {
    // re.sub(r"[^A-Z0-9]", "", text.upper())
    std::string filtered;
    for (char ch : text) {
        const char up = static_cast<char>(
            std::toupper(static_cast<unsigned char>(ch)));
        if ((up >= 'A' && up <= 'Z') || (up >= '0' && up <= '9'))
            filtered += up;
    }
    if (static_cast<int>(filtered.size()) < PLATE_LENGTH)
        return "";

    const std::string candidate = filtered.substr(0, PLATE_LENGTH);

    std::string best;
    int best_score = -1;
    for (const auto& mask : PLATE_MASKS) {
        const std::string masked = apply_mask(candidate, mask);
        const int score = static_cast<int>(
            std::count_if(masked.begin(), masked.end(),
                          [](char c) { return c != '_'; }));
        if (score > best_score) {
            best_score = score;
            best = masked;
        }
    }
    return best;
}

}  // namespace lapi
