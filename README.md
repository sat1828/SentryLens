# SentryLens — Real-Time Construction Site Safety AI

> **Eyes on every site. Always.**

YOLOv8-powered PPE compliance monitoring. Connects to existing CCTV/IP cameras via RTSP, detects violations in real-time, alerts via SMS, and generates OSHA-ready compliance reports.

---

## What was fixed from the original review (31 bugs addressed)

| # | Severity | Fix |
|---|---|---|
| BUG-1  | HIGH     | Server refuses to start with default `SECRET_KEY` in production |
| BUG-3  | MEDIUM   | Malformed JWT sub → 401, not 500 |
| BUG-4,5| HIGH     | Harness/near-miss documented as undetectable with 10-class dataset |
| BUG-6  | LOW      | Inference threads scaled to `max(2, cpu_count//2)` |
| BUG-7  | MEDIUM   | Overcrowding checks polygon zones, not whole frame |
| BUG-9  | LOW      | `get_running_loop()` replaces deprecated `get_event_loop()` |
| BUG-12 | CRITICAL | `ViolationLogger.subscribe_camera()` called on POST /cameras/ |
| BUG-13 | MEDIUM   | Dual cooldown dicts unified into `cooldown.py` |
| BUG-14 | MEDIUM   | Celery task errors logged via callback |
| BUG-15 | HIGH     | Twilio call runs in `run_in_executor` — no longer blocks event loop |
| BUG-16 | HIGH     | `DASHBOARD_URL` config key replaces hardcoded localhost in SMS |
| BUG-17 | MEDIUM   | Cooldown backed by Redis — shared across uvicorn workers |
| BUG-18 | CRITICAL | WebSocket auth via `?token=` query param |
| BUG-19 | MEDIUM   | `global_alert_callbacks` — new cameras added to all alert WS clients |
| BUG-20 | MEDIUM   | `asyncio.wait_for(0.5s)` on WS send — drops slow client frames, not crashes |
| BUG-21 | HIGH     | `/register` gated by `REGISTRATION_OPEN` setting |
| BUG-22 | MEDIUM   | `POST /auth/refresh` endpoint implemented |
| BUG-23 | LOW      | `EmailStr` validates email format properly |
| BUG-24 | CRITICAL | Same as BUG-12 |
| BUG-25 | LOW      | RTSP URL schema validated (`rtsp://` or `rtsps://` only) |
| BUG-26 | LOW      | `limit`/`offset` pagination on camera list |
| BUG-27 | LOW      | Removed `= None` defaults on `Depends()` parameters |
| BUG-28 | MEDIUM   | Acknowledged count uses SQLAlchemy `True`, not Python `False` in WHERE |
| BUG-29 | MEDIUM   | Per-camera breakdown added to PDF and report summary |
| BUG-30 | LOW      | Celery task uses module-level engine (connection pool reuse) |
| BUG-31 | MEDIUM   | Celery daily report queries real acknowledged count |
| BUG-32 | HIGH     | PDF downloaded via `fetch`+blob — JWT never appears in URL |
| BUG-33 | MEDIUM   | `apiFetch` auto-refreshes access token on 401 |
| BUG-34 | LOW      | Canvas resized only on dimension change — no per-frame flicker |
| BUG-35 | LOW      | Single `Image` instance reused — no per-frame GC pressure |
| BUG-36 | CRITICAL | `/snapshots/` StaticFiles removed; authenticated `/api/v1/snapshots/{path}` added |
| BUG-37 | MEDIUM   | Alert list paginated (50/page) with Previous/Next controls |
| CSS    | MEDIUM   | All Tailwind custom classes defined in `globals.css` |
| Settings | MEDIUM | Settings page calls real `GET/PUT /api/v1/config` endpoint |
| Zones  | MEDIUM   | Canvas polygon editor saves to camera config via API |
| SITE_ID | MEDIUM  | All pages read `siteId` from Zustand store — no hardcoded `1` |

---

## Stack

| Layer | Technology |
|---|---|
| AI model | YOLOv8 (Ultralytics) fine-tuned on Roboflow PPE dataset |
| Backend | FastAPI 0.111 + Python 3.11 |
| Video ingestion | OpenCV RTSP → async frame queue |
| Live streaming | WebSocket (annotated JPEG frames, authenticated) |
| Database | PostgreSQL 15 + SQLAlchemy 2.0 async |
| Task queue | Celery + Redis |
| Alerting | Twilio SMS (non-blocking, executor-wrapped) |
| Cooldown store | Redis (multi-worker safe) |
| Frontend | Next.js 14 App Router + Tailwind CSS |
| Auth | JWT (access + refresh, auto-refresh on 401) |
| Containerisation | Docker + Docker Compose |
| Reverse proxy | Nginx (WebSocket upgrade, no public snapshot mount) |

---

## Quick start

```bash
git clone https://github.com/your-org/sentrylens
cd sentrylens
cp .env.example .env
# Edit .env — set SECRET_KEY, TWILIO_*, DASHBOARD_URL

docker-compose up --build

# New terminal:
docker-compose exec backend alembic upgrade head
docker-compose exec backend python -m app.cli create-admin

# Open http://localhost:3000
```

---

## Honest performance expectations

| Metric | Claimed | Real-world |
|---|---|---|
| Detection mAP | 95% | 65–80% (dusty/night/low-res cameras) |
| Alert latency | <5s | 3–15s (network dependent) |
| Live feed latency | <200ms | 250–600ms (WebSocket JPEG) |
| False positive rate | <5% | 8–20% without site-specific tuning |
| Cameras per RTX 3060 | "many" | 4–5 at 30fps source |
| **Harness detection** | Claimed | **NOT possible** — no harness class in Roboflow 10-class dataset |
| **Near-miss detection** | Claimed | **NOT implemented** — requires trajectory ML |

---

## Environment variables

See `.env.example` — all keys documented. Key ones:

- `SECRET_KEY` — **must be set in production** (≥32 chars, not the default) or server refuses to start
- `DASHBOARD_URL` — full URL of your deployment, embedded in SMS alert links
- `REGISTRATION_OPEN` — `true` for dev, `false` for production (forces admin-only user creation)
- `TWILIO_*` — all three required for SMS alerts
- `MODEL_PATH` — path to trained `.pt` model inside container; see `ml/training/train.py`
