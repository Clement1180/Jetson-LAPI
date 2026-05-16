import io
import base64
import time

import pyotp
import qrcode
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Parking, Device, WhitelistEntry
from ..mqtt_publisher import publish_plate_add
from ..security import sanitize_string

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

ACCESS_COOLDOWN = {}
COOLDOWN_SECONDS = 30
MAX_ATTEMPTS = 5
ATTEMPT_WINDOW = 300
ATTEMPT_LOG = {}


def _rate_limited(ip: str) -> bool:
    now = time.time()
    entries = ATTEMPT_LOG.get(ip, [])
    entries = [t for t in entries if now - t < ATTEMPT_WINDOW]
    ATTEMPT_LOG[ip] = entries
    return len(entries) >= MAX_ATTEMPTS


def _log_attempt(ip: str):
    ATTEMPT_LOG.setdefault(ip, []).append(time.time())


@router.get("/access/{parking_id}", response_class=HTMLResponse)
def access_page(request: Request, parking_id: int, db: Session = Depends(get_db)):
    parking = db.query(Parking).filter(Parking.id == parking_id).first()
    if not parking:
        return templates.TemplateResponse(request, "access/form.html", {
            "parking": None, "error": None, "success": False,
            "csrf_token": request.cookies.get("csrf_token", ""),
        })
    return templates.TemplateResponse(request, "access/form.html", {
        "parking": parking, "error": None, "success": False,
        "csrf_token": request.cookies.get("csrf_token", ""),
    })


@router.post("/access/{parking_id}", response_class=HTMLResponse)
def access_submit(request: Request, parking_id: int,
                  plate: str = Form(...), owner_name: str = Form(...),
                  totp_code: str = Form(""),
                  db: Session = Depends(get_db)):
    parking = db.query(Parking).filter(Parking.id == parking_id).first()
    if not parking:
        return templates.TemplateResponse(request, "access/form.html", {
            "parking": None, "error": None, "success": False,
            "csrf_token": request.cookies.get("csrf_token", ""),
        })

    ip = request.client.host
    if _rate_limited(ip):
        return templates.TemplateResponse(request, "access/form.html", {
            "parking": parking, "error": "Trop de tentatives. Reessayez dans quelques minutes.",
            "success": False, "csrf_token": request.cookies.get("csrf_token", ""),
        })

    plate = sanitize_string(plate, max_length=20).upper().replace(" ", "-")
    owner_name = sanitize_string(owner_name, max_length=200)
    totp_code = sanitize_string(totp_code, max_length=10)

    entry = db.query(WhitelistEntry).join(Device).filter(
        Device.parking_id == parking_id,
        WhitelistEntry.plate == plate,
    ).first()

    if not entry or not entry.owner_name:
        _log_attempt(ip)
        return templates.TemplateResponse(request, "access/form.html", {
            "parking": parking, "error": "Plaque non reconnue ou nom incorrect.",
            "success": False, "csrf_token": request.cookies.get("csrf_token", ""),
        })

    if entry.owner_name.lower() != owner_name.lower():
        _log_attempt(ip)
        return templates.TemplateResponse(request, "access/form.html", {
            "parking": parking, "error": "Plaque non reconnue ou nom incorrect.",
            "success": False, "csrf_token": request.cookies.get("csrf_token", ""),
        })

    if parking.require_totp:
        if not entry.totp_secret:
            _log_attempt(ip)
            return templates.TemplateResponse(request, "access/form.html", {
                "parking": parking,
                "error": "TOTP non configure pour cette plaque. Contactez votre gestionnaire.",
                "success": False, "csrf_token": request.cookies.get("csrf_token", ""),
            })
        totp = pyotp.TOTP(entry.totp_secret)
        if not totp.verify(totp_code, valid_window=1):
            _log_attempt(ip)
            return templates.TemplateResponse(request, "access/form.html", {
                "parking": parking, "error": "Code de verification incorrect.",
                "success": False, "csrf_token": request.cookies.get("csrf_token", ""),
            })

    cooldown_key = f"{parking_id}:{plate}"
    now = time.time()
    if cooldown_key in ACCESS_COOLDOWN and now - ACCESS_COOLDOWN[cooldown_key] < COOLDOWN_SECONDS:
        return templates.TemplateResponse(request, "access/form.html", {
            "parking": parking, "error": None, "success": True,
            "csrf_token": request.cookies.get("csrf_token", ""),
        })
    ACCESS_COOLDOWN[cooldown_key] = now

    for device in parking.devices:
        from ..mqtt_publisher import _publish_topic
        _publish_topic(f"lapi/{device.mqtt_client_id}/access/open", {
            "plate": plate, "source": "qr_fallback",
        })

    return templates.TemplateResponse(request, "access/form.html", {
        "parking": parking, "error": None, "success": True,
        "csrf_token": request.cookies.get("csrf_token", ""),
    })


def generate_totp_qr(entry: WhitelistEntry, parking_name: str) -> str:
    if not entry.totp_secret:
        return ""
    totp = pyotp.TOTP(entry.totp_secret)
    uri = totp.provisioning_uri(name=entry.plate, issuer_name=f"LAPI - {parking_name}")
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
