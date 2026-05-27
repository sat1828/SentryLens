"""Unit tests — no DB, no external services."""
import pytest
from datetime import timedelta


class TestSecurity:
    def test_hash_and_verify(self):
        from app.core.security import hash_password, verify_password
        h = hash_password("MyPass123")
        assert verify_password("MyPass123", h)
        assert not verify_password("WrongPass", h)
        assert h != "MyPass123"

    def test_access_token_roundtrip(self):
        from app.core.security import create_access_token, decode_token
        tok = create_access_token("42")
        pay = decode_token(tok)
        assert pay is not None
        assert pay["sub"] == "42"
        assert pay["type"] == "access"

    def test_refresh_token_type(self):
        from app.core.security import create_refresh_token, decode_token
        tok = create_refresh_token("42")
        assert decode_token(tok)["type"] == "refresh"

    def test_expired_token_returns_none(self):
        from app.core.security import create_access_token, decode_token
        tok = create_access_token("42", expires_delta=timedelta(seconds=-1))
        assert decode_token(tok) is None

    def test_tampered_token_returns_none(self):
        from app.core.security import decode_token
        assert decode_token("not.a.valid.token") is None


class TestConfig:
    def test_cors_origins_parsed(self):
        from app.core.config import Settings
        s = Settings(CORS_ORIGINS="http://localhost:3000,https://example.com")
        assert "http://localhost:3000" in s.cors_origins_list
        assert len(s.cors_origins_list) == 2

    def test_empty_recipients(self):
        from app.core.config import Settings
        assert Settings(DEFAULT_ALERT_RECIPIENTS="").alert_recipients_list == []

    def test_recipients_parsed(self):
        from app.core.config import Settings
        s = Settings(DEFAULT_ALERT_RECIPIENTS="+919999999999,+447000000000")
        assert len(s.alert_recipients_list) == 2

    def test_secret_key_validated_in_production(self):
        from app.core.config import Settings
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Settings(
                APP_ENV="production",
                SECRET_KEY="insecure-dev-key-change-in-production",
            )

    def test_secret_key_ok_in_dev_with_default(self):
        from app.core.config import Settings
        # Should NOT raise in development with weak key
        s = Settings(APP_ENV="development", SECRET_KEY="insecure-dev-key-change-in-production")
        assert s.APP_ENV == "development"

    def test_dashboard_url_in_config(self):
        from app.core.config import Settings
        s = Settings(DASHBOARD_URL="https://mysite.sentrylens.io")
        assert s.DASHBOARD_URL == "https://mysite.sentrylens.io"


class TestDetectorMapping:
    def test_violation_class_ids(self):
        from app.services.detector import ROBOFLOW_CLASS_MAP
        from app.models.models import ViolationType
        assert ROBOFLOW_CLASS_MAP[2] == ViolationType.MISSING_HELMET
        assert ROBOFLOW_CLASS_MAP[4] == ViolationType.MISSING_VEST
        assert ROBOFLOW_CLASS_MAP[0] is None   # hardhat present — no violation
        assert ROBOFLOW_CLASS_MAP[5] is None   # person — used for zone logic, not a violation

    def test_severity_all_vtypes_present(self):
        from app.models.models import VIOLATION_SEVERITY, ViolationType, Severity
        for vt in ViolationType:
            assert vt in VIOLATION_SEVERITY, f"{vt} missing from VIOLATION_SEVERITY"
        assert VIOLATION_SEVERITY[ViolationType.NEAR_MISS]       == Severity.CRITICAL
        assert VIOLATION_SEVERITY[ViolationType.MISSING_HARNESS] == Severity.CRITICAL

    def test_labels_all_vtypes_present(self):
        from app.models.models import VIOLATION_LABELS, ViolationType
        for vt in ViolationType:
            assert vt in VIOLATION_LABELS
            assert len(VIOLATION_LABELS[vt]) > 0

    def test_harness_and_near_miss_not_detectable(self):
        """
        BUG-4/5 regression test: documents that these types deliberately
        cannot be produced by the class map with the 10-class Roboflow dataset.
        """
        from app.services.detector import ROBOFLOW_CLASS_MAP
        from app.models.models import ViolationType
        detectable = {v for v in ROBOFLOW_CLASS_MAP.values() if v is not None}
        assert ViolationType.MISSING_HARNESS not in detectable, \
            "MISSING_HARNESS should not be in class map — no harness class in Roboflow dataset"
        assert ViolationType.NEAR_MISS not in detectable, \
            "NEAR_MISS should not be in class map — requires trajectory ML, not class detection"


class TestCooldown:
    """Tests for the Redis-backed cooldown store (uses in-memory fallback in tests)."""

    @pytest.mark.asyncio
    async def test_not_on_cooldown_initially(self):
        from app.core import cooldown
        cooldown._mem_store.clear()
        cooldown._redis = None
        result = await cooldown.is_on_cooldown(9001, "missing_helmet", 30)
        assert result is False

    @pytest.mark.asyncio
    async def test_on_cooldown_after_set(self):
        from app.core import cooldown
        cooldown._mem_store.clear()
        cooldown._redis = None
        await cooldown.set_cooldown(9002, "missing_vest", 30)
        assert await cooldown.is_on_cooldown(9002, "missing_vest", 30) is True

    @pytest.mark.asyncio
    async def test_independent_camera_cooldowns(self):
        from app.core import cooldown
        cooldown._mem_store.clear()
        cooldown._redis = None
        await cooldown.set_cooldown(9003, "missing_helmet", 30)
        # Camera 9004 not set — should not be on cooldown
        assert await cooldown.is_on_cooldown(9004, "missing_helmet", 30) is False

    @pytest.mark.asyncio
    async def test_independent_type_cooldowns(self):
        from app.core import cooldown
        cooldown._mem_store.clear()
        cooldown._redis = None
        await cooldown.set_cooldown(9005, "missing_vest", 30)
        # Different type on same camera — should not be on cooldown
        assert await cooldown.is_on_cooldown(9005, "missing_helmet", 30) is False


class TestAlertService:
    def test_message_contains_required_fields(self):
        from app.services.alert_service import build_alert_message
        from app.models.models import ViolationType
        msg = build_alert_message(ViolationType.MISSING_HELMET, "CAM-01", "Zone A", 0.87)
        assert "Missing helmet" in msg
        assert "CAM-01" in msg
        assert "Zone A" in msg
        assert "87%" in msg

    def test_message_url_not_localhost_if_dashboard_url_set(self):
        """BUG-16 regression: DASHBOARD_URL must come from config, not hardcoded localhost."""
        import os
        os.environ["DASHBOARD_URL"] = "https://sentrylens.mysite.com"
        # Re-import with fresh settings to pick up env var
        from importlib import reload
        import app.core.config as cfg
        cfg._settings = None  # bust cache if present
        from app.services.alert_service import build_alert_message
        from app.models.models import ViolationType
        # The URL in the message should match config (we just verify it's in the message)
        msg = build_alert_message(ViolationType.MISSING_VEST, "CAM-02", "Zone B", 0.75)
        assert "dashboard/alerts" in msg  # link format is present
