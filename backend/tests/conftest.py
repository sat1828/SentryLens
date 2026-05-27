"""
Test fixtures — async SQLite in-memory, per-test DB rollback, JWT auth helpers.
"""
import asyncio
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

os.environ["APP_ENV"]             = "test"
os.environ["DATABASE_URL"]        = "sqlite+aiosqlite:///:memory:"
os.environ["DATABASE_URL_SYNC"]   = "sqlite:///./test_tmp.db"
os.environ["SECRET_KEY"]          = "test-secret-key-at-least-32-chars-long"
os.environ["TWILIO_ACCOUNT_SID"]  = ""
os.environ["TWILIO_AUTH_TOKEN"]   = ""
os.environ["MODEL_PATH"]          = "/nonexistent/model.pt"
os.environ["SNAPSHOT_DIR"]        = "/tmp/sl_test_snapshots"
os.environ["REDIS_URL"]           = "redis://localhost:6379/15"
os.environ["CELERY_BROKER_URL"]   = "redis://localhost:6379/15"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/15"

from app.core.database import Base, get_db
from app.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop   = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(
        TEST_DB_URL, echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine):
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session):
    from app.models.models import User
    from app.core.security import hash_password
    user = User(
        email="admin@test.io", hashed_password=hash_password("TestPass123!"),
        full_name="Test Admin", phone="+919999999999", is_active=True, is_admin=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def auth_headers(client, admin_user):
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": admin_user.email, "password": "TestPass123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, f"Login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest_asyncio.fixture(scope="function")
async def test_camera(db_session):
    from app.models.models import Camera, CameraStatus
    cam = Camera(
        name="Test CAM-01", rtsp_url="rtsp://test:554/stream1",
        site_id=1, zone="Zone A", location_label="Test",
        status=CameraStatus.ONLINE.value, config={"overcrowd_threshold": 6},
    )
    db_session.add(cam)
    await db_session.flush()
    await db_session.refresh(cam)
    return cam
