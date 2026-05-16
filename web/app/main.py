import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db, SessionLocal, engine
from .auth import hash_password, get_current_user, NotAuthenticated
from .models import Admin
from .config import DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD, OTA_STORAGE_DIR, IS_PRODUCTION
from .mqtt_publisher import init_mqtt, stop_mqtt
from .subscription_sync import check_expired_subscriptions, check_expiry_warnings
from .security import CSRFMiddleware, SecurityHeadersMiddleware, generate_csrf_token, CSRF_COOKIE_NAME
from .logging_config import setup_logging
from .routers import auth_routes, admin, dashboard, access
from .routers import subscribe as subscribe_router
from .routers import stripe_webhook

setup_logging(
    json_output=IS_PRODUCTION,
    level=os.getenv("LAPI_LOG_LEVEL", "INFO"),
)

_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=_sentry_dsn,
            traces_sample_rate=0.1,
            environment=os.getenv("LAPI_ENV", "development"),
        )
    except ImportError:
        pass

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
            warnings = check_expiry_warnings(db)
            if warnings:
                log.info(f"{warnings} avertissement(s) d'expiration envoye(s)")
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

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)

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


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return HTMLResponse(
        content=open("app/templates/errors/404.html").read(),
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    log.error(f"Erreur 500 sur {request.url}: {exc}")
    return HTMLResponse(
        content=open("app/templates/errors/500.html").read(),
        status_code=500,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception(f"Exception non geree sur {request.method} {request.url}: {exc}")
    return HTMLResponse(
        content=open("app/templates/errors/500.html").read(),
        status_code=500,
    )


@app.get("/health")
def health_check():
    from sqlalchemy import text
    status = {"status": "ok", "timestamp": time.time()}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["database"] = "ok"
    except Exception as e:
        status["database"] = "error"
        status["database_error"] = str(e)
        status["status"] = "degraded"

    from .mqtt_publisher import _connected as mqtt_connected
    status["mqtt"] = "ok" if mqtt_connected else "disconnected"

    return JSONResponse(status)


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
            if not DEFAULT_ADMIN_USERNAME or not DEFAULT_ADMIN_PASSWORD:
                if IS_PRODUCTION:
                    log.error(
                        "LAPI_ADMIN_USERNAME and LAPI_ADMIN_PASSWORD env vars are required "
                        "for first-launch admin creation in production."
                    )
                    return
                log.warning(
                    "No admin account and no LAPI_ADMIN_USERNAME/LAPI_ADMIN_PASSWORD set. "
                    "Set these env vars to create the initial admin account."
                )
                return
            from .security import validate_password_strength
            pw_error = validate_password_strength(DEFAULT_ADMIN_PASSWORD)
            if pw_error and IS_PRODUCTION:
                log.error(f"LAPI_ADMIN_PASSWORD does not meet policy: {pw_error}")
                return
            db.add(Admin(
                username=DEFAULT_ADMIN_USERNAME,
                password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            ))
            db.commit()
            log.info(f"Admin account '{DEFAULT_ADMIN_USERNAME}' created.")
    finally:
        db.close()
