"""
FIX BUG-3: wrap int(user_id) in try/except so malformed tokens → 401, not 500.
"""
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import decode_token
from app.models.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise exc
    raw_id = payload.get("sub")
    try:
        user_id = int(raw_id)   # BUG-3 FIX: ValueError → 401
    except (TypeError, ValueError):
        raise exc
    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise exc
    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


# ── WebSocket token auth helper ───────────────────────────────────────────────
async def ws_auth(token: str, db: AsyncSession) -> User:
    """
    FIX BUG-18: authenticate WebSocket connections via ?token= query param.
    Raises ValueError (caller closes WS with code 4001) on failure.
    """
    if not token:
        raise ValueError("Missing token")
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise ValueError("Invalid or expired token")
    raw_id = payload.get("sub")
    try:
        user_id = int(raw_id)
    except (TypeError, ValueError):
        raise ValueError("Malformed token")
    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise ValueError("User not found or inactive")
    return user


CurrentUser  = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
DB           = Annotated[AsyncSession, Depends(get_db)]
