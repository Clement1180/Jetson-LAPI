"""Stabilisation vidéo par flux optique (lissage de trajectoire).

NOTE : cette étape est actuellement désactivée dans `core.run_pipeline` pour
accélérer le traitement sur Jetson. Elle est conservée ici, prête à être
réactivée (voir le commentaire dans `run_pipeline`).
"""
from __future__ import annotations

import cv2
import numpy as np


def _estimate_transform(prev_gray: np.ndarray, curr_gray: np.ndarray) -> np.ndarray:
    """Estime la transformation affine partielle entre deux frames grises.

    Retourne l'identité si le suivi de points échoue.
    """
    pts = cv2.goodFeaturesToTrack(prev_gray, maxCorners=200, qualityLevel=0.01, minDistance=30)
    if pts is None:
        return np.eye(2, 3, dtype=np.float32)
    curr_pts, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, pts, None)
    good_prev = pts[status == 1]
    good_curr = curr_pts[status == 1]
    if len(good_prev) < 4:
        return np.eye(2, 3, dtype=np.float32)
    m, _ = cv2.estimateAffinePartial2D(good_prev, good_curr)
    return m if m is not None else np.eye(2, 3, dtype=np.float32)


def stabilize(frame: np.ndarray, state):
    """Stabilise une frame : (frame, state) → (frame_stabilisée, state mis à jour).

    `state` est le PipelineState du pipeline ; ses champs `prev_gray`,
    `trajectory` et `smoothing` sont utilisés. La frame est recadrée de 5 %
    sur chaque bord puis redimensionnée pour masquer les bords introduits
    par la compensation de mouvement.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    if state.prev_gray is None:
        state.prev_gray = gray
        state.trajectory = [np.zeros(3)]
        return frame, state

    m = _estimate_transform(state.prev_gray, gray)
    state.trajectory = state.trajectory + [
        np.array([m[0, 2], m[1, 2], np.arctan2(m[1, 0], m[0, 0])])
    ]
    state.prev_gray = gray

    # Trajectoire lissée = moyenne glissante sur la demi-fenêtre de lissage
    n = len(state.trajectory)
    smooth = np.array(state.trajectory[max(0, n - state.smoothing // 2):n]).mean(axis=0)
    diff = smooth - state.trajectory[-1]

    h, w = frame.shape[:2]
    fix = np.array([[np.cos(diff[2]), -np.sin(diff[2]), diff[0]],
                    [np.sin(diff[2]),  np.cos(diff[2]), diff[1]]], dtype=np.float32)
    out = cv2.warpAffine(frame, fix, (w, h), borderMode=cv2.BORDER_REFLECT)
    crop_x, crop_y = int(w * 0.05), int(h * 0.05)

    return cv2.resize(out[crop_y:h - crop_y, crop_x:w - crop_x], (w, h)), state
