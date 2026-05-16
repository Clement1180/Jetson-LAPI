"""Security middleware and utilities: CSRF, headers, rate limiting, input validation."""

import hashlib
import hmac
import html
import re
import secrets
import time
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .config import SECRET_KEY

# --- CSRF Protection ---

CSRF_TOKEN_LENGTH = 32
CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_EXEMPT_PATHS = {"/webhook/stripe"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def generate_csrf_token() -> str:
    return secrets.token_hex(CSRF_TOKEN_LENGTH)


def _verify_csrf_token(cookie_token: str, form_token: str) -> bool:
    if not cookie_token or not form_token:
        return False
    return hmac.compare_digest(cookie_token, form_token)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in SAFE_METHODS:
            response = await call_next(request)
            if not request.cookies.get(CSRF_COOKIE_NAME):
                token = generate_csrf_token()
                response.set_cookie(
                    CSRF_COOKIE_NAME, token,
                    httponly=False, samesite="lax", secure=False,
                )
            return response

        if request.url.path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        content_type = request.headers.get("content-type", "")

        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            body = await request.body()
            form = await request.form()
            form_token = form.get(CSRF_FORM_FIELD, "")
            await form.close()
        else:
            form_token = request.headers.get("x-csrf-token", "")

        if not _verify_csrf_token(cookie_token, form_token):
            return RedirectResponse(url=request.headers.get("referer", "/login"), status_code=303)

        response = await call_next(request)
        new_token = generate_csrf_token()
        response.set_cookie(
            CSRF_COOKIE_NAME, new_token,
            httponly=False, samesite="lax", secure=False,
        )
        return response


# --- Security Headers ---

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "frame-ancestors 'none';"
        )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


# --- Rate Limiting ---

class RateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def is_limited(self, key: str) -> bool:
        now = time.time()
        entries = self._attempts.get(key, [])
        entries = [t for t in entries if now - t < self.window_seconds]
        self._attempts[key] = entries
        return len(entries) >= self.max_attempts

    def record(self, key: str):
        self._attempts.setdefault(key, []).append(time.time())

    def reset(self, key: str):
        self._attempts.pop(key, None)


auth_rate_limiter = RateLimiter(max_attempts=5, window_seconds=300)


# --- Password Policy ---

MIN_PASSWORD_LENGTH = 12


def validate_password_strength(password: str) -> Optional[str]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caracteres"
    if not re.search(r"[A-Z]", password):
        return "Le mot de passe doit contenir au moins une majuscule"
    if not re.search(r"[0-9]", password):
        return "Le mot de passe doit contenir au moins un chiffre"
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Le mot de passe doit contenir au moins un caractere special"
    return None


# --- Input Validation ---

PLATE_REGEX = re.compile(r"^[A-Z]{2}-[0-9]{3}-[A-Z]{2}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def sanitize_string(value: str, max_length: int = 255) -> str:
    return value.strip()[:max_length]


def validate_email(email: str) -> Optional[str]:
    email = email.strip()
    if len(email) > 254:
        return "Adresse email trop longue"
    if not EMAIL_REGEX.match(email):
        return "Format d'adresse email invalide"
    return None


def validate_plate(plate: str) -> Optional[str]:
    plate = plate.upper().strip().replace(" ", "-")
    if not PLATE_REGEX.match(plate):
        return "Format de plaque invalide (attendu: AA-123-AA)"
    return None


def escape_html(value: str) -> str:
    return html.escape(value, quote=True)
