"""Tests for CRUD whitelist operations via dashboard."""

import pytest
from unittest.mock import patch
from app.models import WhitelistEntry
from app.security import CSRF_COOKIE_NAME

CSRF = "test-csrf-token-fixed"


def _post(client, url, data=None, cookies=None):
    cookies = cookies or {}
    cookies[CSRF_COOKIE_NAME] = CSRF
    data = data or {}
    data["csrf_token"] = CSRF
    return client.post(url, data=data, cookies=cookies, follow_redirects=False)


class TestWhitelistCRUD:
    def test_view_device_whitelist(self, client, tenant_token, device):
        r = client.get(f"/dashboard/device/{device.id}", cookies={"token": tenant_token})
        assert r.status_code == 200

    @patch("app.routers.dashboard.publish_plate_add")
    def test_add_plate(self, mock_mqtt, client, tenant_token, device, db_session):
        r = _post(client, f"/dashboard/device/{device.id}/whitelist/add", {
            "plate": "AB-123-CD",
            "label": "Test",
            "owner_name": "Jean Test",
        }, cookies={"token": tenant_token})
        assert r.status_code == 303
        entry = db_session.query(WhitelistEntry).filter(
            WhitelistEntry.device_id == device.id,
            WhitelistEntry.plate == "AB-123-CD",
        ).first()
        assert entry is not None
        assert entry.owner_name == "Jean Test"
        mock_mqtt.assert_called_once()

    @patch("app.routers.dashboard.publish_plate_add")
    def test_add_duplicate_plate_ignored(self, mock_mqtt, client, tenant_token, device, db_session):
        entry = WhitelistEntry(device_id=device.id, plate="AB-123-CD", label="Existing")
        db_session.add(entry)
        db_session.commit()

        _post(client, f"/dashboard/device/{device.id}/whitelist/add", {
            "plate": "AB-123-CD",
            "label": "Duplicate",
        }, cookies={"token": tenant_token})
        count = db_session.query(WhitelistEntry).filter(
            WhitelistEntry.device_id == device.id,
            WhitelistEntry.plate == "AB-123-CD",
        ).count()
        assert count == 1
        mock_mqtt.assert_not_called()

    @patch("app.routers.dashboard.publish_plate_remove")
    def test_remove_plate(self, mock_mqtt, client, tenant_token, device, db_session):
        entry = WhitelistEntry(device_id=device.id, plate="AB-123-CD", label="ToRemove")
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        r = _post(client, f"/dashboard/device/{device.id}/whitelist/{entry.id}/delete",
                  cookies={"token": tenant_token})
        assert r.status_code == 303
        remaining = db_session.query(WhitelistEntry).filter(
            WhitelistEntry.id == entry.id
        ).first()
        assert remaining is None
        mock_mqtt.assert_called_once()

    @patch("app.routers.dashboard.publish_whitelist_sync")
    def test_sync_whitelist(self, mock_mqtt, client, tenant_token, device, db_session):
        db_session.add(WhitelistEntry(device_id=device.id, plate="AA-111-AA", label="A"))
        db_session.add(WhitelistEntry(device_id=device.id, plate="BB-222-BB", label="B"))
        db_session.commit()

        r = _post(client, f"/dashboard/device/{device.id}/whitelist/sync",
                  cookies={"token": tenant_token})
        assert r.status_code == 303
        mock_mqtt.assert_called_once()
        call_args = mock_mqtt.call_args[0]
        assert call_args[0] == device.mqtt_client_id
        assert len(call_args[1]) == 2


class TestWhitelistAccess:
    def test_unauthorized_access_redirects(self, client, device):
        r = client.get(f"/dashboard/device/{device.id}", follow_redirects=False)
        assert r.status_code == 303

    def test_wrong_tenant_redirects(self, client, device, db_session):
        from app.auth import hash_password, create_token
        from app.models import Tenant, TenantUser
        other_tenant = Tenant(name="Other")
        db_session.add(other_tenant)
        db_session.commit()
        db_session.refresh(other_tenant)
        other_user = TenantUser(tenant_id=other_tenant.id, username="other", password_hash=hash_password("OtherPass123!@#"))
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)
        token = create_token({"sub": str(other_user.id), "username": "other", "role": "tenant", "tenant_id": other_tenant.id})

        r = client.get(f"/dashboard/device/{device.id}", cookies={"token": token}, follow_redirects=False)
        assert r.status_code == 303
        assert "/dashboard" in r.headers.get("location", "")
