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

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {
        "error": None,
    })


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...),
          db: Session = Depends(get_db)):
    # Admin ?
    admin = authenticate_admin(db, username, password)
    if admin:
        token = create_token({"sub": str(admin.id), "username": admin.username, "role": "admin"})
        response = RedirectResponse(url="/admin", status_code=303)
        response.set_cookie("token", token, httponly=True, samesite="lax", max_age=28800)
        return response

    # Tenant user ?
    user = authenticate_user(db, username, password)
    if user:
        token = create_token({
            "sub": str(user.id),
            "username": user.username,
            "role": "tenant",
            "tenant_id": user.tenant_id,
        })
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie("token", token, httponly=True, samesite="lax", max_age=28800)
        return response

    return templates.TemplateResponse(request, "login.html", {
        "error": "Identifiants incorrects",
    })


@router.get("/subscribe/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "subscribe/register.html", {
        "error": None,
    })


@router.post("/subscribe/register")
def register(request: Request, email: str = Form(...), password: str = Form(...),
             password_confirm: str = Form(...), first_name: str = Form(""),
             last_name: str = Form(""), plate: str = Form(...),
             db: Session = Depends(get_db)):
    if password != password_confirm:
        return templates.TemplateResponse(request, "subscribe/register.html", {
            "error": "Les mots de passe ne correspondent pas",
        })
    if len(password) < 6:
        return templates.TemplateResponse(request, "subscribe/register.html", {
            "error": "Le mot de passe doit contenir au moins 6 caracteres",
        })
    existing = db.query(Subscriber).filter(Subscriber.email == email).first()
    if existing:
        return templates.TemplateResponse(request, "subscribe/register.html", {
            "error": "Cette adresse email est deja utilisee",
        })

    plate = plate.upper().strip().replace(" ", "-")
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
        "error": None,
    })


@router.post("/subscribe/login")
def subscriber_login(request: Request, email: str = Form(...), password: str = Form(...),
                     db: Session = Depends(get_db)):
    subscriber = authenticate_subscriber(db, email, password)
    if subscriber:
        token = create_token({
            "sub": str(subscriber.id),
            "email": subscriber.email,
            "role": "subscriber",
        })
        response = RedirectResponse(url="/subscribe/account", status_code=303)
        response.set_cookie("token", token, httponly=True, samesite="lax", max_age=28800)
        return response

    return templates.TemplateResponse(request, "subscribe/login.html", {
        "error": "Email ou mot de passe incorrect",
    })


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("token")
    return response
