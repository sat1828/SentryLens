"""
Celery tasks.
FIX BUG-31: acknowledged count now queries DB, not hardcoded 0.
FIX BUG-30: engine created once at module level, not per-task.
"""
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

app = Celery("sentrylens")
app.config_from_object({
    "broker_url":        settings.CELERY_BROKER_URL,
    "result_backend":    settings.CELERY_RESULT_BACKEND,
    "task_serializer":   "json",
    "result_serializer": "json",
    "accept_content":    ["json"],
    "timezone":          "UTC",
    "enable_utc":        True,
    "beat_schedule": {
        "daily-reports":     {"task": "app.workers.tasks.generate_daily_reports",
                              "schedule": crontab(hour=0, minute=5)},
        "cleanup-snapshots": {"task": "app.workers.tasks.cleanup_snapshots",
                              "schedule": crontab(hour=2, minute=0)},
    },
})

# BUG-30 FIX: module-level engine — connection pool reused across task calls
_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine
        _engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    return _engine


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_daily_reports(self, site_ids: list = None):
    """BUG-31 FIX: acknowledged count queried from DB."""
    from sqlalchemy.orm import Session
    from sqlalchemy import select, func, and_
    from datetime import datetime, timezone, timedelta
    from pathlib import Path
    from app.models.models import Camera, Violation, ComplianceReport
    from app.services.report_service import render_pdf_report
    from loguru import logger

    try:
        engine = _get_engine()
        with Session(engine) as db:
            if site_ids is None:
                rows     = db.execute(select(Camera.site_id).distinct()).fetchall()
                site_ids = [r[0] for r in rows]

            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            next_day  = yesterday + timedelta(days=1)

            for site_id in site_ids:
                cam_rows = db.execute(
                    select(Camera.id, Camera.name).where(Camera.site_id == site_id)
                ).fetchall()
                cam_ids = [r[0] for r in cam_rows]
                if not cam_ids:
                    continue

                by_type = {}
                for row in db.execute(
                    select(Violation.violation_type, func.count(Violation.id).label("cnt"))
                    .where(and_(
                        Violation.camera_id.in_(cam_ids),
                        Violation.timestamp >= yesterday,
                        Violation.timestamp < next_day,
                    ))
                    .group_by(Violation.violation_type)
                ).fetchall():
                    by_type[row.violation_type] = row.cnt

                # BUG-31 FIX: real acknowledged count
                acked = db.execute(
                    select(func.count(Violation.id)).where(and_(
                        Violation.camera_id.in_(cam_ids),
                        Violation.timestamp >= yesterday,
                        Violation.timestamp < next_day,
                        Violation.acknowledged == True,
                    ))
                ).scalar() or 0

                # Per-camera breakdown
                by_camera = {}
                for cam_id, cam_name in cam_rows:
                    cnt = db.execute(
                        select(func.count(Violation.id)).where(and_(
                            Violation.camera_id == cam_id,
                            Violation.timestamp >= yesterday,
                            Violation.timestamp < next_day,
                        ))
                    ).scalar() or 0
                    by_camera[cam_name] = cnt

                total   = sum(by_type.values())
                summary = {
                    "site_id": site_id, "report_date": yesterday.isoformat(),
                    "period": "daily", "total_violations": total,
                    "acknowledged": acked, "open": total - acked,
                    "by_type": by_type, "by_camera": by_camera,
                    "camera_count": len(cam_ids),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }

                pdf_dir  = Path(settings.SNAPSHOT_DIR).parent / "reports"
                pdf_dir.mkdir(parents=True, exist_ok=True)
                pdf_path = str(pdf_dir / f"site{site_id}_{yesterday.strftime('%Y%m%d')}.pdf")
                render_pdf_report(summary, pdf_path)

                db.add(ComplianceReport(
                    site_id=site_id, report_date=yesterday, period="daily",
                    summary=summary, pdf_path=pdf_path,
                ))
                db.commit()
                logger.info(f"Daily report site {site_id}: {pdf_path}")
    except Exception as exc:
        raise self.retry(exc=exc)


@app.task
def cleanup_snapshots():
    from pathlib import Path
    from datetime import datetime, timezone, timedelta
    from loguru import logger
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.MAX_SNAPSHOT_AGE_DAYS)
    root, deleted = Path(settings.SNAPSHOT_DIR), 0
    if root.exists():
        for p in root.rglob("*.jpg"):
            try:
                if datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc) < cutoff:
                    p.unlink(); deleted += 1
            except Exception:
                pass
    logger.info(f"Snapshot cleanup: {deleted} files deleted.")


@app.task(bind=True, max_retries=2)
def dispatch_sms_alert(self, to_number: str, message: str):
    try:
        if not settings.TWILIO_ACCOUNT_SID:
            return {"status": "skipped"}
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg    = client.messages.create(body=message, from_=settings.TWILIO_FROM_NUMBER, to=to_number)
        return {"status": "sent", "sid": msg.sid}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
