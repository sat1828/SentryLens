"""
FIX BUG-28: acknowledged count uses proper SQLAlchemy expressions, not Python False.
FIX BUG-29: per-camera breakdown added to PDF.
FIX BUG-31: acknowledged field populated correctly.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from loguru import logger
from app.core.config import settings


async def generate_daily_report(db, site_id: int, report_date: Optional[datetime] = None) -> dict:
    from sqlalchemy import select, func, and_
    from app.models.models import Violation, Camera

    if report_date is None:
        report_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    next_day = report_date + timedelta(days=1)

    cam_res    = await db.execute(select(Camera.id, Camera.name).where(Camera.site_id == site_id))
    cam_rows   = cam_res.fetchall()
    camera_ids = [r[0] for r in cam_rows]

    by_type: dict = {}
    by_camera: dict = {}
    total = acknowledged = 0

    if camera_ids:
        # Violation counts by type
        type_res = await db.execute(
            select(Violation.violation_type, func.count(Violation.id).label("cnt"))
            .where(and_(
                Violation.camera_id.in_(camera_ids),
                Violation.timestamp >= report_date,
                Violation.timestamp < next_day,
            ))
            .group_by(Violation.violation_type)
        )
        by_type = {row.violation_type: row.cnt for row in type_res.fetchall()}
        total   = sum(by_type.values())

        # BUG-28 FIX: acknowledged count — no Python False in WHERE
        acked_res   = await db.execute(
            select(func.count(Violation.id)).where(and_(
                Violation.camera_id.in_(camera_ids),
                Violation.timestamp >= report_date,
                Violation.timestamp < next_day,
                Violation.acknowledged == True,
            ))
        )
        acknowledged = acked_res.scalar() or 0

        # BUG-29 FIX: per-camera breakdown
        for cam_id, cam_name in cam_rows:
            cam_count_res = await db.execute(
                select(func.count(Violation.id)).where(and_(
                    Violation.camera_id == cam_id,
                    Violation.timestamp >= report_date,
                    Violation.timestamp < next_day,
                ))
            )
            by_camera[cam_name] = cam_count_res.scalar() or 0

    return {
        "site_id":           site_id,
        "report_date":       report_date.isoformat(),
        "period":            "daily",
        "total_violations":  total,
        "acknowledged":      acknowledged,      # BUG-31 FIX: real value
        "open":              total - acknowledged,
        "by_type":           by_type,
        "by_camera":         by_camera,          # BUG-29 FIX: per-camera data
        "camera_count":      len(camera_ids),
        "generated_at":      datetime.now(timezone.utc).isoformat(),
    }


def render_pdf_report(summary: dict, output_path: str) -> str:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        doc    = SimpleDocTemplate(output_path, pagesize=A4,
                                   rightMargin=2*cm, leftMargin=2*cm,
                                   topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story  = []
        hdr    = colors.HexColor("#1e3a5f")

        def make_table(rows, col_widths):
            t = Table(rows, colWidths=col_widths)
            t.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),  (-1,0), hdr),
                ("TEXTCOLOR",     (0,0),  (-1,0), colors.white),
                ("FONTNAME",      (0,0),  (-1,0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS",(0,1),  (-1,-1),[colors.white, colors.HexColor("#f4f4f4")]),
                ("GRID",          (0,0),  (-1,-1), 0.5, colors.HexColor("#cccccc")),
                ("FONTSIZE",      (0,0),  (-1,-1), 10),
                ("PADDING",       (0,0),  (-1,-1), 6),
            ]))
            return t

        story.append(Paragraph("SentryLens — Daily Compliance Report", styles["Title"]))
        story.append(Paragraph(
            f"Site: {summary['site_id']} | Date: {summary['report_date'][:10]} | "
            f"Generated: {summary['generated_at'][:19]} UTC", styles["Normal"]))
        story.append(Spacer(1, 0.5*cm))
        story.append(HRFlowable(width="100%", thickness=1))
        story.append(Spacer(1, 0.5*cm))

        story.append(Paragraph("Summary", styles["Heading2"]))
        story.append(make_table([
            ["Metric", "Value"],
            ["Total violations",  str(summary["total_violations"])],
            ["Acknowledged",      str(summary["acknowledged"])],
            ["Open / unresolved", str(summary["open"])],
            ["Cameras monitored", str(summary["camera_count"])],
        ], [10*cm, 6*cm]))
        story.append(Spacer(1, 0.8*cm))

        story.append(Paragraph("Violation Breakdown by Type", styles["Heading2"]))
        type_rows = [["Violation Type", "Count"]]
        for vtype, count in summary.get("by_type", {}).items():
            type_rows.append([str(vtype).replace("_"," ").title(), str(count)])
        if len(type_rows) > 1:
            story.append(make_table(type_rows, [12*cm, 4*cm]))
        story.append(Spacer(1, 0.8*cm))

        # BUG-29 FIX: per-camera section
        by_camera = summary.get("by_camera", {})
        if by_camera:
            story.append(Paragraph("Violations per Camera", styles["Heading2"]))
            cam_rows = [["Camera", "Count"]]
            for name, cnt in sorted(by_camera.items(), key=lambda x: -x[1]):
                cam_rows.append([name, str(cnt)])
            story.append(make_table(cam_rows, [12*cm, 4*cm]))
            story.append(Spacer(1, 0.8*cm))

        story.append(HRFlowable(width="100%", thickness=0.5))
        story.append(Spacer(1, 0.3*cm))
        footer = ParagraphStyle("footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
        story.append(Paragraph(
            "SentryLens AI-assisted monitoring. Human review required for compliance decisions.", footer))
        doc.build(story)
        logger.info(f"PDF written: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        return ""
