#include "models/ocr.hpp"

#include <fstream>
#include <iostream>
#include <stdexcept>

namespace lapi {

namespace {

std::string strip(const std::string& s) {
    const auto first = s.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return "";
    const auto last = s.find_last_not_of(" \t\r\n");
    return s.substr(first, last - first + 1);
}

}  // namespace

std::vector<std::string> load_chars(const std::string& chars_path) {
    std::ifstream f(chars_path);
    if (!f) throw std::runtime_error("Dictionnaire OCR introuvable : " + chars_path);
    std::vector<std::string> chars = {""};  // index 0 = blank CTC
    std::string line;
    while (std::getline(f, line)) {
        const std::string c = strip(line);
        if (!c.empty()) chars.push_back(c);
    }
    return chars;
}

OcrModel load_ocr(const std::string& model_path, const std::string& chars_path,
                  Ort::Env& env) {
    OcrModel model;
    Ort::SessionOptions opts;
#ifdef _WIN32
    std::wstring wpath(model_path.begin(), model_path.end());
    model.session = std::make_unique<Ort::Session>(env, wpath.c_str(), opts);
#else
    model.session = std::make_unique<Ort::Session>(env, model_path.c_str(), opts);
#endif
    Ort::AllocatorWithDefaultOptions alloc;
    model.input_name = model.session->GetInputNameAllocated(0, alloc).get();
    model.chars = load_chars(chars_path);
    std::cout << "OCR  : " << model.chars.size() << " chars\n";
    return model;
}

std::string decode_ocr(const float* preds, int seq_len, int num_classes,
                       const std::vector<std::string>& chars) {
    std::string text;
    int prev = -1;
    for (int i = 0; i < seq_len; ++i) {
        const float* row = preds + static_cast<size_t>(i) * num_classes;
        int c = 0;
        for (int j = 1; j < num_classes; ++j)
            if (row[j] > row[c]) c = j;
        if (c != 0 && c != prev && c < static_cast<int>(chars.size()))
            text += chars[c];
        prev = c;
    }
    return text;
}

std::string run_ocr(OcrModel& /*model*/, const cv::Mat& /*plate*/) {
    // TODO étape 2 : 3 variantes de preprocess (CLAHE, sharpen, brut),
    // normalisation [-1, 1], padding à droite, garde le texte le plus long.
    throw std::logic_error("run_ocr : non porté (étape 2)");
}

}  // namespace lapi
