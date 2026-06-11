"""Pipeline LAPI : détection YOLO → lissage Kalman → OCR, avec chronométrage."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from time import time

import numpy as np

from ..config import SMOOTHING, OCR_FRAME_INTERVAL
from ..models.yolo import YoloModel, run_yolo, parse_yolo
from ..models.ocr import OcrModel, run_ocr
from .detect import extract_plate_crop, clean_plate
from .kalman import make_kalman_quad, kalman_update_quad


@dataclass
class PipelineState:
    """État persistant du pipeline entre deux frames."""
    # Stabilisation (voir stabilize.py — étape actuellement désactivée)
    prev_gray: np.ndarray = None
    trajectory: list = field(default_factory=list)
    smoothing: int = SMOOTHING
    # Suivi Kalman du quadrilatère de la plaque
    kalman: object = None          # KalmanFilter 16x8 (créé à la 1re détection)
    missed: int = 0                # frames consécutives sans détection
    max_missed: int = 10           # au-delà, le filtre est réinitialisé
    # Cadencement de l'OCR
    frame_count: int = 0
    last_ocr_text: str = ""        # dernier texte reconnu, réutilisé entre deux OCR


def make_initial_state() -> PipelineState:
    return PipelineState()


def _detect_plates(yolo: YoloModel, frame: np.ndarray) -> list:
    """Inférence YOLO + parsing des sorties brutes en détections."""
    outputs = run_yolo(yolo, frame)
    return parse_yolo(yolo, outputs, frame.shape[0], frame.shape[1])


def _smooth_with_kalman(detections: list, state: PipelineState) -> None:
    """Lisse le polygone de la première détection avec le filtre de Kalman.

    Sans détection, le filtre continue de prédire jusqu'à `max_missed` frames,
    puis est réinitialisé.
    """
    if detections:
        polygon = detections[0]["polygon"]
        if state.kalman is None:
            state.kalman = make_kalman_quad(polygon)
        state.kalman.predict()
        detections[0]["polygon"] = kalman_update_quad(state.kalman, polygon)
        state.missed = 0
    else:
        state.missed += 1
        if state.kalman is not None and state.missed <= state.max_missed:
            state.kalman.predict()
        else:
            state.kalman = None


def _read_plate_texts(frame: np.ndarray, detections: list, state: PipelineState,
                      ocr: OcrModel) -> None:
    """Renseigne det["text"] : OCR une frame sur OCR_FRAME_INTERVAL.

    Entre deux exécutions, le polygone lissé par Kalman suit la plaque et le
    dernier texte reconnu est réutilisé.
    """
    for det in detections:
        ocr_due = (state.frame_count % OCR_FRAME_INTERVAL == 0
                   or state.last_ocr_text == "")
        if ocr_due:
            plate = extract_plate_crop(frame, det)
            det["text"] = clean_plate(run_ocr(ocr, plate))
            state.last_ocr_text = det["text"]
        else:
            det["text"] = state.last_ocr_text


def run_pipeline(frame: np.ndarray, state: PipelineState,
                 yolo: YoloModel, ocr: OcrModel):
    """Lance le pipeline complet sur une frame, avec mesure du temps de chaque étape.

    Retourne : (frame, detections, new_state, times)
    `times` contient une entrée par étape (clés de benchmark.PIPELINE_STEPS).
    L'état passé en argument n'est pas modifié.
    """
    times = {}
    state = replace(state)          # copie : l'état de l'appelant reste intact
    state.frame_count += 1

    # ── 1. Stabilisation ──────────────────────────────────────────────────
    # Désactivée pour accélérer le traitement. Pour la réactiver :
    #   from .stabilize import stabilize
    #   frame, state = stabilize(frame, state)
    t0 = time()
    times["stabilization"] = time() - t0

    # ── 2. Détection YOLO ─────────────────────────────────────────────────
    t0 = time()
    detections = _detect_plates(yolo, frame)
    times["yolo_inference"] = time() - t0

    # ── 3. Lissage Kalman ─────────────────────────────────────────────────
    t0 = time()
    _smooth_with_kalman(detections, state)
    times["kalman_postproc"] = time() - t0

    # ── 4. OCR (cadencé) ──────────────────────────────────────────────────
    t0 = time()
    _read_plate_texts(frame, detections, state, ocr)
    times["ocr"] = time() - t0

    return frame, detections, state, times
