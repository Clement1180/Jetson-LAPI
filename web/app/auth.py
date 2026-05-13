import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from .config import SECRET_KEY, ALGORITHM, TOKEN_EXPIRE_MINUTES
from .models import Admin, TenantUser, Subscriber


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"


def verify_password(plain: str, hashed: str) -> bool:
    if "$" not in hashed:
        return False
    salt, h = hashed.split("$", 1)
    return hashlib.sha256((salt + plain).encode()).hexdigest() == h


def create_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def authenticate_admin(db: Session, username: str, password: str) -> Optional[Admin]:
    admin = db.query(Admin).filter(Admin.username == username).first()
    if admin and verify_password(password, admin.password_hash):
        return admin
    return None


def authenticate_user(db: Session, username: str, password: str) -> Optional[TenantUser]:
    user = db.query(TenantUser).filter(
        TenantUser.username == username,
        TenantUser.is_active == True
    ).first()
    if user and verify_password(password, user.password_hash):
        return user
    return None


def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("token")
    if not token:
        return None
    return decode_token(token)


class NotAuthenticated(Exception):
    pass


def require_admin(request: Request) -> dict:
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        raise NotAuthenticated()
    return user


def require_tenant(request: Request) -> dict:
    user = get_current_user(request)
    if not user or user.get("role") != "tenant":
        raise NotAuthenticated()
    return user


def authenticate_subscriber(db: Session, email: str, password: str) -> Optional[Subscriber]:
    sub = db.query(Subscriber).filter(
        Subscriber.email == email,
        Subscriber.is_active == True
    ).first()
    if sub and verify_password(password, sub.password_hash):
        return sub
    return None


def require_subscriber(request: Request) -> dict:
    user = get_current_user(request)
    if not user or user.get("role") != "subscriber":
        raise NotAuthenticated()
    return user
