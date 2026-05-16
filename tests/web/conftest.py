"""Shared fixtures for web tests."""

import os
import sys
import time

import pytest

os.environ["LAPI_ENV"] = "development"
os.environ["LAPI_SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["LAPI_DATABASE_URL"] = "sqlite://"
os.environ["LAPI_ADMIN_USERNAME"] = "testadmin"
os.environ["LAPI_ADMIN_PASSWORD"] = "TestAdmin123!@#"
os.environ["LAPI_MQTT_BROKER"] = "localhost"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "web"))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.auth import hash_password, create_token
from app.models import (
    Admin, Tenant, TenantUser, Parking, Device, WhitelistEntry,
    Subscriber, SubscriptionPlan, Subscription, SubscriptionStatus, PlanDuration,
)
from app.security import CSRF_COOKIE_NAME


@pytest.fixture(autouse=True)
def test_db():
    """Create a fresh shared in-memory database for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestSession
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def db_session(test_db):
    session = test_db()
    yield session
    session.close()


def _csrf_post(client, url, data=None, cookies=None, **kwargs):
    """Helper: perform a POST with valid CSRF token."""
    cookies = cookies or {}
    csrf_token = "test-csrf-token-fixed"
    cookies[CSRF_COOKIE_NAME] = csrf_token
    if data is None:
        data = {}
    data["csrf_token"] = csrf_token
    return client.post(url, data=data, cookies=cookies, **kwargs)


@pytest.fixture
def csrf_post(client):
    """Returns a function that performs POST requests with valid CSRF."""
    def _post(url, data=None, cookies=None, **kwargs):
        return _csrf_post(client, url, data=data, cookies=cookies, **kwargs)
    return _post


@pytest.fixture
def admin_user(db_session):
    admin = Admin(username="testadmin", password_hash=hash_password("TestAdmin123!@#"))
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


@pytest.fixture
def admin_token(admin_user):
    return create_token({"sub": str(admin_user.id), "username": admin_user.username, "role": "admin"})


@pytest.fixture
def tenant(db_session):
    t = Tenant(name="Test Tenant", contact_email="tenant@test.com")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def tenant_user(db_session, tenant):
    user = TenantUser(
        tenant_id=tenant.id,
        username="tenantuser",
        password_hash=hash_password("TenantPass123!@#"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def tenant_token(tenant_user):
    return create_token({
        "sub": str(tenant_user.id),
        "username": tenant_user.username,
        "role": "tenant",
        "tenant_id": tenant_user.tenant_id,
    })


@pytest.fixture
def parking(db_session, tenant):
    p = Parking(tenant_id=tenant.id, name="Parking Test", address="1 rue test")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def device(db_session, parking):
    d = Device(
        parking_id=parking.id,
        serial_number="SN-TEST-001",
        name="Device Test",
        mqtt_client_id="device-test-001",
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


@pytest.fixture
def subscriber(db_session):
    s = Subscriber(
        email="sub@test.com",
        password_hash=hash_password("SubPass123!@#"),
        first_name="Jean",
        last_name="Test",
        plate="AB-123-CD",
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture
def subscriber_token(subscriber):
    return create_token({
        "sub": str(subscriber.id),
        "email": subscriber.email,
        "role": "subscriber",
    })


@pytest.fixture
def plan(db_session, parking):
    p = SubscriptionPlan(
        parking_id=parking.id,
        name="Plan Mensuel",
        duration=PlanDuration.MONTHLY,
        price_cents=2000,
        auto_renew_allowed=True,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def active_subscription(db_session, subscriber, plan):
    now = time.time()
    sub = Subscription(
        subscriber_id=subscriber.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        auto_renew=False,
        start_date=now,
        end_date=now + 30 * 86400,
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    return sub
