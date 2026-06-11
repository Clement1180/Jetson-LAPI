#include "io/viz.hpp"

#include <sstream>

#include <opencv2/imgproc.hpp>

#include "config.hpp"

namespace lapi {

cv::Mat draw(const cv::Mat& frame, const std::vector<Detection>& detections,
             int frame_count) {
    cv::Mat out = frame.clone();
    for (const auto& det : detections) {
        const cv::Scalar color = config::COLORS[0];
        const cv::Point p1(det.box.x, det.box.y);
        const cv::Point p2(det.box.x + det.box.width, det.box.y + det.box.height);

        std::ostringstream label;
        label << " " << det.score << "  " << det.text;

        // Masque translucide à l'intérieur de la boîte
        if (!det.mask.empty()) {
            cv::Mat overlay = out.clone();
            overlay(det.box).setTo(color, det.mask == 1);
            cv::addWeighted(out, 0.6, overlay, 0.4, 0, out);
        }

        std::vector<cv::Point> poly;
        for (const auto& pt : det.polygon) poly.emplace_back(pt);
        cv::polylines(out, poly, /*isClosed=*/true, color, 2);
        cv::rectangle(out, p1, p2, color, 2);

        // Cartouche du label au-dessus de la boîte
        int baseline = 0;
        const cv::Size ts = cv::getTextSize(label.str(), cv::FONT_HERSHEY_SIMPLEX,
                                            0.6, 2, &baseline);
        cv::rectangle(out, cv::Point(p1.x, p1.y - ts.height - 10),
                      cv::Point(p1.x + ts.width, p1.y), color, -1);
        cv::putText(out, label.str(), cv::Point(p1.x, p1.y - 5),
                    cv::FONT_HERSHEY_SIMPLEX, 0.6, cv::Scalar(255, 255, 255), 2);
    }

    cv::putText(out, "frame " + std::to_string(frame_count), cv::Point(10, 30),
                cv::FONT_HERSHEY_SIMPLEX, 1, cv::Scalar(0, 255, 0), 2);
    return out;
}

}  // namespace lapi
