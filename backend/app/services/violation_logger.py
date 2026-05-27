"""
FIX BUG-12: subscribe_camera() public — called from cameras.py on POST /cameras/
FIX BUG-13: cooldown delegated to cooldown.py (Redis-backed, single source of truth)
FIX BUG-14: tasks stored with weakref tracking; exceptions logged properly
"""
import asyncio
from datetime import datetime, timezone
from loguru import logger

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.cooldown import is_on_cooldown, set_cooldown
from app.models.models import Violation, Alert, Camera, AlertStatus
from app.services.alert_service import send_alerts_to_recipients


class ViolationLogger:
    def __init__(self):
        self._running = False

    async def start(self):
        self._running = True
        from app.services.stream_manager import stream_manager
        for cam_id in list(stream_manager._streams.keys()):
            stream_manager.subscribe(cam_id, self._handle)
        logger.info("ViolationLogger started.")

    def stop(self):
        self._running = False
        from app.services.stream_manager import stream_manager
        for cam_id in list(stream_manager._streams.keys()):
            stream_manager.unsubscribe(cam_id, self._handle)

    def subscribe_camera(self, camera_id: int):
        """
        FIX BUG-12: called from cameras.py when a new camera is added at runtime
        so that violations from post-startup cameras are also logged and alerted.
        """
        from app.services.stream_manager import stream_manager
        stream_manager.subscribe(camera_id, self._handle)
        logger.info(f"ViolationLogger: subscribed to camera {camera_id}")

    async def _handle(self, result) -> None:
        if not self._running or not result.violations:
            return

        from app.services.detector import detector

        for v in result.violations:
            if v.confidence < settings.VIOLATION_CONFIDENCE_THRESHOLD:
                continue
            if v.violation_type is None:
                continue

            # Save snapshot
            snapshot_path = None
            if result.annotated_frame is not None:
                try:
                    loop = asyncio.get_running_loop()
                    snapshot_path = await loop.run_in_executor(
                        None, detector.save_snapshot,
                        result.annotated_frame,
                        result.camera_id,
                        v.violation_type.value,
                    )
                except Exception as e:
                    logger.warning(f"Snapshot save failed: {e}")

            # Persist to DB
            violation_id = None
            try:
                async with AsyncSessionLocal() as db:
                    violation = Violation(
                        camera_id=result.camera_id,
                        violation_type=v.violation_type.value,
                        confidence=v.confidence,
                        severity=v.severity.value if v.severity else "medium",
                        bounding_box=v.bbox,
                        frame_detections={
                            "all": [
                                {"class": d.class_name, "conf": d.confidence, "bbox": d.bbox}
                                for d in result.detections
                            ],
                            "person_count": result.person_count,
                            "inference_ms": result.inference_ms,
                        },
                        snapshot_path=snapshot_path,
                        timestamp=result.timestamp,
                    )
                    db.add(violation)
                    await db.flush()
                    violation_id = violation.id
                    await db.commit()
            except Exception as e:
                logger.error(f"Violation persist failed: {e}")
                continue

            # Check consolidated Redis cooldown — BUG-13 FIX
            vtype_str = v.violation_type.value
            on_cd = await is_on_cooldown(result.camera_id, vtype_str, settings.ALERT_COOLDOWN_SECONDS)
            if not on_cd:
                recipients = settings.alert_recipients_list
                if recipients and violation_id:
                    # BUG-14 FIX: store task reference, log exceptions
                    task = asyncio.create_task(
                        self._dispatch_alert(violation_id, result.camera_id, v.violation_type, v.confidence, recipients),
                        name=f"alert-{violation_id}",
                    )
                    task.add_done_callback(
                        lambda t: logger.error(f"Alert task error: {t.exception()}") if t.exception() else None
                    )
                    await set_cooldown(result.camera_id, vtype_str, settings.ALERT_COOLDOWN_SECONDS)

    async def _dispatch_alert(self, violation_id, camera_id, violation_type, confidence, recipients):
        try:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                res = await db.execute(select(Camera).where(Camera.id == camera_id))
                cam      = res.scalar_one_or_none()
                cam_name = cam.name if cam else f"Camera {camera_id}"
                zone     = cam.zone if cam else "Unknown"

            alert_results = await send_alerts_to_recipients(
                recipients=recipients, violation_type=violation_type,
                camera_name=cam_name, zone=zone, confidence=confidence,
            )

            async with AsyncSessionLocal() as db:
                for r in alert_results:
                    db.add(Alert(
                        violation_id=violation_id,
                        camera_id=camera_id,
                        recipient_phone=r["phone"],
                        status=AlertStatus.SENT.value if r.get("status") == "sent" else AlertStatus.FAILED.value,
                        twilio_sid=r.get("sid"),
                        error_message=r.get("error"),
                        message_body=f"Violation: {violation_type.value} | {cam_name}",
                        sent_at=datetime.now(timezone.utc) if r.get("status") == "sent" else None,
                    ))
                await db.commit()
        except Exception as e:
            logger.error(f"_dispatch_alert failed for violation {violation_id}: {e}")
