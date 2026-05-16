import pyotp
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import require_tenant
from ..models import (
    Tenant, Parking, Device, WhitelistEntry, SubscriptionPlan, Subscription,
    PlanDuration, SubscriptionStatus, AccessLog, Alert, AccessResult,
)
from ..mqtt_publisher import publish_plate_add, publish_plate_remove, publish_whitelist_sync
from ..security import sanitize_string, validate_plate
from ..templates_env import templates
from .access import generate_totp_qr

router = APIRouter(prefix="/dashboard")


@router.get("", response_class=HTMLResponse)
def dashboard_home(request: Request, db: Session = Depends(get_db)):
    user = require_tenant(request)
    tenant = db.query(Tenant).filter(Tenant.id == user["tenant_id"]).first()
    if not tenant:
        return RedirectResponse(url="/login", status_code=303)
    parkings = db.query(Parking).filter(Parking.tenant_id == tenant.id).all()
    return templates.TemplateResponse(request, "dashboard/parkings.html", {
        "user": user, "tenant": tenant, "parkings": parkings,
        "csrf_token": request.cookies.get("csrf_token", ""),
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
        "csrf_token": request.cookies.get("csrf_token", ""),
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
        "csrf_token": request.cookies.get("csrf_token", ""),
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

    plate = sanitize_string(plate, max_length=20).upper().replace(" ", "-")
    label = sanitize_string(label, max_length=200)
    owner_name = sanitize_string(owner_name, max_length=200)

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


DURATION_LABELS = {
    PlanDuration.DAILY: "Journalier",
    PlanDuration.WEEKLY: "Hebdomadaire",
    PlanDuration.MONTHLY: "Mensuel",
    PlanDuration.QUARTERLY: "Trimestriel",
    PlanDuration.YEARLY: "Annuel",
}


@router.get("/parking/{parking_id}/plans", response_class=HTMLResponse)
def parking_plans(request: Request, parking_id: int, db: Session = Depends(get_db)):
    user = require_tenant(request)
    parking = db.query(Parking).filter(
        Parking.id == parking_id,
        Parking.tenant_id == user["tenant_id"],
    ).first()
    if not parking:
        return RedirectResponse(url="/dashboard", status_code=303)

    plans = db.query(SubscriptionPlan).filter(
        SubscriptionPlan.parking_id == parking_id,
    ).order_by(SubscriptionPlan.created_at.desc()).all()

    active_sub_counts = {}
    for plan in plans:
        count = db.query(Subscription).filter(
            Subscription.plan_id == plan.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        ).count()
        active_sub_counts[plan.id] = count

    return templates.TemplateResponse(request, "dashboard/plans.html", {
        "user": user, "parking": parking, "plans": plans,
        "duration_labels": DURATION_LABELS,
        "durations": list(PlanDuration),
        "active_sub_counts": active_sub_counts,
        "csrf_token": request.cookies.get("csrf_token", ""),
    })


@router.post("/parking/{parking_id}/plans/add")
def add_plan(request: Request, parking_id: int,
             name: str = Form(...), duration: str = Form(...),
             price: str = Form(...), auto_renew_allowed: bool = Form(False),
             db: Session = Depends(get_db)):
    user = require_tenant(request)
    parking = db.query(Parking).filter(
        Parking.id == parking_id,
        Parking.tenant_id == user["tenant_id"],
    ).first()
    if not parking:
        return RedirectResponse(url="/dashboard", status_code=303)

    name = sanitize_string(name, max_length=200)
    if not name:
        return RedirectResponse(url=f"/dashboard/parking/{parking_id}/plans", status_code=303)

    try:
        price_cents = int(float(price.replace(",", ".")) * 100)
    except (ValueError, TypeError):
        return RedirectResponse(url=f"/dashboard/parking/{parking_id}/plans", status_code=303)
    if price_cents <= 0:
        return RedirectResponse(url=f"/dashboard/parking/{parking_id}/plans", status_code=303)

    try:
        duration_enum = PlanDuration(duration)
    except ValueError:
        return RedirectResponse(url=f"/dashboard/parking/{parking_id}/plans", status_code=303)

    plan = SubscriptionPlan(
        parking_id=parking_id,
        name=name,
        duration=duration_enum,
        price_cents=price_cents,
        auto_renew_allowed=auto_renew_allowed,
    )
    db.add(plan)
    db.commit()
    return RedirectResponse(url=f"/dashboard/parking/{parking_id}/plans", status_code=303)


@router.post("/parking/{parking_id}/plans/{plan_id}/toggle")
def toggle_plan(request: Request, parking_id: int, plan_id: int,
                db: Session = Depends(get_db)):
    user = require_tenant(request)
    plan = db.query(SubscriptionPlan).filter(
        SubscriptionPlan.id == plan_id,
        SubscriptionPlan.parking_id == parking_id,
    ).first()
    if plan:
        parking = db.query(Parking).filter(
            Parking.id == parking_id,
            Parking.tenant_id == user["tenant_id"],
        ).first()
        if parking:
            plan.is_active = not plan.is_active
            db.commit()
    return RedirectResponse(url=f"/dashboard/parking/{parking_id}/plans", status_code=303)


@router.post("/parking/{parking_id}/plans/{plan_id}/delete")
def delete_plan(request: Request, parking_id: int, plan_id: int,
                db: Session = Depends(get_db)):
    user = require_tenant(request)
    plan = db.query(SubscriptionPlan).filter(
        SubscriptionPlan.id == plan_id,
        SubscriptionPlan.parking_id == parking_id,
    ).first()
    if plan:
        parking = db.query(Parking).filter(
            Parking.id == parking_id,
            Parking.tenant_id == user["tenant_id"],
        ).first()
        if parking:
            db.delete(plan)
            db.commit()
    return RedirectResponse(url=f"/dashboard/parking/{parking_id}/plans", status_code=303)


@router.get("/parking/{parking_id}/logs", response_class=HTMLResponse)
def parking_access_logs(request: Request, parking_id: int, db: Session = Depends(get_db)):
    user = require_tenant(request)
    parking = db.query(Parking).filter(
        Parking.id == parking_id,
        Parking.tenant_id == user["tenant_id"],
    ).first()
    if not parking:
        return RedirectResponse(url="/dashboard", status_code=303)

    device_ids = [d.id for d in parking.devices]
    logs = []
    if device_ids:
        logs = db.query(AccessLog).filter(
            AccessLog.device_id.in_(device_ids),
        ).order_by(AccessLog.created_at.desc()).limit(200).all()

    devices_map = {d.id: d for d in parking.devices}
    return templates.TemplateResponse(request, "dashboard/access_logs.html", {
        "user": user, "parking": parking, "logs": logs, "devices_map": devices_map,
    })


@router.get("/parking/{parking_id}/alerts", response_class=HTMLResponse)
def parking_alerts(request: Request, parking_id: int, db: Session = Depends(get_db)):
    user = require_tenant(request)
    parking = db.query(Parking).filter(
        Parking.id == parking_id,
        Parking.tenant_id == user["tenant_id"],
    ).first()
    if not parking:
        return RedirectResponse(url="/dashboard", status_code=303)

    alerts = db.query(Alert).filter(
        Alert.parking_id == parking_id,
    ).order_by(Alert.created_at.desc()).limit(100).all()

    devices_map = {d.id: d for d in parking.devices}
    return templates.TemplateResponse(request, "dashboard/alerts.html", {
        "user": user, "parking": parking, "alerts": alerts, "devices_map": devices_map,
        "csrf_token": request.cookies.get("csrf_token", ""),
    })


@router.post("/parking/{parking_id}/alerts/mark-read")
def mark_alerts_read(request: Request, parking_id: int, db: Session = Depends(get_db)):
    user = require_tenant(request)
    parking = db.query(Parking).filter(
        Parking.id == parking_id,
        Parking.tenant_id == user["tenant_id"],
    ).first()
    if not parking:
        return RedirectResponse(url="/dashboard", status_code=303)

    db.query(Alert).filter(
        Alert.parking_id == parking_id,
        Alert.is_read == False,
    ).update({"is_read": True})
    db.commit()
    return RedirectResponse(url=f"/dashboard/parking/{parking_id}/alerts", status_code=303)
