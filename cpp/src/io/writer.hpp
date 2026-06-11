// Miroir de src/io/writer.py — écriture vidéo et affichage écran.
#pragma once

#include <string>

#include <opencv2/videoio.hpp>

namespace lapi {

// Crée le dossier parent si besoin, ouvre un writer mp4v ; lève si échec.
cv::VideoWriter open_video_writer(const std::string& path, int fps,
                                  int width, int height);

// Affiche la frame ; retourne false si l'utilisateur appuie sur 'q'.
bool display(const std::string& window, const cv::Mat& frame);

void close_display();

}  // namespace lapi
