// Miroir de src/models/ocr.py — session OCR (CRNN/CTC) et dictionnaire de chars.
#pragma once

#include <memory>
#include <string>
#include <vector>

#include <onnxruntime_cxx_api.h>
#include <opencv2/core.hpp>

namespace lapi {

// Dimensions d'entrée du réseau OCR (C, H, W)
inline constexpr int OCR_INPUT_CHANNELS = 3;
inline constexpr int OCR_INPUT_HEIGHT = 48;
inline constexpr int OCR_INPUT_WIDTH = 320;

struct OcrModel {
    std::unique_ptr<Ort::Session> session;
    std::string input_name;
    std::vector<std::string> chars;  // index 0 = blank CTC
};

// Charge le dictionnaire : [""] + lignes non vides strip()ées, comme en Python.
std::vector<std::string> load_chars(const std::string& chars_path);

OcrModel load_ocr(const std::string& model_path, const std::string& chars_path,
                  Ort::Env& env);

// Décodage CTC greedy : supprime blanks (0) et répétitions consécutives.
std::string decode_ocr(const float* preds, int seq_len, int num_classes,
                       const std::vector<std::string>& chars);

// 3 variantes de prétraitement, garde le texte le plus long.
std::string run_ocr(OcrModel& model, const cv::Mat& plate);

}  // namespace lapi
