// Miroir de src/pipeline/detect.py — extraction du crop plaque et nettoyage du texte.
#pragma once

#include <string>

#include <opencv2/core.hpp>

#include "detection.hpp"

namespace lapi {

// Trie les 4 points : haut-gauche, haut-droit, bas-droit, bas-gauche.
Quad order_points(const Quad& pts);

// Redresse la plaque par transformation perspective (200×60 par défaut).
cv::Mat warp_plate(const cv::Mat& frame, const Quad& polygon,
                   int out_w = 200, int out_h = 60);

// Crop redressé de la plaque à partir d'une détection.
cv::Mat extract_plate_crop(const cv::Mat& frame, const Detection& det);

// Applique un masque L/D (lettre/chiffre) au texte brut.
std::string apply_mask(const std::string& text, const std::string& mask);

// Filtre le texte OCR brut vers un format plaque 6 caractères.
std::string clean_plate(const std::string& text);

}  // namespace lapi
