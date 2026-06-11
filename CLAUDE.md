# Jetson-LAPI — lecture de plaques (YOLO-seg → Kalman → OCR, ONNX Runtime)

Python 3.11, venv `.venv\Scripts\python.exe`. Branche `LAPI-IR`. Sur ce PC : CPU only (DLL CUDA/TensorRT absentes, fallback normal). Cible : Jetson (TensorRT) ou Docker (`ENV=docker`, chemins `/app`).

## Architecture (refactorisée 2026-06-10, vérifiée bit-identique sur 40 frames)
- `src/config.py` — chemins, CONF/IOU/SMOOTHING, `OCR_FRAME_INTERVAL=3`, sélection PROVIDERS
- `src/models/yolo.py` — dataclass `YoloModel`, `load_yolo(path, providers)`, `run_yolo(model, frame)`, `parse_yolo(model, outputs, h, w)`
- `src/models/ocr.py` — dataclass `OcrModel`, `load_ocr(path, chars_path, providers)`, `run_ocr(model, img)` (3 variantes, garde la + longue)
- `src/pipeline/core.py` — `PipelineState` (dataclass), `make_initial_state()`, `run_pipeline(frame, state, yolo, ocr) -> (frame, detections, new_state, times)`
- `src/pipeline/detect.py` — `warp_plate`, `extract_plate_crop`, `clean_plate` (masques L/D, 6 chars)
- `src/pipeline/kalman.py` — filtre 16×8 sur quadrilatère ; `stabilize.py` — stabilisation DÉSACTIVÉE dans run_pipeline (perf) ; `benchmark.py` — temps/étape + tableau LaTeX
- `src/io/` — `reader.py` (vidéo/dataset/gstreamer), `writer.py` (vidéo/affichage), `metrics.py` (TP/FP/FN plaques+chars), `viz.py` (draw)
- Détection = dict `{class, score, box, polygon(4pts), mask, text}` ; clés `times` : stabilization, yolo_inference, kalman_postproc, ocr

## Points d'entrée
- `python -m src.mainvideo` — vidéo annotée + benchmark ; `python -m src.main` — éval dataset annoté (attend `exemples/inputs/testset/`)
- `streamlit run app.py` — UI parking (whitelist, ROI, lit `rush_2.avi`)
- `python server.py` — FastAPI :8000, MJPEG webcam, templates dans `template/` (singulier)
- Poids : `src/models_weight/{best.onnx, ocr_model.onnx, en_dict.txt}`

## Port C++ (ROADMAP_CPP.md)
- Étape 0 faite : oracle `oracle/oracle_40frames.json` (généré par `python -m src.make_oracle`, déterministe, CPU) = référence bit-exacte pour le port
- Étapes 1-2 faites : port C++ complet dans `cpp/` (CMake, structure miroir, tous modules portés) — JAMAIS COMPILÉ (pas de toolchain C++ sur ce PC), build + validation = sur Jetson
- Validation : `lapi_oracle` dump JSON → `python tools/compare_oracle.py oracle/oracle_40frames.json cpp_oracle.json` (oracle = CPU, valider en CPU d'abord)
- Quirks portés exprès : NMSBoxes reçoit (x1,y1,x2,y2) interprété (x,y,w,h) ; Kalman = port manuel filterpy CV_64F forme de Joseph ; astype(int) = troncature vers zéro ; max(key=len) = premier ex æquo
- Étape suivante : étape 3, build sur Jetson (ORT aarch64 + TensorRT EP), gstreamer caméra, FP16

## En suspens / pièges
- `inference_video_ocr.py` = monolithe legacy (comportement différent : stabilisation active, autre clean_plate) — candidat à suppression, non refactorisé volontairement
- Doublons non référencés supprimables : `src/best.onnx`, `src/ocr_model.onnx`, `src/en_dict.txt` (copies de models_weight/)
- Anomalies préservées exprès (ne pas "corriger" sans demande) : % du tableau LaTeX ne somment pas à 100 ; `viz.draw` utilise toujours `COLORS[0]`
- `serveur.py` supprimé (doublon de server.py)
