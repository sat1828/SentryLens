"""Violations API"""
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select, desc, and_, func
from pydantic import BaseModel

from app.core.deps import CurrentUser, DB
from app.models.models import Violation, ViolationType, Severity, Camera

router = APIRouter(prefix="/violations", tags=["violations"])


class ViolationResponse(BaseModel):
    id:             int
    camera_id:      int
    violation_type: str
    confidence:     float
    severity:       str
    bounding_box:   Optional[list]
    snapshot_path:  Optional[str]
    worker_id:      Optional[str]
    zone_label:     Optional[str]
    acknowledged:   bool
    timestamp:      datetime
    model_config    = {"from_attributes": True}


@router.get("/", response_model=List[ViolationResponse])
async def list_violations(
    camera_id:      Optional[int]  = None,
    violation_type: Optional[str]  = None,
    acknowledged:   Optional[bool] = None,
    since:          Optional[datetime] = None,
    limit:          int = Query(default=50, le=500),
    offset:         int = 0,
    current_user:   CurrentUser = None,
    db:             DB = None,
):
    q = select(Violation).order_by(desc(Violation.timestamp))
    if camera_id:      q = q.where(Violation.camera_id == camera_id)
    if violation_type: q = q.where(Violation.violation_type == violation_type)
    if acknowledged is not None: q = q.where(Violation.acknowledged == acknowledged)
    if since:          q = q.where(Violation.timestamp >= since)
    q = q.limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.patch("/{violation_id}/acknowledge", response_model=ViolationResponse)
async def acknowledge_violation(violation_id: int, current_user: CurrentUser, db: DB):
    result = await db.execute(select(Violation).where(Violation.id == violation_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Violation not found")
    v.acknowledged    = True
    v.acknowledged_by = current_user.id
    v.acknowledged_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(v)
    return v


@router.get("/stats")
async def violation_stats(
    site_id: Optional[int] = None,
    days:    int = Query(default=7, le=90),
    current_user: CurrentUser = None,
    db:      DB = None,
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = select(Violation.violation_type, func.count(Violation.id).label("count"))
    q = q.where(Violation.timestamp >= since)

    if site_id:
        cam_q   = select(Camera.id).where(Camera.site_id == site_id)
        cam_res = await db.execute(cam_q)
        cam_ids = [r[0] for r in cam_res.fetchall()]
        if cam_ids:
            q = q.where(Violation.camera_id.in_(cam_ids))

    q      = q.group_by(Violation.violation_type)
    result = await db.execute(q)
    return {row.violation_type: row.count for row in result.fetchall()}
