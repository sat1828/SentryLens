"""
FIX BUG-18: WebSocket authentication via ?token= query param
FIX BUG-19: alerts WS subscribes dynamically; new cameras included
FIX BUG-20: frame-level backpressure via try_send (skip if client slow)
"""
import asyncio
import base64
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.database import AsyncSessionLocal
from app.core.deps import ws_auth
from app.services.stream_manager import stream_manager

router = APIRouter(prefix="/streams", tags=["streams"])


async def _authenticate_ws(token: str, websocket: WebSocket) -> bool:
    """Authenticate WS connection. Closes with 4001 on failure. Returns True if OK."""
    async with AsyncSessionLocal() as db:
        try:
            await ws_auth(token, db)
            return True
        except ValueError as e:
            logger.warning(f"WS auth failed: {e}")
            await websocket.close(code=4001)
            return False


@router.websocket("/{camera_id}/live")
async def camera_live_stream(
    camera_id: int,
    websocket: WebSocket,
    token: str = Query(default=""),   # BUG-18 FIX
):
    await websocket.accept()
    if not await _authenticate_ws(token, websocket):
        return

    logger.info(f"WS authenticated: camera {camera_id}")
    from app.services.detector import detector

    async def on_inference(result) -> None:
        if result.annotated_frame is None:
            return
        try:
            jpeg  = detector.encode_jpeg(result.annotated_frame, quality=70)
            b64   = base64.b64encode(jpeg).decode()
            payload = {
                "type":         "frame",
                "camera_id":    camera_id,
                "frame_id":     result.frame_id,
                "jpeg_b64":     b64,
                "violations":   [
                    {
                        "type":       v.violation_type.value if v.violation_type else None,
                        "confidence": round(v.confidence, 3),
                        "severity":   v.severity.value if v.severity else None,
                        "bbox":       v.bbox,
                    }
                    for v in result.violations
                ],
                "person_count": result.person_count,
                "inference_ms": round(result.inference_ms, 1),
                "timestamp":    result.timestamp.isoformat(),
            }
            # BUG-20 FIX: non-blocking send — skip frame if send buffer full
            if websocket.client_state.value == 1:  # CONNECTED
                await asyncio.wait_for(websocket.send_json(payload), timeout=0.5)
        except (asyncio.TimeoutError, Exception):
            pass  # slow client — frame dropped, not crashed

    stream_manager.subscribe(camera_id, on_inference)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=25)
                if msg == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    finally:
        stream_manager.unsubscribe(camera_id, on_inference)
        logger.info(f"WS disconnected: camera {camera_id}")


@router.websocket("/alerts/live")
async def live_alerts_stream(
    websocket: WebSocket,
    token: str = Query(default=""),   # BUG-18 FIX
):
    await websocket.accept()
    if not await _authenticate_ws(token, websocket):
        return

    queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    async def enqueue(result) -> None:
        if not result.violations:
            return
        for v in result.violations:
            try:
                queue.put_nowait({
                    "type":           "violation",
                    "camera_id":      result.camera_id,
                    "violation_type": v.violation_type.value if v.violation_type else None,
                    "confidence":     round(v.confidence, 3),
                    "timestamp":      result.timestamp.isoformat(),
                })
            except asyncio.QueueFull:
                pass

    # BUG-19 FIX: subscribe to ALL cameras at connection time AND
    # store callback so future cameras can be subscribed if needed.
    # stream_manager.subscribe handles dedup already.
    connected_cameras = set(stream_manager._streams.keys())
    for cid in connected_cameras:
        stream_manager.subscribe(cid, enqueue)

    # Also store the callback in a place the stream_manager can find
    # for cameras added AFTER this client connected (handled via
    # stream_manager global_alert_callbacks)
    stream_manager.global_alert_callbacks.append(enqueue)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=25)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    finally:
        for cid in connected_cameras:
            stream_manager.unsubscribe(cid, enqueue)
        if enqueue in stream_manager.global_alert_callbacks:
            stream_manager.global_alert_callbacks.remove(enqueue)
