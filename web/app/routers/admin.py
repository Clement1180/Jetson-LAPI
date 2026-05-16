import hashlib
import os

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import OTA_STORAGE_DIR, WEB_BASE_URL
from ..database import get_db
from ..auth import require_admin, hash_password
from ..models import Tenant, TenantUser, Parking, Device, WhitelistEntry
from ..mqtt_publisher import publish_ota_update
from ..security import sanitize_string, validate_email, validate_password_strength

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def admin_home(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request)
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return templates.TemplateResponse(request, "admin/tenants.html", {
        "user": user, "tenants": tenants,
        "csrf_token": request.cookies.get("csrf_token", ""),
    })


# --- TENANTS ---

@router.post("/tenants/create")
def create_tenant(request: Request, name: str = Form(...),
                  contact_email: str = Form(""), db: Session = Depends(get_db)):
    require_admin(request)
    name = sanitize_string(name, max_length=200)
    contact_email = sanitize_string(contact_email, max_length=254)
    if not name:
        return RedirectResponse(url="/admin", status_code=303)
    if contact_email:
        err = validate_email(contact_email)
        if err:
            return RedirectResponse(url="/admin", status_code=303)
    tenant = Tenant(name=name, contact_email=contact_email)
    db.add(tenant)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/tenants/{tenant_id}", response_class=HTMLResponse)
def tenant_detail(request: Request, tenant_id: int, db: Session = Depends(get_db)):
    user = require_admin(request)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(request, "admin/tenant_detail.html", {
        "user": user, "tenant": tenant,
        "csrf_token": request.cookies.get("csrf_token", ""),
    })


@router.post("/tenants/{tenant_id}/delete")
def delete_tenant(request: Request, tenant_id: int, db: Session = Depends(get_db)):
    require_admin(request)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant:
        db.delete(tenant)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/tenants/{tenant_id}/toggle")
def toggle_tenant(request: Request, tenant_id: int, db: Session = Depends(get_db)):
    require_admin(request)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant:
        tenant.is_active = not tenant.is_active
        db.commit()
    return RedirectResponse(url=f"/admin/tenants/{tenant_id}", status_code=303)


# --- USERS ---

