"""Sorties vidéo : écriture de fichiers et affichage à l'écran."""
from __future__ import annotations

import os

import cv2


# ── Vidéo ─────────────────────────────────────────────────────────────────────

def open_video_writer(path: str, fps: int, width: int, height: int) -> cv2.VideoWriter:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    handle = cv2.VideoWriter(path, fourcc, fps, (width, height))
    if not handle.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir le writer : {path}")
    return handle


def write_frame(handle: cv2.VideoWriter, frame) -> None:
    handle.write(frame)


def close_video_writer(handle: cv2.VideoWriter) -> None:
    handle.release()


# ── Affichage ─────────────────────────────────────────────────────────────────

def display(window: str, frame) -> bool:
    """Affiche la frame ; retourne False si l'utilisateur appuie sur 'q'."""
    cv2.imshow(window, frame)
    return (cv2.waitKey(1) & 0xFF) != ord("q")


def close_display() -> None:
    cv2.destroyAllWindows()
