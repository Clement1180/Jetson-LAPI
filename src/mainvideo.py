#!/usr/bin/env python3
"""Traitement d'un fichier vidéo par le pipeline LAPI.

Écrit la vidéo annotée en sortie et affiche les temps de chaque étape.
"""
from __future__ import annotations

import os
from time import time

from src.config import YOLO_MODEL, OCR_MODEL, CHARS_PATH, PROVIDERS, OUTPUT_VIDEO
from src.io.reader import frames_from_video, get_video_meta
from src.io.viz import draw
from src.io.writer import open_video_writer, write_frame, close_video_writer
from src.models.ocr import load_ocr
from src.models.yolo import load_yolo
from src.pipeline.benchmark import (
    make_pipeline_metrics, update_pipeline_metrics, print_pipeline_metrics,
)
from src.pipeline.core import make_initial_state, run_pipeline

_HERE        = os.path.dirname(os.path.abspath(__file__))
VIDEO_INPUT  = os.path.join(_HERE, "../exemples/inputs/rush_2.avi")
VIDEO_OUTPUT = os.path.join(_HERE, OUTPUT_VIDEO)


def main() -> None:
    # ── Modèles ───────────────────────────────────────────────────────────
    yolo      = load_yolo(YOLO_MODEL, PROVIDERS)
    ocr       = load_ocr(OCR_MODEL, CHARS_PATH, PROVIDERS)
    state     = make_initial_state()
    benchmark = make_pipeline_metrics()

    # ── Source + writer ───────────────────────────────────────────────────
    meta   = get_video_meta(VIDEO_INPUT)
    writer = open_video_writer(VIDEO_OUTPUT, meta["fps"], meta["width"], meta["height"])

    # ── Boucle vidéo ──────────────────────────────────────────────────────
    frame_count  = 0
    total_frames = meta["total"]
    total_time   = 0

    for frame in frames_from_video(VIDEO_INPUT):
        t0 = time()
        frame, detections, state, times = run_pipeline(frame, state, yolo, ocr)
        benchmark = update_pipeline_metrics(benchmark, times)
        elapsed = time() - t0
        frame_count += 1
        total_time  += elapsed

        write_frame(writer, draw(frame, detections, frame_count))
        texts = [d.get("text", "") for d in detections if d.get("text")]

        # ── Affichage détaillé de chaque étape ──
        stab_ms = times["stabilization"] * 1000
        yolo_ms = times["yolo_inference"] * 1000
        kalk_ms = times["kalman_postproc"] * 1000
        ocr_ms  = times["ocr"] * 1000

        avg_fps = frame_count / total_time if total_time > 0 else 0
        print(f"[{frame_count:3d}/{total_frames}] {elapsed:.3f}s | Stab:{stab_ms:5.1f}ms"
              f" | YOLO:{yolo_ms:5.1f}ms | Kalm:{kalk_ms:5.1f}ms | OCR:{ocr_ms:5.1f}ms"
              f" | Avg:{avg_fps:.1f}fps | {texts}")

    close_video_writer(writer)
    avg_fps = frame_count / total_time if total_time > 0 else 0
    print(f"\n Terminé! {frame_count} frames en {total_time:.1f}s → {VIDEO_OUTPUT}")
    print(f" FPS moyen: {avg_fps:.1f} fps")
    print_pipeline_metrics(benchmark)


if __name__ == "__main__":
    main()
