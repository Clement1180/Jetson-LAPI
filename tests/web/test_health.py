"""Tests for /health endpoint."""

import pytest


class TestHealth:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "degraded")
        assert "timestamp" in data
        assert "database" in data
        assert "mqtt" in data

    def test_health_reports_database_status(self, client):
        r = client.get("/health")
        data = r.json()
        assert data["database"] == "ok"
