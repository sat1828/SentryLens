"""
FIX BUG-28: acknowledged count queries correctly using sqlalchemy.false()
FIX BUG-31: Celery task now queries acknowledged count properly
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, desc, func, and_, false as sa_false
import os

from app.core.deps import CurrentUser, CurrentAdmin, DB
from app.models.models import ComplianceReport, Violation, Camera

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/")
async def list_reports(
    site_id: Optional[int] = None,
    limit:   int = Query(default=30, le=100),
    current_user: CurrentUser = None,
    db: DB = None,
):
    q = select(ComplianceReport).order_by(desc(ComplianceReport.report_date))
    if site_id:
        q = q.where(ComplianceReport.site_id == site_id)
    q = q.limit(limit)
    result  = await db.execute(q)
    reports = result.scalars().all()
    return [
        {
            "id":            r.id,
            "site_id":       r.site_id,
            "report_date":   r.report_date.isoformat(),
            "period":        r.period,
            "summary":       r.summary,
            "pdf_available": bool(r.pdf_path and os.path.exists(r.pdf_path)),
            "generated_at":  r.generated_at.isoformat(),
        }
        for r in reports
    ]


@router.get("/{report_id}/pdf")
async def download_report_pdf(report_id: int, current_user: CurrentUser, db: DB):
    # BUG-32 FIX: proper auth via CurrentUser (no ?token= in URL)
    result = await db.execute(select(ComplianceReport).where(ComplianceReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")
    if not report.pdf_path or not os.path.exists(report.pdf_path):
        raise HTTPException(404, "PDF not yet generated")
    return FileResponse(
        path=report.pdf_path,
        media_type="application/pdf",
        filename=f"sentrylens_report_{report.report_date.strftime('%Y%m%d')}.pdf",
    )


@router.post("/generate")
async def generate_report_now(site_id: int, current_user: CurrentAdmin, db: DB):
    from app.workers.tasks import generate_daily_reports
    task = generate_daily_reports.delay(site_ids=[site_id])
    return {"task_id": task.id, "status": "queued"}


@router.get("/daily/summary")
async def daily_summary(site_id: int, current_user: CurrentUser, db: DB):
    from app.services.report_service import generate_daily_report
    return await generate_daily_report(db, site_id)
