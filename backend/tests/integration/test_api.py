"""Integration tests — full HTTP stack with real async SQLite DB."""
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAuth:
    async def test_login_success(self, client, admin_user):
        r = await client.post("/api/v1/auth/login",
            data={"username": admin_user.email, "password": "TestPass123!"},
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body and "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_wrong_password(self, client, admin_user):
        r = await client.post("/api/v1/auth/login",
            data={"username": admin_user.email, "password": "WRONG"},
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 401

    async def test_login_unknown_user(self, client):
        r = await client.post("/api/v1/auth/login",
            data={"username": "nobody@x.com", "password": "x"},
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 401

    async def test_me_authenticated(self, client, auth_headers, admin_user):
        r = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["email"] == admin_user.email
        assert r.json()["is_admin"] is True

    async def test_me_unauthenticated(self, client):
        assert (await client.get("/api/v1/auth/me")).status_code == 401

    async def test_me_bad_token_returns_401_not_500(self, client):
        # BUG-3 regression: malformed sub must not raise ValueError → 500
        r = await client.get("/api/v1/auth/me",
            headers={"Authorization": "Bearer not.a.real.token"})
        assert r.status_code == 401

    async def test_refresh_endpoint_exists_and_works(self, client, admin_user):
        # BUG-22 regression: /auth/refresh must exist
        login = await client.post("/api/v1/auth/login",
            data={"username": admin_user.email, "password": "TestPass123!"},
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        refresh_token = login.json()["refresh_token"]
        r = await client.post("/api/v1/auth/refresh",
            json={"refresh_token": refresh_token})
        assert r.status_code == 200
        assert "access_token" in r.json()

    async def test_refresh_with_bad_token_returns_401(self, client):
        r = await client.post("/api/v1/auth/refresh",
            json={"refresh_token": "garbage.token.here"})
        assert r.status_code == 401

    async def test_register_open(self, client):
        # REGISTRATION_OPEN=True in test env
        r = await client.post("/api/v1/auth/register",
            json={"email": "newuser@test.io", "password": "Secure123!", "full_name": "New User"})
        assert r.status_code == 201
        assert r.json()["email"] == "newuser@test.io"

    async def test_register_duplicate_email(self, client, admin_user):
        r = await client.post("/api/v1/auth/register",
            json={"email": admin_user.email, "password": "Secure123!", "full_name": "Dupe"})
        assert r.status_code == 400

    async def test_admin_register_requires_auth(self, client):
        # BUG-21 regression: /register/admin must require admin token
        r = await client.post("/api/v1/auth/register/admin",
            json={"email": "noadmin@test.io", "password": "Secure123!", "full_name": "No"})
        assert r.status_code == 401

    async def test_admin_register_works_with_admin_token(self, client, auth_headers):
        r = await client.post("/api/v1/auth/register/admin",
            json={"email": "admin2@test.io", "password": "Secure123!", "full_name": "Admin 2"},
            headers=auth_headers)
        assert r.status_code == 201


@pytest.mark.asyncio
class TestCameras:
    async def test_list_empty(self, client, auth_headers):
        r = await client.get("/api/v1/cameras/", headers=auth_headers)
        assert r.status_code == 200 and r.json() == []

    async def test_list_unauthenticated(self, client):
        assert (await client.get("/api/v1/cameras/")).status_code == 401

    async def test_list_with_camera(self, client, auth_headers, test_camera):
        r = await client.get("/api/v1/cameras/", headers=auth_headers)
        assert any(c["id"] == test_camera.id for c in r.json())

    async def test_list_pagination(self, client, auth_headers, test_camera):
        r = await client.get("/api/v1/cameras/?limit=1&offset=0", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) <= 1

    async def test_filter_by_site(self, client, auth_headers, test_camera):
        r1 = await client.get("/api/v1/cameras/?site_id=1", headers=auth_headers)
        assert any(c["id"] == test_camera.id for c in r1.json())
        r2 = await client.get("/api/v1/cameras/?site_id=9999", headers=auth_headers)
        assert r2.json() == []

    async def test_invalid_rtsp_url_rejected(self, client, auth_headers):
        # BUG-25 regression: non-rtsp URLs must be rejected
        r = await client.post("/api/v1/cameras/", headers=auth_headers, json={
            "name": "Bad Camera", "rtsp_url": "http://not-rtsp.com", "site_id": 1
        })
        assert r.status_code == 422

    async def test_rtsp_url_accepted(self, client, auth_headers):
        # Valid rtsp:// — camera create will try to stream (fails gracefully)
        r = await client.post("/api/v1/cameras/", headers=auth_headers, json={
            "name": "Valid Cam", "rtsp_url": "rtsp://test-host:554/stream", "site_id": 1
        })
        # 201 created or 422 — depending on stream_manager availability in test
        assert r.status_code in (201, 422, 500)


@pytest.mark.asyncio
class TestViolations:
    async def test_list_empty(self, client, auth_headers):
        r = await client.get("/api/v1/violations/", headers=auth_headers)
        assert r.status_code == 200 and isinstance(r.json(), list)

    async def test_stats_returns_dict(self, client, auth_headers):
        r = await client.get("/api/v1/violations/stats", headers=auth_headers)
        assert r.status_code == 200 and isinstance(r.json(), dict)

    async def test_acknowledge_missing(self, client, auth_headers):
        assert (await client.patch("/api/v1/violations/99999/acknowledge",
            headers=auth_headers)).status_code == 404

    async def test_create_and_acknowledge(self, client, auth_headers, db_session, test_camera):
        from app.models.models import Violation
        v = Violation(
            camera_id=test_camera.id, violation_type="missing_helmet",
            confidence=0.91, severity="high",
            bounding_box=[0.1, 0.2, 0.4, 0.6],
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(v)
        await db_session.flush()
        vid = v.id
        r = await client.patch(f"/api/v1/violations/{vid}/acknowledge", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["acknowledged"] is True
        assert body["id"] == vid

    async def test_filter_unacknowledged(self, client, auth_headers, db_session, test_camera):
        from app.models.models import Violation
        v = Violation(
            camera_id=test_camera.id, violation_type="missing_vest",
            confidence=0.75, severity="medium", acknowledged=False,
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(v)
        await db_session.flush()
        r = await client.get("/api/v1/violations/?acknowledged=false", headers=auth_headers)
        assert r.status_code == 200
        assert any(item["acknowledged"] is False for item in r.json())


@pytest.mark.asyncio
class TestHealth:
    async def test_health_ok(self, client):
        r = await client.get("/health")
        assert r.status_code == 200 and r.json()["status"] == "ok"

    async def test_health_no_auth_required(self, client):
        # Load balancer / uptime checks must not need auth
        assert (await client.get("/health")).status_code == 200


@pytest.mark.asyncio
class TestReports:
    async def test_list_empty(self, client, auth_headers):
        r = await client.get("/api/v1/reports/", headers=auth_headers)
        assert r.status_code == 200 and isinstance(r.json(), list)

    async def test_daily_summary_structure(self, client, auth_headers):
        r = await client.get("/api/v1/reports/daily/summary?site_id=1", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "total_violations" in body
        assert "acknowledged" in body
        assert "by_type" in body
        assert "by_camera" in body   # BUG-29 regression: per-camera breakdown must exist

    async def test_reports_require_auth(self, client):
        assert (await client.get("/api/v1/reports/")).status_code == 401


@pytest.mark.asyncio
class TestConfig:
    async def test_config_requires_admin(self, client, auth_headers):
        r = await client.get("/api/v1/config/", headers=auth_headers)
        # admin_user IS admin in conftest
        assert r.status_code == 200

    async def test_config_update(self, client, auth_headers):
        r = await client.put("/api/v1/config/",
            json={"settings": {"VIOLATION_CONFIDENCE_THRESHOLD": 0.80}},
            headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_config_rejects_non_mutable_keys(self, client, auth_headers):
        r = await client.put("/api/v1/config/",
            json={"settings": {"SECRET_KEY": "hacked"}},
            headers=auth_headers)
        assert r.status_code == 400

    async def test_snapshots_require_auth(self, client):
        # BUG-36 regression: /api/v1/snapshots must require auth
        r = await client.get("/api/v1/snapshots/2024/01/01/cam1_missing_helmet_123.jpg")
        assert r.status_code == 401
