"""
Wrapper Python pour le pipeline C++/TensorRT.
Fallback automatique vers le pipeline Python ONNX si le module C++ n'est pas compilé.
"""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

log = logging.getLogger("lapi.pipeline_cpp")

try:
    import lapi_cpp
    HAS_CPP = True
    log.info("Module C++/TensorRT chargé")
except ImportError:
    HAS_CPP = False
    log.warning("Module C++ non disponible, fallback vers pipeline Python/ONNX")


@dataclass
class TrackResult:
    id: int
    vehicle_box: tuple
    velocity: tuple
    has_plate: bool
    plate_text: Optional[str]
    is_confirmed: bool


class CppPipeline:
    """Pipeline C++/TensorRT avec interface compatible Python."""

    def __init__(self, config: dict):
        if not HAS_CPP:
            raise RuntimeError(
                "Module lapi_cpp non disponible. "
                "Compilez avec: cd cpp && ./build.sh"
            )

        cfg = lapi_cpp.PipelineConfig()
        cfg.car_engine_path = config["models"]["car_engine"]
        cfg.plate_engine_path = config["models"]["plate_engine"]
        cfg.ocr_engine_path = config["models"]["ocr_engine"]
        cfg.ocr_dict_path = config["models"]["ocr_dict"]
        cfg.car_conf_thresh = config.get("car_conf_thresh", 0.5)
        cfg.car_iou_thresh = config.get("car_iou_thresh", 0.45)
        cfg.plate_conf_thresh = config.get("plate_conf_thresh", 0.4)

        self._pipeline = lapi_cpp.Pipeline()
        if not self._pipeline.init(cfg):
            raise RuntimeError("Échec d'initialisation du pipeline C++")

        log.info("Pipeline C++/TensorRT initialisé")

    def process_frame(self, frame: np.ndarray) -> List[TrackResult]:
        if frame.dtype != np.uint8:
            frame = frame.astype(np.uint8)
        if not frame.flags['C_CONTIGUOUS']:
            frame = np.ascontiguousarray(frame)

        tracks = self._pipeline.process_frame(frame)

        results = []
        for t in tracks:
            results.append(TrackResult(
                id=t.id,
                vehicle_box=(t.vehicle_box.x1, t.vehicle_box.y1,
                             t.vehicle_box.x2, t.vehicle_box.y2),
                velocity=(t.vx, t.vy),
                has_plate=t.has_plate,
                plate_text=t.plate_text if t.plate_text else None,
                is_confirmed=t.is_confirmed,
            ))

        return results

    @property
    def frame_count(self) -> int:
        return self._pipeline.frame_count()


def create_pipeline(config: dict):
    """
    Factory: retourne le pipeline C++ si disponible, sinon Python.
    """
    engines_config = config.get("engines", {})

    if HAS_CPP and engines_config.get("car_engine"):
        try:
            return CppPipeline({"models": engines_config, **config})
        except RuntimeError as e:
            log.warning(f"Pipeline C++ indisponible: {e}, fallback Python")

    # Fallback Python
    from .core import init_inference_engines
    from .pipeline import create_lapi_pipeline

    models = config["models"]
    run_car, run_plate, run_ocr = init_inference_engines(
        models["yolo_car"], models["yolo_plate"],
        models["ocr_model"], models["ocr_dict"]
    )
    python_pipeline = create_lapi_pipeline(run_car, run_plate, run_ocr)

    class PythonPipelineWrapper:
        def __init__(self):
            self._frame_count = 0

        def process_frame(self, frame):
            self._frame_count += 1
            snapshots = python_pipeline(frame)
            return [
                TrackResult(
                    id=s.id,
                    vehicle_box=s.vehicle_box,
                    velocity=s.vehicle_velocity,
                    has_plate=s.has_plate,
                    plate_text=s.plate_text,
                    is_confirmed=s.is_confirmed,
                )
                for s in snapshots
            ]

        @property
        def frame_count(self):
            return self._frame_count

    log.info("Pipeline Python/ONNX initialisé (fallback)")
    return PythonPipelineWrapper()
