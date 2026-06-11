"""Annotation visuelle des frames : masques, polygones, boîtes et labels."""
from __future__ import annotations

import cv2
import numpy as np

from src.config import COLORS


def draw(frame, detections: list, frame_count: int):
    """Dessine les détections (masque translucide, polygone, boîte, score + texte)."""
    out = frame.copy()
    for det in detections:
        color = COLORS[0]
        x1, y1, x2, y2 = det["box"]
        label = f" {det['score']}  {det.get('text', '')}"

        # Masque translucide à l'intérieur de la boîte
        overlay = out.copy()
        overlay[y1:y2, x1:x2][det["mask"] == 1] = color
        out = cv2.addWeighted(out, 0.6, overlay, 0.4, 0)

        cv2.polylines(out, [np.array(det["polygon"], dtype=np.int32)],
                      isClosed=True, color=color, thickness=2)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        # Cartouche du label au-dessus de la boîte
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(out, (x1, y1 - th - 10), (x1 + tw, y1), color, -1)
        cv2.putText(out, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    cv2.putText(out, f"frame {frame_count}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    return out
