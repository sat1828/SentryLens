"""
FIX BUG-13,17: Single Redis-backed cooldown store — replaces two independent
in-memory dicts that were split between violation_logger.py and alert_service.py.
Redis means cooldown is honoured across multiple uvicorn workers.
Falls back gracefully to in-memory if Redis is unavailable (dev without Redis).
"""
import asyncio
from typing import Optional
from loguru import logger


# ── module-level redis client (lazy-initialised) ───────────────────────────
_redis = None
_redis_lock = asyncio.Lock()
_mem_store: dict = {}   # fallback when Redis is unreachable


async def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    async with _redis_lock:
        if _redis is not None:
            return _redis
        try:
            import redis.asyncio as aioredis
            from app.core.config import settings
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
            await r.ping()
            _redis = r
            logger.info("Cooldown: using Redis backend.")
        except Exception as e:
            logger.warning(f"Cooldown: Redis unavailable ({e}), falling back to in-memory (NOT multi-worker safe).")
            _redis = None
    return _redis


async def is_on_cooldown(camera_id: int, vtype: str, seconds: int) -> bool:
    key = f"sl:cooldown:{camera_id}:{vtype}"
    try:
        r = await _get_redis()
        if r:
            return await r.exists(key) == 1
    except Exception:
        pass
    # in-memory fallback
    from datetime import datetime, timezone
    last = _mem_store.get(key)
    if last is None:
        return False
    return (datetime.now(timezone.utc) - last).total_seconds() < seconds


async def set_cooldown(camera_id: int, vtype: str, seconds: int) -> None:
    key = f"sl:cooldown:{camera_id}:{vtype}"
    try:
        r = await _get_redis()
        if r:
            await r.setex(key, seconds, "1")
            return
    except Exception:
        pass
    # in-memory fallback
    from datetime import datetime, timezone
    _mem_store[key] = datetime.now(timezone.utc)
