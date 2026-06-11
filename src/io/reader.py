"""Sources de frames : vidéo, image, dataset annoté, caméra GStreamer (Jetson)."""
from __future__ import annotations

import json
import os

import cv2


def frames_from_dataset(images_dir: str, annotations_path: str):
    """Générateur qui yield (frame, ground_truth) pour chaque image annotée.

    ground_truth = {
        "image_name": "frame_07424.jpg",
        "polygon":    [[x, y], ...],
        "plate_id":   "K81VRC",
    }
    """
    with open(annotations_path, "r") as f:
        annotations = json.load(f)

    for ann in annotations:
        filename = os.path.basename(ann["image_name"])
        path = os.path.join(images_dir, filename)

        frame = cv2.imread(path)
        if frame is None:
            print(f"image manquante : {path}")
            continue

        yield frame, {
            "image_name": filename,
            "polygon":    ann["polygon"],
            "plate_id":   ann["plate_id"],
        }


def frames_from_image(path: str):
    """Yield une unique frame lue depuis un fichier image."""
    frame = cv2.imread(path)
    if frame is None:
        raise FileNotFoundError(f"Image introuvable : {path}")
    yield frame


def frames_from_video(path: str):
    """Générateur de frames depuis un fichier vidéo."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Vidéo introuvable : {path}")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        yield frame
    cap.release()


def frames_from_gstreamer(width: int = 1280, height: int = 720, fps: int = 30,
                          sensor_id: int = 0, flip: int = 0):
    """Générateur de frames depuis la caméra CSI d'un Jetson (via GStreamer)."""
    pipeline = (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, "
        f"format=NV12, framerate={fps}/1 ! "
        f"nvvidconv flip-method={flip} ! "
        f"video/x-raw, format=BGRx ! "
        f"videoconvert ! video/x-raw, format=BGR ! appsink"
    )
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        raise RuntimeError("GStreamer indisponible")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        yield frame
    cap.release()


def get_video_meta(path: str) -> dict:
    """Retourne les métadonnées (fps, dimensions, nb de frames) sans ouvrir le flux."""
    cap = cv2.VideoCapture(path)
    meta = {
        "fps":    int(cap.get(cv2.CAP_PROP_FPS)) or 30,
        "width":  int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "total":  int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    cap.release()
    return meta
