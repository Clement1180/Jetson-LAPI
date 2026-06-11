# Roadmap port C++ — Jetson-LAPI

Objectif : porter le pipeline LAPI (YOLO-seg → Kalman → OCR) de Python vers C++, d'abord sur Jetson (TensorRT), puis sur une carte low-budget.

Contexte : code Python ~1070 lignes, dépendances = OpenCV + NumPy + ONNX Runtime uniquement. Port très faisable.

## Étape 0 — Geler la référence Python (1j)

- Commiter le refactoring actuel (tout est en working tree !)
- Sauver des sorties bit-exactes sur 40 frames (boxes, polygones, textes OCR) → fichier JSON = oracle de validation pour le port

## Étape 1 — Squelette projet (1j)

- CMake + structure miroir : `config.hpp`, `models/yolo.cpp`, `models/ocr.cpp`, `pipeline/{core,detect,kalman}.cpp`, `io/{reader,writer,viz}.cpp`
- Deps : OpenCV C++ (déjà dispo sur Jetson via JetPack), ONNX Runtime C++ API
- Charger le dict chars `en_dict.txt` à l'identique

## Étape 2 — Port module par module, valider contre oracle (4-6j)

Ordre conseillé :

1. `yolo.cpp` — preprocess (letterbox), session ORT, `parse_yolo` (NMS + masques seg). Partie la plus dure : décodage proto-masques fait en NumPy → refaire avec `cv::Mat`/Eigen
2. `detect.cpp` — `warp_plate` (`cv::getPerspectiveTransform`), `clean_plate` (masques L/D, regex 6 chars → `std::regex`)
3. `kalman.cpp` — filtre 16×8 sur quadrilatère : `cv::KalmanFilter` direct, quasi trivial
4. `ocr.cpp` — 3 variantes, garde la plus longue : preprocess + CTC decode
5. `core.cpp` — `PipelineState` struct, boucle, timings (`std::chrono`)
6. `io/` — `cv::VideoCapture` (gstreamer natif sur Jetson), writer, viz

Notes :
- `stabilize.py` : **ne pas porter** (déjà désactivé dans run_pipeline)
- `main.py` / `metrics.py` : porter plus tard, ou garder l'évaluation en Python

## Étape 3 — Jetson (2-3j)

- Build sur Jetson (aarch64), ORT avec TensorRT Execution Provider (déjà testé côté Python)
- Pipeline gstreamer caméra → décodage HW (`nvv4l2decoder`)
- FP16, mesurer avec le benchmark porté

## Étape 4 — Carte low-budget (dépend de la cible)

- Si pas de GPU NVIDIA (RPi, Rockchip, etc.) : TensorRT exclu → garder ORT CPU, ou réexporter vers le NPU vendeur (RKNN pour Rockchip, NCNN/TFLite sinon)
- Quantization INT8 probablement nécessaire
- **Le choix de la carte conditionne le backend → décider tôt**

## Pièges connus

- Reproduire exactement le preprocess Python (letterbox, normalisation, ordre BGR/RGB) — source n°1 d'écarts
- Anomalies à préserver telles quelles : `COLORS[0]` partout dans viz, % du tableau LaTeX qui ne somment pas à 100
- Legacy `inference_video_ocr.py` : ignorer, ce n'est pas la référence (stabilisation active, autre clean_plate)

## Estimation

~2 semaines jusqu'à Jetson fonctionnel. Étape 4 non chiffrée tant que la carte cible n'est pas choisie.
