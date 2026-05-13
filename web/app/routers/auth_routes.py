from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import authenticate_admin, authenticate_user, create_token

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


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("token")
    return response
