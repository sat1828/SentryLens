"""
All ORM models + shared constants for SentryLens.
Keeping VIOLATION_LABELS and VIOLATION_SEVERITY here avoids circular imports
— all services import from models, not from each other.
"""
from datetime import datetime, timezone
from typing import Optional, List
import enum
from sqlalchemy import (
    String, Boolean, Float, Integer, DateTime, ForeignKey,
    Text, Index, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── Enums ─────────────────────────────────────────────────────────

class ViolationType(str, enum.Enum):
    MISSING_HELMET    = "missing_helmet"
    MISSING_VEST      = "missing_vest"
    MISSING_HARNESS   = "missing_harness"
    RESTRICTED_ZONE   = "restricted_zone"
    SCAFFOLD_OVERCROWD = "scaffold_overcrowd"
    NEAR_MISS         = "near_miss"


class AlertStatus(str, enum.Enum):
    PENDING = "pending"
    SENT    = "sent"
    FAILED  = "failed"


class CameraStatus(str, enum.Enum):
    ONLINE   = "online"
    OFFLINE  = "offline"
    DEGRADED = "degraded"


class Severity(str, enum.Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


# ─── Shared lookup tables (imported by services) ─────────────────

VIOLATION_LABELS: dict[ViolationType, str] = {
    ViolationType.MISSING_HELMET:     "Missing helmet",
    ViolationType.MISSING_VEST:       "Missing hi-vis vest",
    ViolationType.MISSING_HARNESS:    "Missing harness",
    ViolationType.RESTRICTED_ZONE:    "Restricted zone entry",
    ViolationType.SCAFFOLD_OVERCROWD: "Scaffold overcrowding",
    ViolationType.NEAR_MISS:          "Near-miss incident",
}

VIOLATION_SEVERITY: dict[ViolationType, Severity] = {
    ViolationType.MISSING_HELMET:     Severity.HIGH,
    ViolationType.MISSING_VEST:       Severity.MEDIUM,
    ViolationType.MISSING_HARNESS:    Severity.CRITICAL,
    ViolationType.RESTRICTED_ZONE:    Severity.HIGH,
    ViolationType.SCAFFOLD_OVERCROWD: Severity.HIGH,
    ViolationType.NEAR_MISS:          Severity.CRITICAL,
}


# ─── ORM Models ────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id:               Mapped[int]           = mapped_column(Integer, primary_key=True)
    email:            Mapped[str]           = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password:  Mapped[str]           = mapped_column(String(255), nullable=False)
    full_name:        Mapped[str]           = mapped_column(String(255), nullable=False)
    phone:            Mapped[Optional[str]] = mapped_column(String(20))
    is_active:        Mapped[bool]          = mapped_column(Boolean, default=True)
    is_admin:         Mapped[bool]          = mapped_column(Boolean, default=False)
    created_at:       Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)

    alerts: Mapped[List["Alert"]] = relationship("Alert", back_populates="recipient_user", foreign_keys="Alert.recipient_user_id")


class Camera(Base):
    __tablename__ = "cameras"

    id:             Mapped[int]            = mapped_column(Integer, primary_key=True)
    name:           Mapped[str]            = mapped_column(String(100), nullable=False)
    rtsp_url:       Mapped[str]            = mapped_column(String(500), nullable=False)
    site_id:        Mapped[int]            = mapped_column(Integer, nullable=False, index=True)
    zone:           Mapped[str]            = mapped_column(String(100), default="General")
    location_label: Mapped[str]            = mapped_column(String(200), default="")
    gps_coords:     Mapped[Optional[dict]] = mapped_column(JSON)
    status:         Mapped[str]            = mapped_column(String(20), default=CameraStatus.OFFLINE.value)
    config:         Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    is_active:      Mapped[bool]           = mapped_column(Boolean, default=True)
    last_seen:      Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at:     Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=utcnow)

    violations: Mapped[List["Violation"]] = relationship("Violation", back_populates="camera")
    alerts:     Mapped[List["Alert"]]     = relationship("Alert", back_populates="camera")


class Violation(Base):
    __tablename__ = "violations"

    id:               Mapped[int]            = mapped_column(Integer, primary_key=True)
    camera_id:        Mapped[int]            = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    violation_type:   Mapped[str]            = mapped_column(String(50), nullable=False, index=True)
    confidence:       Mapped[float]          = mapped_column(Float, nullable=False)
    severity:         Mapped[str]            = mapped_column(String(20), nullable=False)
    bounding_box:     Mapped[Optional[list]] = mapped_column(JSON)
    frame_detections: Mapped[Optional[dict]] = mapped_column(JSON)
    snapshot_path:    Mapped[Optional[str]]  = mapped_column(String(500))
    worker_id:        Mapped[Optional[str]]  = mapped_column(String(100), index=True)
    zone_label:       Mapped[Optional[str]]  = mapped_column(String(100))
    acknowledged:     Mapped[bool]           = mapped_column(Boolean, default=False)
    acknowledged_by:  Mapped[Optional[int]]  = mapped_column(ForeignKey("users.id"))
    acknowledged_at:  Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    timestamp:        Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    camera: Mapped["Camera"]    = relationship("Camera", back_populates="violations")
    alerts: Mapped[List["Alert"]] = relationship("Alert", back_populates="violation")

    __table_args__ = (
        Index("ix_violations_camera_ts", "camera_id", "timestamp"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id:                Mapped[int]            = mapped_column(Integer, primary_key=True)
    violation_id:      Mapped[int]            = mapped_column(ForeignKey("violations.id"), nullable=False, index=True)
    camera_id:         Mapped[int]            = mapped_column(ForeignKey("cameras.id"), nullable=False)
    recipient_user_id: Mapped[Optional[int]]  = mapped_column(ForeignKey("users.id"))
    recipient_phone:   Mapped[str]            = mapped_column(String(20), nullable=False)
    status:            Mapped[str]            = mapped_column(String(20), default=AlertStatus.PENDING.value)
    twilio_sid:        Mapped[Optional[str]]  = mapped_column(String(100))
    error_message:     Mapped[Optional[str]]  = mapped_column(Text)
    message_body:      Mapped[str]            = mapped_column(Text, nullable=False)
    sent_at:           Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at:        Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=utcnow)

    violation:      Mapped["Violation"]     = relationship("Violation", back_populates="alerts")
    camera:         Mapped["Camera"]        = relationship("Camera", back_populates="alerts")
    recipient_user: Mapped[Optional["User"]] = relationship("User", back_populates="alerts", foreign_keys=[recipient_user_id])


class ComplianceReport(Base):
    __tablename__ = "compliance_reports"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    site_id:      Mapped[int]      = mapped_column(Integer, nullable=False, index=True)
    report_date:  Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period:       Mapped[str]      = mapped_column(String(20), nullable=False)
    summary:      Mapped[dict]     = mapped_column(JSON, nullable=False, default=dict)
    pdf_path:     Mapped[Optional[str]] = mapped_column(String(500))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    generated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
