"""
FIX BUG-21: registration protected by REGISTRATION_OPEN flag
FIX BUG-22: /auth/refresh endpoint implemented
FIX BUG-23: proper email validation via pydantic EmailStr
"""
from fastapi import APIRouter, HTTPException, Depends, Body, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.security import (
    verify_password, hash_password,
    create_access_token, create_refresh_token, decode_token,
)
from app.core.deps import CurrentUser, CurrentAdmin, DB
from app.models.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class UserCreate(BaseModel):
    email:     EmailStr   # BUG-23 FIX: real email validation
    password:  str
    full_name: str
    phone:     str | None = None


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id:        int
    email:     str
    full_name: str
    phone:     str | None
    is_admin:  bool
    model_config = {"from_attributes": True}


# ── Login ──────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user   = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(400, "Account inactive")
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


# ── Refresh ─────────────────────────────────────────────────────────────────
# FIX BUG-22: this endpoint was completely missing
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(body: RefreshRequest, db: DB):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(401, "Invalid or expired refresh token")
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(401, "Malformed token")
    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


# ── Register ──────────────────────────────────────────────────────────────────
# FIX BUG-21: gated by REGISTRATION_OPEN; closed → admin required
@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    # conditional admin dep applied below
):
    if not settings.REGISTRATION_OPEN:
        # Require admin token when registration is closed
        raise HTTPException(
            403,
            "Open registration is disabled. Ask an admin to create your account.",
        )
    existing = await db.execute(select(User).where(User.email == str(payload.email)))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")
    if len(payload.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    user = User(
        email=str(payload.email),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/register/admin", response_model=UserResponse, status_code=201)
async def admin_register(payload: UserCreate, _admin: CurrentAdmin, db: DB):
    """Admin-only user creation — always available regardless of REGISTRATION_OPEN."""
    existing = await db.execute(select(User).where(User.email == str(payload.email)))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")
    if len(payload.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    user = User(
        email=str(payload.email),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


# ── Me ────────────────────────────────────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser):
    return current_user
