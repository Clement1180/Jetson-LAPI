"""Détection de plaques : chargement et inférence du modèle YOLO-seg (ONNX)."""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

from ..config import LABELS, CONF, IOU


@dataclass(frozen=True)
class YoloModel:
    """Session ONNX YOLO et métadonnées d'entrée du réseau."""
    session: ort.InferenceSession
    input_name: str
    input_height: int
    input_width: int
    num_mask_coeffs: int = 32


def load_yolo(path: str, providers: list) -> YoloModel:
    """Charge le modèle YOLO depuis `path` avec les providers ONNX donnés."""
    session = ort.InferenceSession(path, providers=providers)
    model_input = session.get_inputs()[0]
    print(f"YOLO : {session.get_providers()}")
    return YoloModel(
        session=session,
        input_name=model_input.name,
        input_height=model_input.shape[2],
        input_width=model_input.shape[3],
    )


def run_yolo(model: YoloModel, frame: np.ndarray) -> list:
    """Prépare la frame (RGB, resize, normalisation NCHW) et lance l'inférence."""
    img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (model.input_width, model.input_height))
    tensor = (img / 255.0).transpose(2, 0, 1)[np.newaxis].astype(np.float32)
    return model.session.run(None, {model.input_name: tensor})


def _mask_to_polygon(crop: np.ndarray, blur_size: tuple):
    """Binarise le masque et l'approxime par un polygone convexe (≤ 4 points).

    Retourne (masque_binaire, polygone) ou (None, None) si aucun contour.
    """
    crop = cv2.blur(crop, blur_size)
    crop = (crop > 0.5).astype(np.uint8)

    contours, _ = cv2.findContours(crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None

    # Enveloppe convexe sur TOUS les contours (pas seulement le plus grand)
    all_points = np.vstack(contours)
    hull = cv2.convexHull(all_points)

    # Augmente epsilon jusqu'à obtenir au plus 4 sommets
    epsilon = 0.02 * cv2.arcLength(hull, True)
    while True:
        poly = cv2.approxPolyDP(hull, epsilon, True)
        if len(poly) <= 4:
            break
        epsilon *= 1.1

    return crop, poly


def _force_quadrilateral(poly: np.ndarray) -> np.ndarray:
    """Force le polygone à exactement 4 points (requis par le filtre de Kalman)."""
    if len(poly) < 4:
        # Complète avec la boîte englobante orientée
        rect = cv2.minAreaRect(poly.astype(np.int32))
        return cv2.boxPoints(rect)
    if len(poly) > 4:
        return poly[:4]
    return poly


def _extract_detections(boxes, scores, class_ids, mask_preds, proto, img_h, img_w) -> list:
    """Reconstruit les masques d'instance et en extrait box + polygone + masque."""
    num_m, mask_h, mask_w = proto.shape
    masks = (1 / (1 + np.exp(-(mask_preds @ proto.reshape(num_m, -1))))).reshape(-1, mask_h, mask_w)

    # Boîtes exprimées dans le repère (basse résolution) des masques
    boxes_mask = boxes.copy()
    boxes_mask[:, [0, 2]] *= mask_w / img_w
    boxes_mask[:, [1, 3]] *= mask_h / img_h
    blur_size = (int(img_w / mask_w), int(img_h / mask_h))

    detections = []
    for i in range(len(boxes)):
        x1, y1 = int(math.floor(boxes[i][0])), int(math.floor(boxes[i][1]))
        x2, y2 = int(math.ceil(boxes[i][2])), int(math.ceil(boxes[i][3]))
        mx1, my1 = int(math.floor(boxes_mask[i][0])), int(math.floor(boxes_mask[i][1]))
        mx2, my2 = int(math.ceil(boxes_mask[i][2])), int(math.ceil(boxes_mask[i][3]))

        crop = masks[i][my1:my2, mx1:mx2]
        if crop.size == 0:
            continue
        crop = cv2.resize(crop, (x2 - x1, y2 - y1), interpolation=cv2.INTER_CUBIC)

        crop, poly = _mask_to_polygon(crop, blur_size)
        if poly is None:
            continue

        poly = poly.reshape(-1, 2) + np.array([x1, y1])
        poly = _force_quadrilateral(poly)

        detections.append({
            "class":   LABELS[int(class_ids[i])],
            "score":   round(float(scores[i]), 3),
            "box":     [x1, y1, x2, y2],
            "polygon": poly.tolist(),
            "mask":    crop,
        })

    return detections


def parse_yolo(model: YoloModel, outputs: list, img_h: int, img_w: int) -> list:
    """Parse les sorties brutes YOLO-seg → liste de détections.

    Chaque détection : {"class", "score", "box", "polygon", "mask"}.
    """
    box_output, mask_output = outputs[0], outputs[1]
    num_classes = box_output.shape[1] - model.num_mask_coeffs - 4
    predictions = box_output[0].T

    # Filtrage par confiance
    scores = np.max(predictions[:, 4:4 + num_classes], axis=1)
    keep = scores > CONF
    predictions, scores = predictions[keep], scores[keep]
    if len(predictions) == 0:
        return []

    class_ids = np.argmax(predictions[:, 4:4 + num_classes], axis=1)
    mask_preds = predictions[:, 4 + num_classes:]

    # (cx, cy, w, h) réseau → (x1, y1, x2, y2) image
    cx, cy, w, h = predictions[:, 0], predictions[:, 1], predictions[:, 2], predictions[:, 3]
    sx, sy = img_w / model.input_width, img_h / model.input_height
    boxes = np.stack([
        np.clip((cx - w / 2) * sx, 0, img_w),
        np.clip((cy - h / 2) * sy, 0, img_h),
        np.clip((cx + w / 2) * sx, 0, img_w),
        np.clip((cy + h / 2) * sy, 0, img_h),
    ], axis=1)

    indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), CONF, IOU)
    if len(indices) == 0:
        return []
    indices = indices.flatten()

    return _extract_detections(
        boxes[indices], scores[indices],
        class_ids[indices], mask_preds[indices],
        mask_output[0], img_h, img_w,
    )
