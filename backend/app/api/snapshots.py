"""
FIX BUG-36: authenticated snapshot serving — removes publicly accessible StaticFiles mount.
Prevents path traversal via Path.resolve() check.
"""
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.deps import CurrentUser
from app.core.config import settings

router = APIRouter(prefix="/snapshots", tags=["snapshots"])

_SNAP_ROOT = Path(settings.SNAPSHOT_DIR).resolve()


@router.get("/{path:path}")
async def serve_snapshot(path: str, current_user: CurrentUser):
    # BUG-36 FIX: resolve and validate — prevent path traversal
    requested = (_SNAP_ROOT / path).resolve()
    if not str(requested).startswith(str(_SNAP_ROOT)):
        raise HTTPException(400, "Invalid path")
    if not requested.exists() or not requested.is_file():
        raise HTTPException(404, "Snapshot not found")
    return FileResponse(str(requested), media_type="image/jpeg")
