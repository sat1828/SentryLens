"""
FIX BUG-12: violation_logger.subscribe_camera() called after stream_manager.add_camera()
FIX BUG-25: RTSP URL schema validation
FIX BUG-26: pagination on list_cameras
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select
from pydantic import BaseModel, field_validator

from app.core.deps import CurrentUser, CurrentAdmin, DB
from app.models.models import Camera, CameraStatus

router = APIRouter(prefix="/cameras", tags=["cameras"])


class CameraCreate(BaseModel):
    name:           str
    rtsp_url:       str
    site_id:        int
    zone:           str  = "General"
    location_label: str  = ""
    config:         dict = {}

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp_url(cls, v: str) -> str:
        # BUG-25 FIX: only allow rtsp:// or rtsps:// schemes
        v = v.strip()
        if not (v.startswith("rtsp://") or v.startswith("rtsps://")):
            raise ValueError("rtsp_url must start with rtsp:// or rtsps://")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Camera name cannot be empty")
        return v.strip()


class CameraResponse(BaseModel):
    id:             int
    name:           str
    rtsp_url:       str
    site_id:        int
    zone:           str
    location_label: str
    status:         str
    is_active:      bool
    last_seen:      Optional[datetime]
    config:         Optional[dict]
    model_config    = {"from_attributes": True}


@router.get("/", response_model=List[CameraResponse])
async def list_cameras(
    site_id: Optional[int] = None,
    limit:   int = Query(default=50, le=200),   # BUG-26 FIX: pagination
    offset:  int = 0,
    current_user: CurrentUser = None,
    db: DB = None,
):
    q = select(Camera).where(Camera.is_active == True)
    if site_id:
        q = q.where(Camera.site_id == site_id)
    q = q.limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=CameraResponse, status_code=201)
async def create_camera(payload: CameraCreate, request: Request, current_user: CurrentAdmin, db: DB):
    from app.services.stream_manager import stream_manager
    cam = Camera(
        name=payload.name, rtsp_url=payload.rtsp_url, site_id=payload.site_id,
        zone=payload.zone, location_label=payload.location_label, config=payload.config,
        status=CameraStatus.OFFLINE.value,
    )
    db.add(cam)
    await db.flush()
    await db.refresh(cam)

    # Start streaming
    await stream_manager.add_camera(cam.id, cam.rtsp_url, cam.config)

    # BUG-12 FIX: wire ViolationLogger to this new camera
    vlogger = getattr(request.app.state, "violation_logger", None)
    if vlogger:
        vlogger.subscribe_camera(cam.id)

    return cam


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(camera_id: int, current_user: CurrentAdmin, db: DB):
    from app.services.stream_manager import stream_manager
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    cam    = result.scalar_one_or_none()
    if not cam:
        raise HTTPException(404, "Camera not found")
    await stream_manager.remove_camera(camera_id)
    cam.is_active = False
    await db.flush()


@router.get("/status")
async def all_camera_statuses(current_user: CurrentUser, db: DB):
    from app.services.stream_manager import stream_manager
    return stream_manager.get_all_statuses()


@router.put("/{camera_id}/config")
async def update_camera_config(
    camera_id: int, config: dict, current_user: CurrentAdmin, db: DB
):
    """Update camera zone/threshold config (used by zone editor UI)."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    cam    = result.scalar_one_or_none()
    if not cam:
        raise HTTPException(404, "Camera not found")
    cam.config = config
    await db.flush()
    # Update live stream config
    from app.services.stream_manager import stream_manager
    if camera_id in stream_manager._streams:
        stream_manager._streams[camera_id].zone_config = config
    return {"ok": True}
