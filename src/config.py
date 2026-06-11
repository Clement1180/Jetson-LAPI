"""Configuration centrale du projet : chemins, hyperparamètres et providers ONNX."""
import os

# ── Environnement ─────────────────────────────────────────────────────────────
# docker : docker run -e ENV=docker ...
# local  : python directement sur Jetson ou env conda
_ENV = os.getenv("ENV", "local")

# ── Chemins ───────────────────────────────────────────────────────────────────
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SRC_DIR)

if _ENV == "docker":
    YOLO_MODEL   = "/app/src/models_weight/best.onnx"
    OCR_MODEL    = "/app/src/models_weight/ocr_model.onnx"
    CHARS_PATH   = "/app/src/models_weight/en_dict.txt"
    INPUT_VIDEO  = "/app/exemples/inputs/rush_2.avi"
    OUTPUT_VIDEO = "/app/exemples/outputs/rush_2.avi"
else:
    YOLO_MODEL   = os.path.join(_SRC_DIR, "models_weight", "best.onnx")
    OCR_MODEL    = os.path.join(_SRC_DIR, "models_weight", "ocr_model.onnx")
    CHARS_PATH   = os.path.join(_SRC_DIR, "models_weight", "en_dict.txt")
    INPUT_VIDEO  = os.path.join(_PROJECT_ROOT, "exemples", "inputs", "rush_2.avi")
    OUTPUT_VIDEO = os.path.join(_PROJECT_ROOT, "exemples", "outputs", "rush_2.avi")

# ── Inférence ─────────────────────────────────────────────────────────────────
CONF      = 0.5      # seuil de confiance YOLO
IOU       = 0.5      # seuil IoU pour la NMS
SMOOTHING = 100      # fenêtre de lissage de la stabilisation vidéo
LABELS    = ["day", "night"]
COLORS    = [(0, 255, 0), (0, 0, 255)]

# L'OCR n'est exécuté qu'une frame sur N ; entre deux exécutions, le filtre de
# Kalman suit la plaque et le dernier texte reconnu est conservé.
OCR_FRAME_INTERVAL = 3


def _select_providers() -> list:
    """Choisit les providers ONNX Runtime par ordre de préférence.

    Sur Jetson : TensorRT (le plus rapide), puis CUDA, puis CPU en dernier
    recours. Si onnxruntime n'est pas interrogeable, on retombe sur la liste
    CUDA + CPU (onnxruntime ignore silencieusement les providers absents).
    """
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        if "TensorrtExecutionProvider" in available:
            return ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
        if "CUDAExecutionProvider" in available:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]
    except Exception:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]


PROVIDERS = _select_providers()
