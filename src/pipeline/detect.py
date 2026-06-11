"""Post-traitement des détections : redressement de la plaque et nettoyage du texte OCR."""
from __future__ import annotations

import re

import cv2
import numpy as np

# Longueur attendue d'une plaque et formats acceptés (L = lettre, D = chiffre)
PLATE_LENGTH = 6
PLATE_MASKS = [
    "LLLDDD",   # ABC123
    "DDDLLL",   # 123ABC
    "LDDLLL",   # A12BCD
    "LLLDDL",   # AAK70N
    "DDLLLL",   # 23AAGP
]


def order_points(pts) -> np.ndarray:
    """Ordonne 4 points en (haut-gauche, haut-droit, bas-droit, bas-gauche)."""
    pts = np.array(pts, dtype=np.float32)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).flatten()
    return np.array([pts[np.argmin(s)], pts[np.argmin(diff)],
                     pts[np.argmax(s)], pts[np.argmax(diff)]], dtype=np.float32)


def warp_plate(frame: np.ndarray, polygon, out_w: int = 200, out_h: int = 60):
    """Redresse la plaque par transformation perspective. None si polygone ≠ 4 points."""
    if len(polygon) != 4:
        return None
    src = order_points(polygon)
    dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
                   dtype=np.float32)
    return cv2.warpPerspective(frame, cv2.getPerspectiveTransform(src, dst),
                               (out_w, out_h), flags=cv2.INTER_CUBIC)


def extract_plate_crop(frame: np.ndarray, detection: dict):
    """Extrait l'image de la plaque : perspective si quadrilatère, sinon crop de la boîte."""
    polygon = detection["polygon"]
    if len(polygon) == 4:
        return warp_plate(frame, polygon)
    x1, y1, x2, y2 = detection["box"]
    return frame[y1:y2, x1:x2]


def apply_mask(text: str, mask: str) -> str:
    """Compare un texte à un format de plaque.

    text : "Y4555T"   (texte brut sans espaces)
    mask : "LDDLLL"   (L = lettre, D = chiffre)
    Retourne "Y4___T" — '_' aux positions où le caractère ne correspond pas
    au type attendu.
    """
    result = ""
    for char, expected in zip(text, mask):
        if expected == "L" and char.isalpha():
            result += char
        elif expected == "D" and char.isdigit():
            result += char
        else:
            result += "_"
    return result


def clean_plate(text: str) -> str:
    """Nettoie la sortie OCR brute et la projette sur le format de plaque le plus plausible.

    Retourne "" si moins de PLATE_LENGTH caractères alphanumériques, sinon le
    candidat masqué ayant le plus de caractères valides (ex. "Y45SST" ou "Y4___T").
    """
    text = re.sub(r"[^A-Z0-9]", "", text.upper())
    if len(text) < PLATE_LENGTH:
        return ""

    # Le texte ne contient plus que [A-Z0-9] : le candidat est la première
    # fenêtre de PLATE_LENGTH caractères, quel que soit le format testé.
    candidate = text[:PLATE_LENGTH]

    best = ""
    best_score = -1
    for mask in PLATE_MASKS:
        masked = apply_mask(candidate, mask)
        score = sum(1 for c in masked if c != "_")   # nb de caractères valides
        if score > best_score:
            best_score = score
            best = masked

    return best
