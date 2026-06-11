"""Génère l'oracle de validation pour le port C++.

Lance le pipeline sur les N premières frames de la vidéo et sauve les sorties
bit-exactes (boxes, polygones, scores, textes OCR, hash des masques) en JSON.
Le port C++ devra reproduire ces valeurs à l'identique (cf. ROADMAP_CPP.md).

Usage : python -m src.make_oracle [--video PATH] [--frames N] [--out PATH]
"""
import argparse
import hashlib
import json
import os

import cv2

from . import config
from .models.yolo import load_yolo
from .models.ocr import load_ocr
from .pipeline.core import make_initial_state, run_pipeline

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_video() -> str:
    if os.path.exists(config.INPUT_VIDEO):
        return config.INPUT_VIDEO
    return os.path.join(_PROJECT_ROOT, "rush_2.avi")


def _serialize_detection(det: dict) -> dict:
    mask = det.get("mask")
    return {
        "class": str(det["class"]),
        "score": float(det["score"]),
        "box": [int(v) for v in det["box"]],
        "polygon": [[float(x), float(y)] for x, y in det["polygon"]],
        "text": det.get("text", ""),
        "mask_shape": list(mask.shape) if mask is not None else None,
        "mask_sha256": hashlib.sha256(mask.tobytes()).hexdigest() if mask is not None else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", default=_default_video())
    parser.add_argument("--frames", type=int, default=40)
    parser.add_argument("--out", default=os.path.join(_PROJECT_ROOT, "oracle", "oracle_40frames.json"))
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"Impossible d'ouvrir la vidéo : {args.video}")

    yolo = load_yolo(config.YOLO_MODEL, config.PROVIDERS)
    ocr = load_ocr(config.OCR_MODEL, config.CHARS_PATH, config.PROVIDERS)
    state = make_initial_state()

    frames = []
    for i in range(args.frames):
        ok, frame = cap.read()
        if not ok:
            print(f"Vidéo épuisée à la frame {i}")
            break
        _, detections, state, _ = run_pipeline(frame, state, yolo, ocr)
        frames.append({
            "frame": i,
            "detections": [_serialize_detection(d) for d in detections],
        })
    cap.release()

    oracle = {
        "video": os.path.basename(args.video),
        "n_frames": len(frames),
        "conf": config.CONF,
        "iou": config.IOU,
        "ocr_frame_interval": config.OCR_FRAME_INTERVAL,
        "providers": yolo.session.get_providers(),
        "frames": frames,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(oracle, f, indent=1)

    n_det = sum(len(fr["detections"]) for fr in frames)
    print(f"Oracle écrit : {args.out} ({len(frames)} frames, {n_det} détections)")


if __name__ == "__main__":
    main()