@router.post("/tenants/{tenant_id}/users/create")
def create_user(request: Request, tenant_id: int,
                username: str = Form(...), password: str = Form(...),
                db: Session = Depends(get_db)):
    require_admin(request)
    username = sanitize_string(username, max_length=150)
    if not username:
        return RedirectResponse(url=f"/admin/tenants/{tenant_id}", status_code=303)
    pw_error = validate_password_strength(password)
    if pw_error:
        user = require_admin(request)
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        return templates.TemplateResponse(request, "admin/tenant_detail.html", {
            "user": user, "tenant": tenant,
            "csrf_token": request.cookies.get("csrf_token", ""),
            "user_error_msg": pw_error,
        })
    existing = db.query(TenantUser).filter(TenantUser.username == username).first()
    if existing:
        return RedirectResponse(url=f"/admin/tenants/{tenant_id}", status_code=303)
    user = TenantUser(
        tenant_id=tenant_id,
        username=username,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    return RedirectResponse(url=f"/admin/tenants/{tenant_id}", status_code=303)


@router.post("/tenants/{tenant_id}/users/{user_id}/delete")
def delete_user(request: Request, tenant_id: int, user_id: int,
                db: Session = Depends(get_db)):
    require_admin(request)
    user = db.query(TenantUser).filter(TenantUser.id == user_id).first()
    if user:
        db.delete(user)
        db.commit()
    return RedirectResponse(url=f"/admin/tenants/{tenant_id}", status_code=303)


# --- PARKINGS ---

@router.post("/tenants/{tenant_id}/parkings/create")
def create_parking(request: Request, tenant_id: int,
                   name: str = Form(...), address: str = Form(""),
                   require_totp: str = Form(""),
                   db: Session = Depends(get_db)):
    require_admin(request)
    name = sanitize_string(name, max_length=200)
    address = sanitize_string(address, max_length=500)
    if not name:
        return RedirectResponse(url=f"/admin/tenants/{tenant_id}", status_code=303)
    parking = Parking(tenant_id=tenant_id, name=name, address=address,
                      require_totp=bool(require_totp))
    db.add(parking)
    db.commit()
    return RedirectResponse(url=f"/admin/tenants/{tenant_id}", status_code=303)


@router.post("/tenants/{tenant_id}/parkings/{parking_id}/delete")
def delete_parking(request: Request, tenant_id: int, parking_id: int,
                   db: Session = Depends(get_db)):
    require_admin(request)
    parking = db.query(Parking).filter(Parking.id == parking_id).first()
    if parking:
        db.delete(parking)
        db.commit()
    return RedirectResponse(url=f"/admin/tenants/{tenant_id}", status_code=303)


# --- DEVICES ---

@router.post("/parkings/{parking_id}/devices/create")
def create_device(request: Request, parking_id: int,
                  serial_number: str = Form(...), name: str = Form(""),
                  mqtt_client_id: str = Form(...),
                  db: Session = Depends(get_db)):
    user = require_admin(request)
    serial_number = sanitize_string(serial_number, max_length=100)
    name = sanitize_string(name, max_length=200)
    mqtt_client_id = sanitize_string(mqtt_client_id, max_length=100)
    if not serial_number or not mqtt_client_id:
        return RedirectResponse(url="/admin", status_code=303)
    parking = db.query(Parking).filter(Parking.id == parking_id).first()
    if not parking:
        return RedirectResponse(url="/admin", status_code=303)
    dup_sn = db.query(Device).filter(Device.serial_number == serial_number).first()
    dup_mqtt = db.query(Device).filter(Device.mqtt_client_id == mqtt_client_id).first()
    if dup_sn or dup_mqtt:
        field = "N/S" if dup_sn else "MQTT Client ID"
        tenant = db.query(Tenant).filter(Tenant.id == parking.tenant_id).first()
        return templates.TemplateResponse(request, "admin/tenant_detail.html", {
            "user": user, "tenant": tenant,
            "csrf_token": request.cookies.get("csrf_token", ""),
            "device_error_parking": parking.id,
            "device_error_msg": f"Le {field} est deja utilise par un autre dispositif.",
        })
    device = Device(
        parking_id=parking_id,
        serial_number=serial_number,
        name=name or serial_number,
        mqtt_client_id=mqtt_client_id,
    )
    db.add(device)
    db.commit()
    return RedirectResponse(url=f"/admin/tenants/{parking.tenant_id}", status_code=303)


@router.post("/devices/{device_id}/delete")
def delete_device(request: Request, device_id: int, db: Session = Depends(get_db)):
    require_admin(request)
    device = db.query(Device).filter(Device.id == device_id).first()
    if device:
        tenant_id = device.parking.tenant_id
        db.delete(device)
        db.commit()
        return RedirectResponse(url=f"/admin/tenants/{tenant_id}", status_code=303)
    return RedirectResponse(url="/admin", status_code=303)


# --- OTA ---

@router.get("/ota", response_class=HTMLResponse)
def ota_page(request: Request):
    user = require_admin(request)
    packages = []
    if os.path.isdir(OTA_STORAGE_DIR):
        for f in sorted(os.listdir(OTA_STORAGE_DIR), reverse=True):
            if f.endswith((".tar.gz", ".tgz")):
                path = os.path.join(OTA_STORAGE_DIR, f)
                size_mb = os.path.getsize(path) / (1024 * 1024)
                packages.append({"filename": f, "size_mb": round(size_mb, 2)})
    return templates.TemplateResponse(request, "admin/ota.html", {
        "user": user, "packages": packages,
        "csrf_token": request.cookies.get("csrf_token", ""),
    })


@router.post("/ota/upload")
async def upload_ota(request: Request, version: str = Form(...),
                     package: UploadFile = File(...)):
    require_admin(request)
    version = sanitize_string(version, max_length=50)
    if not version or not version.replace(".", "").replace("-", "").replace("_", "").isalnum():
        return RedirectResponse(url="/admin/ota", status_code=303)
    filename = f"lapi-{version}.tar.gz"
    filepath = os.path.join(OTA_STORAGE_DIR, filename)
    sha256 = hashlib.sha256()
    with open(filepath, "wb") as f:
        while chunk := await package.read(8192):
            f.write(chunk)
            sha256.update(chunk)
    meta_path = filepath + ".sha256"
    with open(meta_path, "w") as f:
        f.write(sha256.hexdigest())
    return RedirectResponse(url="/admin/ota", status_code=303)


@router.post("/devices/{device_id}/ota/push")
def push_ota(request: Request, device_id: int, version: str = Form(...),
             db: Session = Depends(get_db)):
    require_admin(request)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return RedirectResponse(url="/admin", status_code=303)
    version = sanitize_string(version, max_length=50)
    filename = f"lapi-{version}.tar.gz"
    filepath = os.path.join(OTA_STORAGE_DIR, filename)
    meta_path = filepath + ".sha256"
    if not os.path.exists(filepath) or not os.path.exists(meta_path):
        return RedirectResponse(url=f"/admin/tenants/{device.parking.tenant_id}", status_code=303)
    with open(meta_path) as f:
        sha256 = f.read().strip()
    download_url = f"{WEB_BASE_URL}/static/ota/{filename}"
    publish_ota_update(device.mqtt_client_id, download_url, sha256, version)
    return RedirectResponse(url=f"/admin/tenants/{device.parking.tenant_id}", status_code=303)
