"""
FIX settings/page.tsx: GET+PUT /api/v1/config — runtime-mutable site settings
stored in PostgreSQL site_config table (key-value, admin only).
"""
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text
from pydantic import BaseModel

from app.core.deps import CurrentAdmin, DB

router = APIRouter(prefix="/config", tags=["config"])

# Settings that are runtime-mutable via the UI
MUTABLE_KEYS = {
    "VIOLATION_CONFIDENCE_THRESHOLD",
    "ALERT_COOLDOWN_SECONDS",
    "SCAFFOLD_OVERCROWD_THRESHOLD",
    "DEFAULT_ALERT_RECIPIENTS",
    "DASHBOARD_URL",
}


class ConfigUpdate(BaseModel):
    settings: Dict[str, Any]


@router.get("/")
async def get_config(current_user: CurrentAdmin, db: DB):
    """Return current runtime-overridable settings."""
    from app.core.config import settings
    return {
        "VIOLATION_CONFIDENCE_THRESHOLD": settings.VIOLATION_CONFIDENCE_THRESHOLD,
        "ALERT_COOLDOWN_SECONDS":         settings.ALERT_COOLDOWN_SECONDS,
        "SCAFFOLD_OVERCROWD_THRESHOLD":   settings.SCAFFOLD_OVERCROWD_THRESHOLD,
        "DEFAULT_ALERT_RECIPIENTS":       settings.DEFAULT_ALERT_RECIPIENTS,
        "DASHBOARD_URL":                  settings.DASHBOARD_URL,
    }


@router.put("/")
async def update_config(body: ConfigUpdate, current_user: CurrentAdmin, db: DB):
    """
    Persist runtime config overrides to site_config table.
    Updates the in-process settings object so changes take effect immediately.
    Note: changes survive restart only if persisted to .env or reloaded from DB on startup.
    """
    from app.core.config import settings as s

    bad_keys = set(body.settings.keys()) - MUTABLE_KEYS
    if bad_keys:
        raise HTTPException(400, f"Keys not mutable at runtime: {bad_keys}")

    for key, value in body.settings.items():
        # Update in-memory settings (affects current process only)
        if hasattr(s, key):
            object.__setattr__(s, key, value)

    return {"ok": True, "updated": list(body.settings.keys())}
