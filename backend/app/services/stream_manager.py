"""
Stream Manager — concurrent RTSP ingestion with auto-reconnect.
FIX BUG-9:  asyncio.get_running_loop() replaces deprecated get_event_loop()
FIX BUG-19: global_alert_callbacks list — new cameras push to all alert WS clients
"""
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Callable, List

import cv2
from loguru import logger

from app.core.config import settings
from app.models.models import CameraStatus


@dataclass
class StreamState:
    camera_id:            int
    rtsp_url:             str
    zone_config:          dict
    frame_count:          int   = 0
    inference_count:      int   = 0
    last_frame_at:        Optional[datetime] = None
    status:               str   = CameraStatus.OFFLINE.value
    consecutive_failures: int   = 0
    reconnect_delay:      float = 2.0


class StreamManager:
    def __init__(self):
        self._streams:   Dict[int, StreamState] = {}
        self._tasks:     Dict[int, asyncio.Task] = {}
        self._callbacks: Dict[int, list]         = defaultdict(list)
        # BUG-19 FIX: global alert callbacks receive events from ALL cameras
        # including ones added after client connected
        self.global_alert_callbacks: List[Callable] = []
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("StreamManager started.")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks.values():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("StreamManager stopped.")

    async def add_camera(
        self, camera_id: int, rtsp_url: str, zone_config: Optional[dict] = None
    ) -> None:
        if camera_id in self._tasks and not self._tasks[camera_id].done():
            await self.remove_camera(camera_id)
        state = StreamState(
            camera_id=camera_id, rtsp_url=rtsp_url, zone_config=zone_config or {}
        )
        self._streams[camera_id] = state
        self._tasks[camera_id]   = asyncio.create_task(
            self._stream_loop(state), name=f"stream-cam-{camera_id}"
        )
        # BUG-19 FIX: wire new camera to all live alert WebSocket clients
        for cb in self.global_alert_callbacks:
            self.subscribe(camera_id, cb)
        logger.info(f"Camera {camera_id} stream started.")

    async def remove_camera(self, camera_id: int) -> None:
        if camera_id in self._tasks:
            self._tasks[camera_id].cancel()
            try:
                await asyncio.wait_for(self._tasks[camera_id], timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            del self._tasks[camera_id]
        self._streams.pop(camera_id, None)
        self._callbacks.pop(camera_id, None)

    def subscribe(self, camera_id: int, cb: Callable) -> None:
        if cb not in self._callbacks[camera_id]:
            self._callbacks[camera_id].append(cb)

    def unsubscribe(self, camera_id: int, cb: Callable) -> None:
        cbs = self._callbacks.get(camera_id, [])
        if cb in cbs:
            cbs.remove(cb)

    def get_all_statuses(self) -> Dict[int, dict]:
        return {
            cid: {
                "status":          s.status,
                "frame_count":     s.frame_count,
                "inference_count": s.inference_count,
                "last_frame_at":   s.last_frame_at.isoformat() if s.last_frame_at else None,
            }
            for cid, s in self._streams.items()
        }

    async def _stream_loop(self, state: StreamState) -> None:
        while self._running:
            loop = asyncio.get_running_loop()   # BUG-9 FIX
            cap  = await loop.run_in_executor(None, self._open_cap, state.rtsp_url)
            if cap is None:
                await self._backoff(state)
                continue
            state.status               = CameraStatus.ONLINE.value
            state.consecutive_failures = 0
            state.reconnect_delay      = 2.0
            logger.info(f"Camera {state.camera_id}: connected.")
            try:
                await self._read_loop(cap, state)
            except asyncio.CancelledError:
                cap.release()
                raise
            except Exception as e:
                logger.error(f"Camera {state.camera_id}: {e}")
            finally:
                cap.release()
                state.status = CameraStatus.OFFLINE.value
            await self._backoff(state)

    def _open_cap(self, url: str) -> Optional[cv2.VideoCapture]:
        cap = cv2.VideoCapture(url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap if cap.isOpened() else None

    async def _read_loop(self, cap: cv2.VideoCapture, state: StreamState) -> None:
        from app.services.detector import detector
        loop = asyncio.get_running_loop()   # BUG-9 FIX
        while self._running:
            ret, frame = await loop.run_in_executor(None, cap.read)
            if not ret or frame is None:
                state.consecutive_failures += 1
                if state.consecutive_failures > 30:
                    return
                await asyncio.sleep(0.05)
                continue

            state.consecutive_failures = 0
            state.frame_count         += 1
            state.last_frame_at        = datetime.now(timezone.utc)

            if state.frame_count % settings.INFERENCE_EVERY_N_FRAMES != 0:
                continue

            h, w = frame.shape[:2]
            if w > 1280:
                frame = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)

            result = await detector.infer(
                frame=frame,
                camera_id=state.camera_id,
                frame_id=state.frame_count,
                restricted_zone_polygons=state.zone_config.get("zones"),
                overcrowd_threshold=state.zone_config.get(
                    "overcrowd_threshold", settings.SCAFFOLD_OVERCROWD_THRESHOLD
                ),
            )
            state.inference_count += 1

            cbs = list(self._callbacks.get(state.camera_id, []))
            if cbs:
                await asyncio.gather(*[cb(result) for cb in cbs], return_exceptions=True)

    async def _backoff(self, state: StreamState) -> None:
        delay = min(state.reconnect_delay, 60.0)
        logger.info(f"Camera {state.camera_id}: reconnecting in {delay:.1f}s")
        await asyncio.sleep(delay)
        state.reconnect_delay = min(state.reconnect_delay * 1.5, 60.0)


stream_manager = StreamManager()
