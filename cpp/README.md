# Port C++ — Jetson-LAPI (étapes 1-2 : port complet, à valider sur Jetson)

Structure miroir de `src/` Python. Tous les modules sont portés ; reste la
compilation + validation contre l'oracle (jamais buildé sur le PC de dev,
pas de toolchain C++).

## Build (Jetson, JetPack ≥ 5)

OpenCV vient avec JetPack. ONNX Runtime C++ : télécharger l'archive aarch64
(avec TensorRT EP) ou builder depuis les sources, puis :

```bash
cd cpp
cmake -B build -DONNXRUNTIME_ROOT_DIR=/path/to/onnxruntime
cmake --build build -j
```

Deux exécutables :

```bash
# Pipeline complet + temps moyen par étape (sortie vidéo optionnelle en 5e arg)
./build/lapi ../rush_2.avi ../src/models_weight/best.onnx \
             ../src/models_weight/ocr_model.onnx ../src/models_weight/en_dict.txt

# Validation contre l'oracle Python (étape 0)
./build/lapi_oracle ../rush_2.avi ../src/models_weight/best.onnx \
                    ../src/models_weight/ocr_model.onnx \
                    ../src/models_weight/en_dict.txt cpp_oracle.json 40
python ../tools/compare_oracle.py ../oracle/oracle_40frames.json cpp_oracle.json
```

NB : l'oracle de référence a été généré en CPU. Pour comparer à armes égales,
première validation en forçant CPU (désactiver TensorRT/CUDA dans
`make_session_options`, ou comparer avec tolérances élargies en TensorRT FP16).

## Correspondance Python → C++

| Python | C++ | Notes |
|---|---|---|
| `config.py` | `config.hpp` | constantes identiques |
| `models/yolo.py` | `models/yolo.cpp` | quirk NMSBoxes préservé : boîtes (x1,y1,x2,y2) passées comme (x,y,w,h) |
| `models/ocr.py` | `models/ocr.cpp` | 3 variantes, max(key=len) → première en cas d'égalité |
| `pipeline/detect.py` | `pipeline/detect.cpp` | version refactorisée, PAS le legacy |
| `pipeline/kalman.py` | `pipeline/kalman.cpp` | port manuel filterpy en CV_64F (forme de Joseph), pas cv::KalmanFilter (float32) |
| `pipeline/core.py` | `pipeline/core.cpp` | mêmes clés times ; état modifié en place (pas copié) |
| `io/*` | `io/*` | pipeline GStreamer CSI identique ; viz garde COLORS[0] partout (anomalie préservée) |
| `make_oracle.py` | `make_oracle.cpp` | masques : forme seulement, pas de sha256 côté C++ |

Non porté : `stabilize.py` (désactivé côté Python), `main.py`/`metrics.py`
(évaluation dataset reste en Python), `benchmark.py` (tableau LaTeX — les
temps par étape sont déjà mesurés dans `lapi`).
