import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db, SessionLocal
from .auth import hash_password, get_current_user, NotAuthenticated
from .models import Admin
from .config import DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD, OTA_STORAGE_DIR
from .mqtt_publisher import init_mqtt, stop_mqtt
from .subscription_sync import check_expired_subscriptions
from .routers import auth_routes, admin, dashboard, access
from .routers import subscribe as subscribe_router
from .routers import stripe_webhook

log = logging.getLogger("lapi.web")

_expiry_task = None


async def _subscription_expiry_loop():
    while True:
        await asyncio.sleep(300)
        try:
            db = SessionLocal()
            count = check_expired_subscriptions(db)
            if count:
                log.info(f"{count} abonnement(s) traite(s)")
            db.close()
        except Exception as e:
            log.error(f"Erreur verification abonnements: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _expiry_task
    init_db()
    _ensure_admin()
    os.makedirs(OTA_STORAGE_DIR, exist_ok=True)
    init_mqtt()
    _expiry_task = asyncio.create_task(_subscription_expiry_loop())
    yield
    _expiry_task.cancel()
    stop_mqtt()


app = FastAPI(title="LAPI Admin", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_routes.router)
app.include_router(admin.router)
app.include_router(dashboard.router)
app.include_router(access.router)
app.include_router(subscribe_router.router)
app.include_router(stripe_webhook.router)


@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url="/login", status_code=303)


@app.get("/")
def root(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user.get("role") == "admin":
        return RedirectResponse(url="/admin", status_code=303)
    if user.get("role") == "subscriber":
        return RedirectResponse(url="/subscribe/account", status_code=303)
    return RedirectResponse(url="/dashboard", status_code=303)


def _ensure_admin():
    db = SessionLocal()
    try:
        if not db.query(Admin).first():
            db.add(Admin(
                username=DEFAULT_ADMIN_USERNAME,
                password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            ))
            db.commit()
    finally:
        db.close()
