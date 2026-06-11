"""Lecture de plaques : chargement et inférence du modèle OCR (CRNN/CTC, ONNX)."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

# Dimensions d'entrée du réseau OCR (C, H, W)
OCR_INPUT_CHANNELS = 3
OCR_INPUT_HEIGHT = 48
OCR_INPUT_WIDTH = 320

# Noyau de netteté appliqué à l'une des variantes de prétraitement
_SHARPEN_KERNEL = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])


@dataclass(frozen=True)
class OcrModel:
    """Session ONNX OCR et table de caractères (index 0 = blank CTC)."""
    session: ort.InferenceSession
    input_name: str
    chars: list


def load_ocr(path: str, chars_path: str, providers: list) -> OcrModel:
    """Charge le modèle OCR et son dictionnaire de caractères."""
    session = ort.InferenceSession(path, providers=providers)
    with open(chars_path, "r", encoding="utf-8") as f:
        chars = [""] + [c.strip() for c in f.readlines() if c.strip()]
    print(f"OCR  : {session.get_providers()}, {len(chars)} chars")
    return OcrModel(
        session=session,
        input_name=session.get_inputs()[0].name,
        chars=chars,
    )


def apply_clahe(img: np.ndarray) -> np.ndarray:
    """Égalisation adaptative du contraste (CLAHE) sur le canal de luminance."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    lab = cv2.merge((cv2.createCLAHE(3.0, (8, 8)).apply(l), a, b))
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def decode_ocr(preds: np.ndarray, chars: list) -> str:
    """Décodage CTC greedy : supprime les blanks et les répétitions consécutives."""
    idx = preds.argmax(axis=2)[0]
    text = ""
    for i in range(len(idx)):
        c = idx[i]
        if c != 0 and (i == 0 or c != idx[i - 1]) and c < len(chars):
            text += chars[c]
    return text


def _to_input_tensor(img: np.ndarray, resized_w: int) -> np.ndarray:
    """CLAHE + RGB + resize + normalisation [-1, 1], complété à droite par des zéros."""
    img = cv2.cvtColor(apply_clahe(img), cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (resized_w, OCR_INPUT_HEIGHT))
    img = (img.astype("float32") / 255.0 - 0.5) / 0.5
    tensor = np.zeros((OCR_INPUT_CHANNELS, OCR_INPUT_HEIGHT, OCR_INPUT_WIDTH), dtype=np.float32)
    tensor[:, :, 0:resized_w] = img.transpose((2, 0, 1))
    return tensor


def run_ocr(model: OcrModel, plate_img: np.ndarray) -> str:
    """Lit le texte d'une image de plaque.

    Trois variantes (originale, inversée, accentuée) sont testées et le
    résultat le plus long est conservé.
    """
    if plate_img is None or plate_img.size == 0:
        return ""

    h, w = plate_img.shape[:2]
    resized_w = min(int(OCR_INPUT_HEIGHT * w / float(h)), OCR_INPUT_WIDTH)

    variants = [
        plate_img,
        cv2.bitwise_not(plate_img),
        cv2.filter2D(plate_img, -1, _SHARPEN_KERNEL),
    ]

    results = []
    for variant in variants:
        tensor = _to_input_tensor(variant, resized_w)
        preds = model.session.run(None, {model.input_name: tensor[np.newaxis]})[0]
        results.append(decode_ocr(preds, model.chars))

    return max(results, key=len)
