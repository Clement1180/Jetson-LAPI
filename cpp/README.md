# Port C++ — Jetson-LAPI (étape 1 : squelette)

Structure miroir de `src/` Python. État : compile + smoke test (chargement
modèles, dict OCR, ouverture vidéo) ; les fonctions cœur lèvent
`std::logic_error` tant que l'étape 2 (port module par module) n'est pas faite.
Validation : reproduire `oracle/oracle_40frames.json` (cf. `src/make_oracle.py`).

## Build (Jetson, JetPack ≥ 5)

OpenCV vient avec JetPack. ONNX Runtime C++ : télécharger l'archive aarch64
(avec TensorRT EP) ou builder depuis les sources, puis :

```bash
cd cpp
cmake -B build -DONNXRUNTIME_ROOT_DIR=/path/to/onnxruntime
cmake --build build -j
./build/lapi ../rush_2.avi ../src/models_weight/best.onnx \
             ../src/models_weight/ocr_model.onnx ../src/models_weight/en_dict.txt
```

Sans argument, chemins par défaut de `config.hpp` (relatifs à la racine du dépôt).

## Implémenté / à porter

| Module | État |
|---|---|
| `config.hpp` | fait (constantes miroir de config.py) |
| `io/reader` | fait (fichier + pipeline GStreamer CSI identique) |
| `io/writer` | fait (mp4v + affichage) |
| `io/viz` | fait (masque translucide, polygone, boîte, label — COLORS[0] partout, anomalie préservée) |
| `models/ocr` | dict + decode CTC faits ; `run_ocr` (3 variantes preprocess) à porter |
| `models/yolo` | chargement session fait ; `run_yolo`/`parse_yolo` (letterbox, NMS, proto-masques) à porter |
| `pipeline/detect` | à porter (warp, clean_plate — version refactorisée, PAS le legacy) |
| `pipeline/kalman` | à porter (cv::KalmanFilter 16×8) |
| `pipeline/core` | à porter (ordre + clés times identiques au Python) |

`stabilize.py` : ne pas porter (désactivé côté Python).
