// Détection plaque — miroir du dict Python {class, score, box, polygon, mask, text}.
#pragma once

#include <array>
#include <string>

#include <opencv2/core.hpp>

namespace lapi {

struct Detection {
    std::string klass;                    // "day" ou "night"
    float score = 0.f;
    cv::Rect box;                         // x1, y1 → x2, y2 (stocké x,y,w,h)
    std::array<cv::Point2f, 4> polygon;   // quadrilatère plaque
    cv::Mat mask;                         // masque binaire, taille de la box
    std::string text;                     // texte OCR (6 chars après clean_plate)
};

}  // namespace lapi
