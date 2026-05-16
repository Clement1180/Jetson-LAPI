"""Tests for authentication: login, registration, rate limiting."""

import pytest
from app.auth import hash_password, verify_password, create_token, decode_token
from app.security import auth_rate_limiter, CSRF_COOKIE_NAME


CSRF = "test-csrf-token-fixed"


def _post(client, url, data, cookies=None, follow_redirects=False):
    cookies = cookies or {}
    cookies[CSRF_COOKIE_NAME] = CSRF
    data["csrf_token"] = CSRF
    return client.post(url, data=data, cookies=cookies, follow_redirects=follow_redirects)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "SecurePass123!@#"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("CorrectPass123!@#")
        assert not verify_password("WrongPass123!@#", hashed)

    def test_hash_includes_salt(self):
        pw = "SamePassword123!@#"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2

    def test_malformed_hash_fails(self):
        assert not verify_password("anything", "no-dollar-sign")


class TestJWT:
    def test_create_and_decode(self):
        data = {"sub": "1", "role": "admin", "username": "test"}
        token = create_token(data)
        decoded = decode_token(token)
        assert decoded["sub"] == "1"
        assert decoded["role"] == "admin"

    def test_invalid_token(self):
        assert decode_token("invalid.token.here") is None

    def test_token_contains_expiry(self):
        token = create_token({"sub": "1"})
        decoded = decode_token(token)
        assert "exp" in decoded


class TestAdminLogin:
    def test_login_page_returns_200(self, client):
        r = client.get("/login")
        assert r.status_code == 200

    def test_successful_admin_login(self, client, admin_user):
        r = _post(client, "/login", {"username": "testadmin", "password": "TestAdmin123!@#"})
        assert r.status_code == 303
        assert "/admin" in r.headers.get("location", "")

    def test_failed_login(self, client, admin_user):
        r = _post(client, "/login", {"username": "testadmin", "password": "WrongPassword123!"})
        assert r.status_code == 200
        assert "Identifiants incorrects" in r.text


class TestSubscriberRegistration:
    def test_register_page_returns_200(self, client):
        r = client.get("/subscribe/register")
        assert r.status_code == 200

    def test_successful_registration(self, client):
        r = _post(client, "/subscribe/register", {
            "email": "new@test.com",
            "password": "NewPass123!@#",
            "password_confirm": "NewPass123!@#",
            "first_name": "Jean",
            "last_name": "Dupont",
            "plate": "AB-123-CD",
        })
        assert r.status_code == 303
        assert "/subscribe/account" in r.headers.get("location", "")

    def test_registration_password_mismatch(self, client):
        r = _post(client, "/subscribe/register", {
            "email": "new@test.com",
            "password": "NewPass123!@#",
            "password_confirm": "DifferentPass123!@#",
            "plate": "AB-123-CD",
        })
        assert r.status_code == 200
        assert "ne correspondent pas" in r.text

    def test_registration_weak_password(self, client):
        r = _post(client, "/subscribe/register", {
            "email": "new@test.com",
            "password": "weak",
            "password_confirm": "weak",
            "plate": "AB-123-CD",
        })
        assert r.status_code == 200
        assert "mot de passe" in r.text.lower()

    def test_registration_invalid_plate(self, client):
        r = _post(client, "/subscribe/register", {
            "email": "new@test.com",
            "password": "NewPass123!@#",
            "password_confirm": "NewPass123!@#",
            "plate": "INVALID",
        })
        assert r.status_code == 200
        assert "plaque invalide" in r.text.lower()

    def test_registration_duplicate_email(self, client, subscriber):
        r = _post(client, "/subscribe/register", {
            "email": "sub@test.com",
            "password": "NewPass123!@#",
            "password_confirm": "NewPass123!@#",
            "plate": "EF-456-GH",
        })
        assert r.status_code == 200
        assert "deja utilisee" in r.text


class TestRateLimiting:
    def test_login_rate_limited_after_5_attempts(self, client, admin_user):
        auth_rate_limiter.reset("login:testclient")
        for _ in range(5):
            _post(client, "/login", {"username": "testadmin", "password": "wrong"})

        r = _post(client, "/login", {"username": "testadmin", "password": "wrong"})
        assert "Trop de tentatives" in r.text
        auth_rate_limiter.reset("login:testclient")

    def test_subscriber_login_rate_limited(self, client, subscriber):
        auth_rate_limiter.reset("sub_login:testclient")
        for _ in range(5):
            _post(client, "/subscribe/login", {"email": "sub@test.com", "password": "wrong"})

        r = _post(client, "/subscribe/login", {"email": "sub@test.com", "password": "wrong"})
        assert "Trop de tentatives" in r.text
        auth_rate_limiter.reset("sub_login:testclient")


class TestLogout:
    def test_logout_clears_cookie(self, client, admin_token):
        r = client.get("/logout", cookies={"token": admin_token}, follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers.get("location", "")
