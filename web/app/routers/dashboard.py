import pyotp
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import require_tenant
from ..models import Tenant, Parking, Device, WhitelistEntry
from ..mqtt_publisher import publish_plate_add, publish_plate_remove, publish_whitelist_sync
from .access import generate_totp_qr

router = APIRouter(prefix="/dashboard")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def dashboard_home(request: Request, db: Session = Depends(get_db)):
    user = require_tenant(request)
    tenant = db.query(Tenant).filter(Tenant.id == user["tenant_id"]).first()
    if not tenant:
        return RedirectResponse(url="/login", status_code=303)
    parkings = db.query(Parking).filter(Parking.tenant_id == tenant.id).all()
    return templates.TemplateResponse(request, "dashboard/parkings.html", {
        "user": user, "tenant": tenant, "parkings": parkings,
    })


@router.get("/parking/{parking_id}", response_class=HTMLResponse)
def parking_detail(request: Request, parking_id: int, db: Session = Depends(get_db)):
    user = require_tenant(request)
    parking = db.query(Parking).filter(
        Parking.id == parking_id,
        Parking.tenant_id == user["tenant_id"]
    ).first()
    if not parking:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request, "dashboard/parking_detail.html", {
        "user": user, "parking": parking,
    })


@router.get("/device/{device_id}", response_class=HTMLResponse)
def device_whitelist(request: Request, device_id: int, db: Session = Depends(get_db)):
    user = require_tenant(request)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device or device.parking.tenant_id != user["tenant_id"]:
        return RedirectResponse(url="/dashboard", status_code=303)
    entries = db.query(WhitelistEntry).filter(
        WhitelistEntry.device_id == device_id
    ).order_by(WhitelistEntry.created_at.desc()).all()
    totp_qrs = {}
    if device.parking.require_totp:
        for e in entries:
            if e.totp_secret:
                totp_qrs[e.id] = generate_totp_qr(e, device.parking.name)
    return templates.TemplateResponse(request, "dashboard/device_whitelist.html", {
        "user": user, "device": device, "entries": entries, "totp_qrs": totp_qrs,
    })


@router.post("/device/{device_id}/whitelist/add")
def add_plate(request: Request, device_id: int,
              plate: str = Form(...), label: str = Form(""),
              owner_name: str = Form(""),
              db: Session = Depends(get_db)):
    user = require_tenant(request)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device or device.parking.tenant_id != user["tenant_id"]:
        return RedirectResponse(url="/dashboard", status_code=303)

    plate = plate.upper().strip()
    existing = db.query(WhitelistEntry).filter(
        WhitelistEntry.device_id == device_id,
        WhitelistEntry.plate == plate
    ).first()
    if not existing:
        totp_secret = ""
        if device.parking.require_totp and owner_name:
            totp_secret = pyotp.random_base32()
        entry = WhitelistEntry(
            device_id=device_id, plate=plate, label=label,
            owner_name=owner_name, totp_secret=totp_secret,
        )
        db.add(entry)
        db.commit()
        publish_plate_add(device.mqtt_client_id, plate, label)

    return RedirectResponse(url=f"/dashboard/device/{device_id}", status_code=303)


@router.post("/device/{device_id}/whitelist/{entry_id}/delete")
def remove_plate(request: Request, device_id: int, entry_id: int,
                 db: Session = Depends(get_db)):
    user = require_tenant(request)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device or device.parking.tenant_id != user["tenant_id"]:
        return RedirectResponse(url="/dashboard", status_code=303)

    entry = db.query(WhitelistEntry).filter(WhitelistEntry.id == entry_id).first()
    if entry:
        plate = entry.plate
        db.delete(entry)
        db.commit()
        publish_plate_remove(device.mqtt_client_id, plate)

    return RedirectResponse(url=f"/dashboard/device/{device_id}", status_code=303)


@router.post("/device/{device_id}/whitelist/sync")
def sync_whitelist(request: Request, device_id: int, db: Session = Depends(get_db)):
    user = require_tenant(request)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device or device.parking.tenant_id != user["tenant_id"]:
        return RedirectResponse(url="/dashboard", status_code=303)

    entries = db.query(WhitelistEntry).filter(WhitelistEntry.device_id == device_id).all()
    plates = [(e.plate, e.label) for e in entries]
    publish_whitelist_sync(device.mqtt_client_id, plates)

    return RedirectResponse(url=f"/dashboard/device/{device_id}", status_code=303)
