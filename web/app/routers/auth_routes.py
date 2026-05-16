from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import (
    authenticate_admin, authenticate_user, authenticate_subscriber,
    create_token, hash_password,
)
from ..models import Subscriber
from ..security import (
    auth_rate_limiter, validate_password_strength,
    validate_email, validate_plate, sanitize_string,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {
        "error": None, "csrf_token": request.cookies.get("csrf_token", ""),
    })


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...),
          db: Session = Depends(get_db)):
    ip = request.client.host
    if auth_rate_limiter.is_limited(f"login:{ip}"):
        return templates.TemplateResponse(request, "login.html", {
            "error": "Trop de tentatives. Reessayez dans quelques minutes.",
            "csrf_token": request.cookies.get("csrf_token", ""),
        })

    username = sanitize_string(username, max_length=150)

    admin = authenticate_admin(db, username, password)
    if admin:
        auth_rate_limiter.reset(f"login:{ip}")
        token = create_token({"sub": str(admin.id), "username": admin.username, "role": "admin"})
        response = RedirectResponse(url="/admin", status_code=303)
        response.set_cookie("token", token, httponly=True, samesite="lax", max_age=28800)
        return response

    user = authenticate_user(db, username, password)
    if user:
        auth_rate_limiter.reset(f"login:{ip}")
        token = create_token({
            "sub": str(user.id),
            "username": user.username,
            "role": "tenant",
            "tenant_id": user.tenant_id,
        })
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie("token", token, httponly=True, samesite="lax", max_age=28800)
        return response

    auth_rate_limiter.record(f"login:{ip}")
    return templates.TemplateResponse(request, "login.html", {
        "error": "Identifiants incorrects",
        "csrf_token": request.cookies.get("csrf_token", ""),
    })


@router.get("/subscribe/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "subscribe/register.html", {
        "error": None, "csrf_token": request.cookies.get("csrf_token", ""),
    })


@router.post("/subscribe/register")
def register(request: Request, email: str = Form(...), password: str = Form(...),
             password_confirm: str = Form(...), first_name: str = Form(""),
             last_name: str = Form(""), plate: str = Form(...),
             db: Session = Depends(get_db)):
    ip = request.client.host
    if auth_rate_limiter.is_limited(f"register:{ip}"):
        return templates.TemplateResponse(request, "subscribe/register.html", {
            "error": "Trop de tentatives. Reessayez dans quelques minutes.",
            "csrf_token": request.cookies.get("csrf_token", ""),
        })

    email = sanitize_string(email, max_length=254)
    first_name = sanitize_string(first_name, max_length=100)
    last_name = sanitize_string(last_name, max_length=100)
    plate = sanitize_string(plate, max_length=20)

    email_err = validate_email(email)
    if email_err:
        return templates.TemplateResponse(request, "subscribe/register.html", {
            "error": email_err, "csrf_token": request.cookies.get("csrf_token", ""),
        })

    if password != password_confirm:
        return templates.TemplateResponse(request, "subscribe/register.html", {
            "error": "Les mots de passe ne correspondent pas",
            "csrf_token": request.cookies.get("csrf_token", ""),
        })

    pw_error = validate_password_strength(password)
    if pw_error:
        return templates.TemplateResponse(request, "subscribe/register.html", {
            "error": pw_error, "csrf_token": request.cookies.get("csrf_token", ""),
        })

    plate = plate.upper().strip().replace(" ", "-")
    plate_err = validate_plate(plate)
    if plate_err:
        return templates.TemplateResponse(request, "subscribe/register.html", {
            "error": plate_err, "csrf_token": request.cookies.get("csrf_token", ""),
        })

    existing = db.query(Subscriber).filter(Subscriber.email == email).first()
    if existing:
        auth_rate_limiter.record(f"register:{ip}")
        return templates.TemplateResponse(request, "subscribe/register.html", {
            "error": "Cette adresse email est deja utilisee",
            "csrf_token": request.cookies.get("csrf_token", ""),
        })

    subscriber = Subscriber(
        email=email,
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        plate=plate,
    )
    db.add(subscriber)
    db.commit()
    db.refresh(subscriber)

    token = create_token({
        "sub": str(subscriber.id),
        "email": subscriber.email,
        "role": "subscriber",
    })
    response = RedirectResponse(url="/subscribe/account", status_code=303)
    response.set_cookie("token", token, httponly=True, samesite="lax", max_age=28800)
    return response


@router.get("/subscribe/login", response_class=HTMLResponse)
def subscriber_login_page(request: Request):
    return templates.TemplateResponse(request, "subscribe/login.html", {
        "error": None, "csrf_token": request.cookies.get("csrf_token", ""),
    })


@router.post("/subscribe/login")
def subscriber_login(request: Request, email: str = Form(...), password: str = Form(...),
                     db: Session = Depends(get_db)):
    ip = request.client.host
    if auth_rate_limiter.is_limited(f"sub_login:{ip}"):
        return templates.TemplateResponse(request, "subscribe/login.html", {
            "error": "Trop de tentatives. Reessayez dans quelques minutes.",
            "csrf_token": request.cookies.get("csrf_token", ""),
        })

    email = sanitize_string(email, max_length=254)
    subscriber = authenticate_subscriber(db, email, password)
    if subscriber:
        auth_rate_limiter.reset(f"sub_login:{ip}")
        token = create_token({
            "sub": str(subscriber.id),
            "email": subscriber.email,
            "role": "subscriber",
        })
        response = RedirectResponse(url="/subscribe/account", status_code=303)
        response.set_cookie("token", token, httponly=True, samesite="lax", max_age=28800)
        return response

    auth_rate_limiter.record(f"sub_login:{ip}")
    return templates.TemplateResponse(request, "subscribe/login.html", {
        "error": "Email ou mot de passe incorrect",
        "csrf_token": request.cookies.get("csrf_token", ""),
    })


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("token")
    return response
