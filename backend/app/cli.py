#!/usr/bin/env python3
"""
SentryLens CLI
──────────────
Administrative commands for setup, maintenance, and debugging.

Usage:
  python -m app.cli create-admin
  python -m app.cli list-cameras
  python -m app.cli check-model
  python -m app.cli seed-demo --site-id 1
  python -m app.cli purge-snapshots --older-than 90
"""

import asyncio
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path


def get_db_session():
    """Synchronous DB session for CLI use."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import settings
    engine = create_engine(settings.DATABASE_URL_SYNC)
    return Session(engine), engine


async def get_async_db():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        return db


# ─── create-admin ─────────────────────────────────────────────────────────────

def cmd_create_admin(args):
    """Interactively create the first admin user."""
    import getpass
    from app.models.models import User
    from app.core.security import hash_password

    email = input("Admin email: ").strip()
    name = input("Full name: ").strip()
    phone = input("Phone (optional, e.g. +919XXXXXXXXX): ").strip() or None
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("ERROR: Passwords do not match.")
        sys.exit(1)
    if len(password) < 8:
        print("ERROR: Password must be at least 8 characters.")
        sys.exit(1)

    db, engine = get_db_session()
    from sqlalchemy import select
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        print(f"ERROR: User {email} already exists.")
        db.close()
        sys.exit(1)

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=name,
        phone=phone,
        is_active=True,
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.close()
    print(f"✓ Admin user created: {email}")


# ─── list-cameras ─────────────────────────────────────────────────────────────

def cmd_list_cameras(args):
    from app.models.models import Camera
    from sqlalchemy import select

    db, _ = get_db_session()
    cameras = db.execute(select(Camera).where(Camera.is_active == True)).scalars().all()
    db.close()

    if not cameras:
        print("No cameras registered.")
        return

    print(f"\n{'ID':>4}  {'Name':<25} {'Zone':<20} {'Status':<12} {'RTSP URL'}")
    print("─" * 100)
    for cam in cameras:
        print(f"{cam.id:>4}  {cam.name:<25} {cam.zone:<20} {cam.status:<12} {cam.rtsp_url}")


# ─── check-model ──────────────────────────────────────────────────────────────

def cmd_check_model(args):
    from app.core.config import settings
    import os

    print(f"Model path configured: {settings.MODEL_PATH}")
    if os.path.exists(settings.MODEL_PATH):
        size_mb = os.path.getsize(settings.MODEL_PATH) / 1e6
        print(f"✓ Model file found ({size_mb:.1f} MB)")
        print(f"  Loading and running warm-up inference...")
        try:
            from ultralytics import YOLO
            import numpy as np
            model = YOLO(settings.MODEL_PATH)
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            result = model(dummy, verbose=False)
            print(f"✓ Model loaded. Classes: {list(model.names.values())}")
        except Exception as e:
            print(f"✗ Model load failed: {e}")
    else:
        print(f"✗ Model file NOT found at {settings.MODEL_PATH}")
        print(f"  Fallback model: {settings.FALLBACK_MODEL}")
        print(f"  Run: python ml/training/train.py --roboflow-key YOUR_KEY")
        print(f"  Then copy the output to {settings.MODEL_PATH}")


# ─── seed-demo ────────────────────────────────────────────────────────────────

def cmd_seed_demo(args):
    """Insert sample cameras and violations for demo/testing."""
    from app.models.models import Camera, Violation, ViolationType, Severity, CameraStatus

    demo_cameras = [
        {"name": "CAM-01 Entry gate",   "rtsp_url": "rtsp://demo:554/stream1",  "zone": "Zone A", "location_label": "Main entrance"},
        {"name": "CAM-02 Scaffold N",   "rtsp_url": "rtsp://demo:554/stream2",  "zone": "Zone B", "location_label": "North scaffold"},
        {"name": "CAM-03 Crane bay",    "rtsp_url": "rtsp://demo:554/stream3",  "zone": "Zone C", "location_label": "Crane operating area"},
        {"name": "CAM-04 Foundation",   "rtsp_url": "rtsp://demo:554/stream4",  "zone": "Zone D", "location_label": "Foundation level"},
    ]

    demo_violations = [
        (1, ViolationType.MISSING_HELMET, 0.91, Severity.HIGH),
        (2, ViolationType.MISSING_VEST,   0.78, Severity.MEDIUM),
        (1, ViolationType.RESTRICTED_ZONE, 0.95, Severity.HIGH),
        (2, ViolationType.SCAFFOLD_OVERCROWD, 1.0, Severity.HIGH),
        (4, ViolationType.MISSING_HELMET, 0.82, Severity.HIGH),
    ]

    db, _ = get_db_session()
    site_id = args.site_id

    # Cameras
    cam_ids = []
    for cd in demo_cameras:
        cam = Camera(site_id=site_id, status=CameraStatus.ONLINE.value, **cd)
        db.add(cam)
        db.flush()
        cam_ids.append(cam.id)
        print(f"  + Camera: {cd['name']} (id={cam.id})")

    # Violations
    now = datetime.now(timezone.utc)
    for i, (cam_idx, vtype, conf, sev) in enumerate(demo_violations):
        cam_id = cam_ids[cam_idx - 1] if cam_idx - 1 < len(cam_ids) else cam_ids[0]
        ts = now - timedelta(minutes=i * 15)
        v = Violation(camera_id=cam_id, violation_type=vtype, confidence=conf,
                      severity=sev, timestamp=ts, bounding_box=[0.1, 0.2, 0.5, 0.8])
        db.add(v)
        print(f"  + Violation: {vtype.value} @ cam {cam_id} (conf={conf})")

    db.commit()
    db.close()
    print(f"\n✓ Demo data seeded for site {site_id}.")
    print(f"  Open http://localhost:3000 and log in to see the data.")


# ─── purge-snapshots ─────────────────────────────────────────────────────────

def cmd_purge_snapshots(args):
    from app.core.config import settings

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.older_than)
    root = Path(settings.SNAPSHOT_DIR)
    deleted = 0
    freed_bytes = 0

    if not root.exists():
        print(f"Snapshot directory does not exist: {root}")
        return

    for p in root.rglob("*.jpg"):
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                size = p.stat().st_size
                p.unlink()
                deleted += 1
                freed_bytes += size
        except Exception as e:
            print(f"  WARN: Could not delete {p}: {e}")

    print(f"✓ Purged {deleted} snapshots older than {args.older_than} days ({freed_bytes / 1e6:.1f} MB freed)")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SentryLens CLI — Admin tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("create-admin", help="Create an admin user interactively")
    subparsers.add_parser("list-cameras", help="List all registered cameras")
    subparsers.add_parser("check-model",  help="Verify YOLOv8 model is loaded and working")

    seed_p = subparsers.add_parser("seed-demo", help="Insert demo cameras + violations")
    seed_p.add_argument("--site-id", type=int, default=1)

    purge_p = subparsers.add_parser("purge-snapshots", help="Delete old frame snapshots")
    purge_p.add_argument("--older-than", type=int, default=90, metavar="DAYS")

    args = parser.parse_args()

    commands = {
        "create-admin":    cmd_create_admin,
        "list-cameras":    cmd_list_cameras,
        "check-model":     cmd_check_model,
        "seed-demo":       cmd_seed_demo,
        "purge-snapshots": cmd_purge_snapshots,
    }

    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
