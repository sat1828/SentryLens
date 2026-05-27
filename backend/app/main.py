"""SentryLens — FastAPI Application Entry Point"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────
    logger.info(f"Starting {settings.APP_NAME} [{settings.APP_ENV}]")
    os.makedirs(settings.SNAPSHOT_DIR, exist_ok=True)

    from app.services.detector import detector
    await detector.load()

    from app.services.stream_manager import stream_manager
    await stream_manager.start()

    # Resume all active cameras from DB
    if settings.APP_ENV != "test":
        try:
            from app.core.database import AsyncSessionLocal
            from sqlalchemy import select
            from app.models.models import Camera
            async with AsyncSessionLocal() as db:
                result  = await db.execute(select(Camera).where(Camera.is_active == True))
                cameras = result.scalars().all()
                for cam in cameras:
                    try:
                        await stream_manager.add_camera(cam.id, cam.rtsp_url, cam.config or {})
                        logger.info(f"Resumed camera {cam.id}: {cam.name}")
                    except Exception as e:
                        logger.error(f"Failed to start camera {cam.id}: {e}")
        except Exception as e:
            logger.warning(f"Could not resume cameras: {e}")

    from app.services.violation_logger import ViolationLogger
    vlogger = ViolationLogger()
    await vlogger.start()
    app.state.violation_logger = vlogger

    logger.info("SentryLens startup complete.")
    yield

    # ── Shutdown ──────────────────────────────────────────────────
    logger.info("Shutting down...")
    if hasattr(app.state, "violation_logger"):
        app.state.violation_logger.stop()
    await stream_manager.stop()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SentryLens API",
        description="Real-Time Construction Site Safety AI",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.auth       import router as auth_router
    from app.api.cameras    import router as cameras_router
    from app.api.violations import router as violations_router
    from app.api.streams    import router as streams_router
    from app.api.reports    import router as reports_router
    from app.api.snapshots  import router as snapshots_router   # BUG-36 FIX
    from app.api.config_api import router as config_router      # settings page fix

    p = settings.API_V1_PREFIX
    app.include_router(auth_router,       prefix=p)
    app.include_router(cameras_router,    prefix=p)
    app.include_router(violations_router, prefix=p)
    app.include_router(streams_router,    prefix=p)
    app.include_router(reports_router,    prefix=p)
    app.include_router(snapshots_router,  prefix=p)  # BUG-36: authenticated, not StaticFiles
    app.include_router(config_router,     prefix=p)

    # NOTE: StaticFiles("/snapshots") deliberately REMOVED — BUG-36 FIX
    # All snapshot access goes through /api/v1/snapshots/{path} with auth

    @app.get("/health", tags=["health"])
    async def health():
        from app.services.stream_manager import stream_manager
        return {
            "status":         "ok",
            "app":            settings.APP_NAME,
            "env":            settings.APP_ENV,
            "active_streams": len(stream_manager._streams),
        }

    return app


app = create_app()
