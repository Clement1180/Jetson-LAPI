"""Serveur web FastAPI : flux vidéo annoté (MJPEG) + API de gestion des plaques.

Endpoints :
    GET  /                   page HTML (template/index.html)
    GET  /video_feed         flux MJPEG annoté par le pipeline
    POST /set_roi            enregistre la zone d'intérêt
    GET  /get_current_plate  dernière plaque reconnue + statut
    POST /add_plate          ajoute une plaque à la liste blanche
    POST /remove_plate       retire une plaque de la liste blanche

Lancement : python server.py  (ou uvicorn server:app)
"""
import os
import sys

import cv2
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Ajout du chemin pour trouver les modules locaux
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.config import YOLO_MODEL, PROVIDERS, OCR_MODEL, CHARS_PATH  # noqa: E402
from src.models.ocr import load_ocr                                  # noqa: E402
from src.models.yolo import load_yolo                                 # noqa: E402
from src.pipeline.core import make_initial_state, run_pipeline        # noqa: E402

VIDEO_SOURCE = 0  # webcam ; remplacer par un chemin de fichier .mp4/.mkv si besoin

app = FastAPI()

# Le dossier "template" (singulier) est utilisé s'il existe, sinon "templates"
_TEMPLATES_DIR = "template" if os.path.isdir("template") else "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

try:
    os.makedirs("static", exist_ok=True)
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception:
    pass  # le serveur reste utilisable sans fichiers statiques

# ── État applicatif (partagé entre les requêtes) ──────────────────────────────
roi_points = []                                   # ROI envoyée par le client (réservé)
whitelist = ["AA-123-BB"]                         # plaques autorisées
current_plate = {"text": "Aucune", "image": None}  # dernière plaque reconnue

# ── Modèles YOLO et OCR ───────────────────────────────────────────────────────
try:
    yolo = load_yolo(YOLO_MODEL, PROVIDERS)
    ocr = load_ocr(OCR_MODEL, CHARS_PATH, PROVIDERS)
except Exception as e:
    print("Erreur au chargement des modèles :", e)
    yolo = None
    ocr = None


class RoiData(BaseModel):
    x: int
    y: int
    w: int
    h: int


class PlateData(BaseModel):
    plate: str


def _update_current_plate(detections: list) -> None:
    """Mémorise le texte de la première détection lue."""
    for det in detections:
        if det.get("text"):
            current_plate["text"] = det["text"]
            break


def generate_video_stream():
    """Générateur MJPEG : frames annotées par le pipeline, encodées en JPEG."""
    cap = cv2.VideoCapture(VIDEO_SOURCE)
    state = make_initial_state() if yolo else None

    while True:
        success, frame = cap.read()
        if not success:
            break

        if yolo and ocr:
            try:
                frame, detections, state, _ = run_pipeline(frame, state, yolo, ocr)
                _update_current_plate(detections)
            except Exception:
                # La frame brute est diffusée telle quelle ; le flux continue
                pass

        _, buffer = cv2.imencode(".jpg", frame)
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html",
                                      context={"whitelist": whitelist})


@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generate_video_stream(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/set_roi")
async def set_roi(roi: RoiData):
    global roi_points
    roi_points = [roi.x, roi.y, roi.w, roi.h]
    return {"status": "success"}


@app.get("/get_current_plate")
async def get_current_plate():
    status = "Autorisé" if current_plate["text"] in whitelist else "Inconnu"
    return {"plate": current_plate["text"], "status": status}


@app.post("/add_plate")
async def add_plate(data: PlateData):
    if data.plate not in whitelist:
        whitelist.append(data.plate)
    return {"whitelist": whitelist}


@app.post("/remove_plate")
async def remove_plate(data: PlateData):
    if data.plate in whitelist:
        whitelist.remove(data.plate)
    return {"whitelist": whitelist}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
