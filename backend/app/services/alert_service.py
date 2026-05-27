"""
FIX BUG-15: Twilio call wrapped in run_in_executor — no longer blocks event loop.
FIX BUG-16: dashboard_url reads from settings.DASHBOARD_URL (not hardcoded localhost).
FIX BUG-13: cooldown removed — now lives exclusively in cooldown.py (Redis-backed).
"""
import asyncio
from typing import List
from loguru import logger

from app.core.config import settings
from app.models.models import VIOLATION_LABELS


def build_alert_message(violation_type, camera_name: str, zone: str, confidence: float) -> str:
    label = VIOLATION_LABELS.get(violation_type, str(violation_type))
    from datetime import datetime, timezone
    ts  = datetime.now(timezone.utc).strftime("%H:%M UTC")
    url = settings.DASHBOARD_URL  # BUG-16 FIX: from config, not hardcoded
    return (
        f"SENTRYLENS ALERT\n"
        f"Violation: {label}\n"
        f"Camera: {camera_name} | Zone: {zone}\n"
        f"Confidence: {confidence:.0%} | Time: {ts}\n"
        f"View: {url}/dashboard/alerts"
    )


def _twilio_send_sync(account_sid: str, auth_token: str, from_: str, to: str, body: str) -> str:
    """Synchronous Twilio call — run via executor, never call directly in async context."""
    from twilio.rest import Client
    client = Client(account_sid, auth_token)
    msg    = client.messages.create(body=body, from_=from_, to=to)
    return msg.sid


async def send_sms_alert(to_number: str, message: str) -> dict:
    """
    FIX BUG-15: runs the blocking Twilio HTTP call in a thread executor
    so it never stalls the asyncio event loop.
    """
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio not configured — SMS not sent.")
        return {"status": "skipped", "reason": "no_credentials"}
    try:
        loop = asyncio.get_running_loop()
        sid  = await loop.run_in_executor(
            None,
            _twilio_send_sync,
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
            settings.TWILIO_FROM_NUMBER,
            to_number,
            message,
        )
        logger.info(f"SMS sent to {to_number}: {sid}")
        return {"status": "sent", "sid": sid}
    except Exception as e:
        logger.error(f"Twilio SMS failed to {to_number}: {e}")
        return {"status": "failed", "error": str(e)}


async def send_alerts_to_recipients(
    recipients: List[str],
    violation_type,
    camera_name: str,
    zone: str,
    confidence: float,
) -> List[dict]:
    if not recipients:
        return []
    message = build_alert_message(violation_type, camera_name, zone, confidence)
    results = []
    for phone in recipients:
        r = await send_sms_alert(phone, message)
        results.append({"phone": phone, **r})
    return results
