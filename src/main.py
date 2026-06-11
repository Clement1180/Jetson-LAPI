#!/usr/bin/env python3
"""Évaluation du pipeline LAPI sur un jeu d'images annotées.

Compare le texte détecté au ground truth, affiche les métriques
(plaques + caractères) et sauvegarde les images en erreur.
"""
from __future__ import annotations

import os
from time import time

import cv2

from src.config import YOLO_MODEL, OCR_MODEL, CHARS_PATH, PROVIDERS
from src.io.metrics import make_metrics_state, update_metrics, print_summary
from src.io.reader import frames_from_dataset
from src.io.viz import draw
from src.models.ocr import load_ocr
from src.models.yolo import load_yolo
from src.pipeline.benchmark import (
    make_pipeline_metrics, update_pipeline_metrics, print_pipeline_metrics,
)
from src.pipeline.core import make_initial_state, run_pipeline

_HERE = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR       = os.path.join(_HERE, "../exemples/inputs/testset/images")
ANNOTATIONS_PATH = os.path.join(_HERE, "../exemples/inputs/testset/annotations.json")
ERRORS_DIR       = os.path.join(_HERE, "../exemples/outputs/errors")


def _best_detection_text(detections: list, ground_truth: str) -> str:
    """Retourne le texte détecté le plus proche du ground truth ("" si aucun)."""
    texts = [d.get("text", "") for d in detections if d.get("text")]
    if not texts:
        return ""
    return max(texts, key=lambda t: sum(a == b for a, b in zip(t, ground_truth)))


def _save_error_image(frame, detections: list, frame_count: int,
                      gt: str, detected: str) -> None:
    """Sauvegarde l'image annotée d'une détection erronée pour analyse."""
    annotated = draw(frame, detections, frame_count)
    cv2.putText(annotated, f"GT={gt}  DET={detected}", (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    filename = f"{frame_count:05d}_gt{gt}_det{detected}.jpg"
    cv2.imwrite(os.path.join(ERRORS_DIR, filename), annotated)


def main() -> None:
    os.makedirs(ERRORS_DIR, exist_ok=True)

    yolo = load_yolo(YOLO_MODEL, PROVIDERS)
    ocr  = load_ocr(OCR_MODEL, CHARS_PATH, PROVIDERS)

    state     = make_initial_state()
    metrics   = make_metrics_state()
    benchmark = make_pipeline_metrics()

    frame_count = 0
    total_time  = 0
    for frame, ground_truth in frames_from_dataset(IMAGES_DIR, ANNOTATIONS_PATH):
        t0 = time()
        frame, detections, state, times = run_pipeline(frame, state, yolo, ocr)
        benchmark = update_pipeline_metrics(benchmark, times)
        elapsed = time() - t0
        frame_count += 1
        total_time  += elapsed

        gt   = ground_truth["plate_id"].upper().replace(" ", "")
        best = _best_detection_text(detections, gt)
        metrics = update_metrics(metrics, gt, best)

        # ── Affichage détaillé de chaque étape ──
        stab_ms = times["stabilization"] * 1000
        yolo_ms = times["yolo_inference"] * 1000
        kalk_ms = times["kalman_postproc"] * 1000
        ocr_ms  = times["ocr"] * 1000

        avg_fps = frame_count / total_time if total_time > 0 else 0
        status  = "✓" if best == gt else "✗"
        print(f"[{status}] {frame_count:3d} | Stab:{stab_ms:5.1f}ms | YOLO:{yolo_ms:5.1f}ms"
              f" | Kalm:{kalk_ms:5.1f}ms | OCR:{ocr_ms:5.1f}ms | Avg:{avg_fps:.1f}fps"
              f" | GT={gt} | DET={best}")

        if best != gt:
            _save_error_image(frame, detections, frame_count, gt, best)

    print("\n" + "=" * 60)
    print(f"Traitement terminé: {frame_count} images en {total_time:.1f}s")
    print(f"FPS moyen: {frame_count / total_time if total_time > 0 else 0:.1f} fps")
    print("=" * 60)
    print_summary(metrics)
    print_pipeline_metrics(benchmark)


if __name__ == "__main__":
    main()
