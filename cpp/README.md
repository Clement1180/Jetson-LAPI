# LAPI C++ / TensorRT Pipeline

Port C++ du hot path de la pipeline de reconnaissance de plaques pour le Jetson.

## Architecture

```
Python (service.py)
    │
    ├── lapi_cpp (pybind11)  ← Pipeline C++ complète
    │       ├── YOLOCarDetector (TensorRT)
    │       ├── YOLOPlateDetector (TensorRT, pose model)
    │       ├── PPOCRRecognizer (TensorRT)
    │       ├── Tracker (Kalman 8D/4D + greedy association)
    │       └── CLAHE + perspective warp
    │
    └── Fallback Python/ONNX si C++ non compilé
```

## Prérequis

- Jetson JetPack 5.x ou 6.x (CUDA + TensorRT inclus)
- CMake >= 3.18
- pybind11 (`sudo apt install python3-pybind11 pybind11-dev`)

## Build

```bash
cd cpp
chmod +x build.sh convert_models.sh
./build.sh
```

## Conversion des modèles

```bash
# Convertir ONNX → TensorRT (FP16 par défaut)
./convert_models.sh /opt/lapi/models /opt/lapi/engines

# INT8 (nécessite données de calibration)
PRECISION=int8 ./convert_models.sh /opt/lapi/models /opt/lapi/engines
```

## Utilisation depuis Python

```python
import lapi_cpp
import numpy as np

config = lapi_cpp.PipelineConfig()
config.car_engine_path = "/opt/lapi/engines/yolov8s_car.engine"
config.plate_engine_path = "/opt/lapi/engines/yolov8s_plate.engine"
config.ocr_engine_path = "/opt/lapi/engines/ppocr_v4.engine"
config.ocr_dict_path = "/opt/lapi/models/en_dict.txt"

pipeline = lapi_cpp.Pipeline()
pipeline.init(config)

frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
tracks = pipeline.process_frame(frame)

for t in tracks:
    print(f"Track #{t.id}: plate={t.plate_text}, confirmed={t.is_confirmed}")
```

## Benchmark

```bash
python benchmark.py --image /path/to/test.jpg --iterations 100
```

## Performance attendue (Jetson Orin Nano)

| Pipeline | Latence/frame | FPS |
|----------|--------------|-----|
| Python/ONNX (CUDA EP) | ~80-120ms | 8-12 |
| C++/TensorRT FP16 | ~15-25ms | 40-65 |
| C++/TensorRT INT8 | ~8-15ms | 65-120 |
