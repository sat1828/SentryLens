<div align="center">

<img src="/banner.gif" alt="SentryLens — Real-Time Construction Site Safety AI" width="100%"/>

<br/><br/>

[![Python](https://img.shields.io/badge/Python-3.11-3776ab?style=flat-square&logo=python&logoColor=white&labelColor=0d1117)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-00b386?style=flat-square&logo=fastapi&logoColor=white&labelColor=0d1117)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-ffffff?style=flat-square&logo=nextdotjs&logoColor=white&labelColor=0d1117)](https://nextjs.org)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-f85149?style=flat-square&labelColor=0d1117)](https://ultralytics.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169e1?style=flat-square&logo=postgresql&logoColor=white&labelColor=0d1117)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-dc382d?style=flat-square&logo=redis&logoColor=white&labelColor=0d1117)](https://redis.io)
[![Celery](https://img.shields.io/badge/Celery-worker+beat-37814a?style=flat-square&labelColor=0d1117)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ed?style=flat-square&logo=docker&logoColor=white&labelColor=0d1117)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-3fb950?style=flat-square&labelColor=0d1117)](LICENSE)

<br/>

> **Eyes on every site. Always.**
>
> SentryLens connects to your existing CCTV and IP cameras over RTSP, runs YOLOv8 frame-by-frame,
> texts your site manager within seconds of a PPE violation, and generates OSHA-ready PDF compliance
> reports at 02:00 every morning — automatically, on your own server, no cloud subscription needed.

<br/>

[**Quickstart**](#quickstart) · [**Architecture**](#architecture) · [**Dashboard**](#live-dashboard) · [**Detection Pipeline**](#detection--alert-pipeline) · [**Docker Services**](#docker-services) · [**Zone Editor + PDF**](#zone-editor--osha-pdf) · [**Environment Variables**](#environment-variables) · [**Deployment**](#production-deployment) · [**Performance**](#honest-performance-numbers) · [**Bug Fixes**](#bug-fixes-31-addressed)

</div>

---

## What this actually does

A construction worker walks onto site at 6am without a hard hat. Within 3–15 seconds your site manager gets a Twilio SMS — camera name, violation type, and a direct link (`DASHBOARD_URL` from your env) to the snapshot. The browser dashboard streams all camera feeds simultaneously with YOLOv8 bounding boxes annotated in real time over WebSocket, colour-coded green for compliant and red for violation. Confidence scores float above each box. Zone polygons you drew in the browser overlay the frame.

At end of day, Celery Beat fires the daily OSHA PDF at 02:00: per-camera breakdown, hourly distribution, acknowledged vs unacknowledged counts. No export button, no spreadsheet — it's a blob fetch from the frontend with the JWT in the `Authorization` header, not the URL.

No cloud dependency. No SaaS subscription. Runs entirely on your own server with your own cameras.

---

## Live Dashboard

<img src="/dashboard.gif" alt="SentryLens live dashboard — 4 WebSocket feeds, YOLO bounding boxes, real-time violation log, compliance chart" width="100%"/>

Four camera feeds streamed over WebSocket as annotated JPEG. JWT access token (`ACCESS_TOKEN_EXPIRE_MINUTES=60`) auto-refreshes on every 401 — no login prompt interrupting a night shift. Violation log paginated at 50 per page with Previous/Next. Stat cards read from the real API: violations today, compliance rate, SMS alerts sent, cameras active. `siteId` comes from Zustand store — never hardcoded.

---

## Architecture

<img src="/architecture.gif" alt="SentryLens system architecture — all 7 services animated with data packets" width="100%"/>

Seven Docker services across two networks. The `internal` network carries `internal: true` in production — every backend service is unreachable from outside. Only Nginx bridges both. WebSocket (`ws://`) and REST both go through Nginx on port 80 (443 optional via Let's Encrypt). Snapshots served via authenticated `GET /api/v1/snapshots/{path}` — never a public static mount.

---

## Detection + Alert Pipeline

<img src="/detection_pipeline.gif" alt="RTSP source → OpenCV async queue → YOLOv8 inference → Violation check + zone → Redis cooldown → Twilio SMS + WebSocket stream" width="100%"/>

**How a violation goes from camera to SMS:**

1. **OpenCV RTSP reader** (`stream.py`) pulls frames into an async queue. A watchdog thread monitors staleness — reconnects automatically. H.264 preferred; H.265 works but with more decode variance.
2. **YOLOv8 inference** (`detection.py`) runs every `INFERENCE_EVERY_N_FRAMES=3` frames (~10fps effective from a 30fps source). Boxes drawn above `INFERENCE_CONFIDENCE=0.65`. IoU threshold `NMS_IOU_THRESHOLD=0.45`.
3. **Violation check** — boxes above `VIOLATION_CONFIDENCE_THRESHOLD=0.70` (higher bar than draw threshold, to reduce SMS noise) are tested against the zone polygon stored per camera in PostgreSQL.
4. **Redis cooldown** (`cooldown.py`) — keyed by `camera_id:violation_type`, TTL = `ALERT_COOLDOWN_SECONDS=30`. Shared across both uvicorn workers via Redis, not in-process memory. No race condition, no duplicate SMS within the cooldown window.
5. **Twilio SMS** fires inside `run_in_executor` — never blocks the async event loop.
6. **WebSocket stream** — every annotated frame sent as JPEG with `asyncio.wait_for(0.5s)`. Slow browsers drop frames, they don't block the inference loop.

**The 10 PPE classes the model detects:**

| Compliant ✓ | Violation ⚠ |
|---|---|
| `helmet` | `no-helmet` |
| `vest` | `no-vest` |
| `gloves` | `no-gloves` |
| `boots` | `no-boots` |
| `mask` | `no-mask` |

> **Harness detection is not possible with this dataset.** It was never in the Roboflow 10-class set. BUG-4 and BUG-5 corrected earlier README claims to the contrary. If you need harness detection, train a custom model via `ml/training/train.py` with your own dataset.

---

## Docker Services

<img src="/docker_services.gif" alt="All 7 Docker Compose services — dependency graph, resource limits, volumes, networks" width="100%"/>

| Service | Image | Port | Mem limit | `depends_on` condition |
|---|---|---|---|---|
| `postgres` | `postgres:15-alpine` | — | 512M | — |
| `redis` | `redis:7-alpine` | — | 300M | — |
| `backend` | `sentrylens-backend:latest` | 8000 | 4G | `postgres` service_healthy · `redis` service_healthy |
| `celery_worker` | `sentrylens-backend:latest` | — | 1G | `redis` · `postgres` |
| `celery_beat` | `sentrylens-backend:latest` | — | 256M | `redis` |
| `frontend` | `sentrylens-frontend:latest` | 3000 | 512M | `backend` |
| `nginx` | `nginx:1.25-alpine` | 80 (443 opt) | 128M | `backend` service_healthy · `frontend` started |

**Named volumes:** `postgres_data` · `redis_data` · `model_data` · `snapshot_data` · `celerybeat_data`

**Celery worker command:** `celery -A app.workers.tasks worker --loglevel=info --concurrency=2 -Q default`

**Celery Beat command:** `celery -A app.workers.tasks beat --loglevel=warning --scheduler celery.beat.PersistentScheduler`

**Dev vs prod key differences:**

| | Dev (`docker-compose.yml`) | Prod (`docker-compose.prod.yml`) |
|---|---|---|
| Source | Bind mounts (`./backend:/app`) | Built images only |
| Restart | `unless-stopped` | `always` |
| Resource limits | None | Explicit `deploy.resources.limits` per service |
| uvicorn | Single worker | `--workers 2 --proxy-headers --forwarded-allow-ips='*'` |
| GPU | Off | Commented block — uncomment + install NVIDIA runtime |
| DB password | `sentrylens_dev_pass` | Required from env — server fails if unset |
| Network | Standard bridge | `internal: true` on internal network |

---

## Zone Editor + OSHA PDF

<img src="/zone_pdf.gif" alt="Zone polygon editor with draggable vertices on the live frame + daily OSHA PDF report with per-camera breakdown and hourly chart" width="100%"/>

**Zone editor:** draw detection polygons on the live camera frame. Click to place vertices, drag to reshape, double-click to close. Saves via `POST /api/v1/cameras/{id}/zone` — stored as a coordinate array in PostgreSQL, picked up by the inference loop without restart. Overcrowding alerts fire when the person count inside the polygon exceeds `SCAFFOLD_OVERCROWD_THRESHOLD=6`. Zone A and Zone B can coexist on the same camera feed.

**OSHA PDF:** generated by Celery worker, dispatched by Beat using `PersistentScheduler` at 02:00. Includes:
- Site-level totals (violations, acknowledged, unacknowledged, compliance rate)
- Per-camera breakdown table — was completely absent in the original code (BUG-29)
- Acknowledged count using SQLAlchemy `True` in the WHERE clause — was Python `False`, so count was always 0 (BUG-28)
- Hourly distribution bar chart across 06h–17h

Frontend downloads via `fetch` + blob — JWT in `Authorization` header, never in the URL (BUG-32).

---

## Stack

| Layer | Technology | Key config |
|---|---|---|
| AI | YOLOv8 (Ultralytics) | Fine-tuned on Roboflow PPE 10-class · `MODEL_PATH=/app/models/sentrylens_best.pt` |
| Backend | FastAPI 0.111 · Python 3.11 · uvicorn | `--workers 2` prod · `--proxy-headers` |
| Video | OpenCV RTSP async queue | `stream.py` · watchdog · H.264 preferred |
| Inference | YOLOv8 every N frames | `INFERENCE_EVERY_N_FRAMES=3` · `INFERENCE_CONFIDENCE=0.65` · `NMS_IOU_THRESHOLD=0.45` |
| Violations | Alert engine + zone polygon | `VIOLATION_CONFIDENCE_THRESHOLD=0.70` · `SCAFFOLD_OVERCROWD_THRESHOLD=6` |
| Live stream | WebSocket JPEG | `?token=` JWT · `asyncio.wait_for(0.5s)` per send |
| Database | PostgreSQL 15 · SQLAlchemy 2.0 async | Alembic · violations · cameras · users · sites |
| Tasks | Celery `app.workers.tasks` | `--concurrency=2` · `-Q default` |
| Scheduler | Celery Beat PersistentScheduler | Daily PDF · `celerybeat_data` volume |
| Cooldown | Redis 7 · `allkeys-lru` 256mb | `ALERT_COOLDOWN_SECONDS=30` · multi-worker safe |
| SMS | Twilio · `run_in_executor` | `DEFAULT_ALERT_RECIPIENTS` E.164 comma-separated |
| Auth | JWT access 60min + refresh 30d | `apiFetch` 401 auto-refresh · `REGISTRATION_OPEN` guard |
| Frontend | Next.js 14 App Router · Tailwind · Zustand | `siteId` from store · blob PDF · WS canvas |
| Proxy | Nginx 1.25-alpine | WS upgrade · authenticated snapshots |
| Containers | Docker Compose dev + prod | 7 services · 5 volumes · 2 networks |

---

## Quickstart

```bash
git clone https://github.com/sat1828/SentryLens
cd SentryLens
cp .env.example .env
```

Open `.env`. These are the values that cause real failures if left as defaults:

```bash
# Must be ≥32 chars and not the default string.
# Server refuses to start in production if unchanged.
# Generate with: openssl rand -hex 32
SECRET_KEY=CHANGE_THIS_TO_A_LONG_RANDOM_STRING_MINIMUM_32_CHARACTERS_HERE

# Full public URL of your deployment.
# This gets embedded in every SMS alert link.
# Leaving it as localhost means every link points to localhost on the recipient's phone.
DASHBOARD_URL=https://sentrylens.yourcompany.com

# Set false in production — true means anyone on the internet can self-register.
REGISTRATION_OPEN=false

# All three required. Missing any one = SMS silently fails, no error surfaced.
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
TWILIO_FROM_NUMBER=+1415XXXXXXX

# E.164 format, comma-separated.
# On Twilio free trial, each number must be verified at console.twilio.com/verified-numbers
DEFAULT_ALERT_RECIPIENTS=+919XXXXXXXXXX

# Strong random password for Postgres in production
POSTGRES_PASSWORD=change_this_strong_password
```

```bash
# Start all 7 services
docker-compose up --build

# In a new terminal — run once services are healthy
docker-compose exec backend alembic upgrade head
docker-compose exec backend python -m app.cli create-admin
```

Open `http://localhost:3000`. Add your first camera:

```bash
# Option A: via the Cameras page in the dashboard

# Option B: via API
curl -X POST http://localhost:8000/api/v1/cameras/ \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CAM-01 Entry Gate",
    "rtsp_url": "rtsp://192.168.1.100:554/stream1",
    "site_id": 1,
    "zone": "Zone A",
    "config": {"overcrowd_threshold": 6}
  }'
```

**RTSP not connecting?**

```bash
# Test from inside the backend container
docker-compose exec backend python -c "
import cv2
cap = cv2.VideoCapture('rtsp://192.168.1.100:554/stream1')
print('Opened:', cap.isOpened())
cap.release()
"
# Common fixes:
# - Credentials:  rtsp://admin:password@192.168.1.100:554/stream1
# - Wrong path:   check your camera vendor docs for the RTSP stream path
# - Firewall:     backend container must reach the camera IP
# - H.265:        set camera to H.264 output if you see decode errors
```

---

## Production deployment

```bash
# Step 1 — Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# Step 2 — GPU support (NVIDIA only, optional)
# Install NVIDIA Container Toolkit then uncomment the gpu block in docker-compose.prod.yml

# Step 3 — Train and load the model (do this before first boot)
cd ml/training && pip install ultralytics roboflow pyyaml
python train.py --roboflow-key YOUR_KEY --epochs 100
docker volume create sentrylens_model_data
docker run --rm \
  -v sentrylens_model_data:/data \
  -v $(pwd)/ml/output:/src \
  alpine cp /src/sentrylens_best.pt /data/

# Without this, system falls back to yolov8m.pt (COCO) — no PPE detection.

# Step 4 — Deploy
cd /path/to/SentryLens
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker-compose -f docker-compose.prod.yml exec backend python -m app.cli create-admin
docker-compose -f docker-compose.prod.yml ps

# Step 5 — HTTPS (strongly recommended)
sudo apt install certbot
sudo certbot certonly --standalone -d sentrylens.yourdomain.com
# Mount certs in docker-compose.prod.yml nginx volumes:
#   - /etc/letsencrypt:/etc/letsencrypt:ro
# Auto-renew via cron:
echo "0 0 1 * * root certbot renew --quiet && docker-compose -f /path/docker-compose.prod.yml restart nginx" \
  | sudo tee /etc/cron.d/certbot
```

**Monitoring:**

```bash
docker-compose -f docker-compose.prod.yml logs -f backend
curl -H "Authorization: Bearer TOKEN" http://localhost/api/v1/cameras/status
curl -H "Authorization: Bearer TOKEN" "http://localhost/api/v1/violations/stats?days=1"
du -sh $(docker volume inspect sentrylens_snapshot_data --format '{{.Mountpoint}}')
```

**Maintenance:**

```bash
# Purge old snapshots (set MAX_SNAPSHOT_AGE_DAYS=90 in .env or run manually)
docker-compose exec backend python -m app.cli purge-snapshots --older-than 90

# Update to new version
git pull origin main
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker-compose -f docker-compose.prod.yml up -d --no-deps backend celery_worker
```

---

## Environment variables

Every variable documented in `.env.example` (81 lines). Complete table of every key:

| Variable | Default | Consequence if left unchanged |
|---|---|---|
| `APP_ENV` | `development` | Set to `production` — enables startup checks |
| `SECRET_KEY` | `CHANGE_THIS_TO_A_LONG_RANDOM...` | **Server refuses to start in production** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | 1-min = broken UX; 10080-min (7d) = security hole |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Adjust per your security policy |
| `REGISTRATION_OPEN` | `true` | Anyone on the internet can self-register |
| `DASHBOARD_URL` | `http://localhost:3000` | Every SMS link points to localhost on recipient's phone |
| `DATABASE_URL` | `postgresql+asyncpg://...@postgres:5432/sentrylens` | Must match `POSTGRES_PASSWORD` in prod |
| `DATABASE_URL_SYNC` | `postgresql://...@postgres:5432/sentrylens` | Used by Alembic migrations |
| `REDIS_URL` | `redis://redis:6379/0` | Cooldown + Celery broker |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Same Redis instance as cooldown |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/1` | Separate DB index from broker |
| `TWILIO_ACCOUNT_SID` | `ACxxxxxxxx...` | SMS silently fails — no error surfaced |
| `TWILIO_AUTH_TOKEN` | `your_twilio_auth_token_here` | ↑ |
| `TWILIO_FROM_NUMBER` | `+1415XXXXXXX` | ↑ |
| `DEFAULT_ALERT_RECIPIENTS` | `+919XXXXXXXXXX` | Nobody gets alerted |
| `MODEL_PATH` | `/app/models/sentrylens_best.pt` | Falls back to COCO — no PPE detection |
| `FALLBACK_MODEL` | `yolov8m.pt` | Used when `MODEL_PATH` not found |
| `INFERENCE_CONFIDENCE` | `0.65` | Lower = more boxes drawn, more noise |
| `NMS_IOU_THRESHOLD` | `0.45` | IoU for non-max suppression |
| `INFERENCE_EVERY_N_FRAMES` | `3` | `1` = full 30fps inference = GPU throttle |
| `VIOLATION_CONFIDENCE_THRESHOLD` | `0.70` | `0.50` = SMS every few seconds on any noise |
| `ALERT_COOLDOWN_SECONDS` | `30` | `0` = SMS per-frame per persistent violation |
| `SCAFFOLD_OVERCROWD_THRESHOLD` | `6` | Set per site — a 4-person platform needs `4` |
| `SNAPSHOT_DIR` | `/app/snapshots` | Inside container, mapped to `snapshot_data` volume |
| `MAX_SNAPSHOT_AGE_DAYS` | `90` | Disk fills indefinitely if unset |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost` | Set to your real domain in production |
| `LOG_LEVEL` | `INFO` | Use `WARNING` in prod to reduce noise |

---

## Honest performance numbers

Real-world numbers from dusty, low-resolution, backlit construction cameras — not benchmark numbers from a clean dataset:

| Metric | Claimed in original README | What you'll actually see |
|---|---|---|
| Detection mAP | 95% | **65–80%** (dust, backlight, occlusion, night) |
| Alert latency | <5s | **3–15s** (RTSP buffer + inference + Twilio) |
| Live feed latency | <200ms | **250–600ms** (JPEG over WebSocket) |
| False positive rate | <5% | **8–20%** without site-specific tuning |
| Cameras / RTX 3060 12GB | "many" | **4–5** at 30fps, `INFERENCE_EVERY_N_FRAMES=3` |
| Cameras / CPU only | — | **1–2 max** (~200–400ms per inference) |
| YOLOv8 GPU inference | — | **8–20ms/frame** |
| YOLOv8 CPU inference | — | **200–400ms/frame** |
| Harness detection | ✅ claimed | ❌ **Not possible** — not in 10-class dataset |
| Near-miss detection | ✅ claimed | ❌ **Not implemented** — needs trajectory ML |

> Tune `VIOLATION_CONFIDENCE_THRESHOLD` per camera after 48 hours of real footage — never assume training-environment thresholds hold on a real site.

---

## Bug fixes (31 addressed)

All bugs from a structured code review. Sorted by severity using the original review labels:

| # | Severity | What was wrong | What was fixed |
|---|---|---|---|
| BUG-1 | HIGH | Server accepted default `SECRET_KEY` in production | Refuses to start if key matches default |
| BUG-3 | MEDIUM | Malformed JWT `sub` returned 500 | Returns 401 correctly |
| BUG-4, 5 | HIGH | Harness/near-miss claimed as detectable | Corrected — documented as impossible with 10-class dataset |
| BUG-6 | LOW | Inference threads hardcoded to 4 | Scaled to `max(2, cpu_count//2)` |
| BUG-7 | MEDIUM | Overcrowding checked whole frame | Now checks zone polygon only |
| BUG-9 | LOW | Deprecated `get_event_loop()` | Replaced with `get_running_loop()` |
| BUG-12 | CRITICAL | `ViolationLogger.subscribe_camera()` never called on `POST /cameras/` | New cameras now enter detection loop |
| BUG-13 | MEDIUM | Two separate cooldown dicts in different modules | Unified into `cooldown.py` backed by Redis |
| BUG-14 | MEDIUM | Celery task errors silent | Logged via error callback |
| BUG-15 | HIGH | Twilio call blocked the event loop | Moved to `run_in_executor` |
| BUG-16 | HIGH | `DASHBOARD_URL` hardcoded as `localhost` in SMS body | Reads from `DASHBOARD_URL` env var |
| BUG-17 | MEDIUM | Cooldown in process memory — broken with 2 workers | Backed by Redis — shared across all uvicorn workers |
| BUG-18 | CRITICAL | WebSocket had zero authentication | Enforces JWT via `?token=` query param |
| BUG-19 | MEDIUM | `global_alert_callbacks` not updated for cameras added at runtime | Fixed — new cameras get all WS callbacks |
| BUG-20 | MEDIUM | No timeout on WebSocket send — slow clients blocked inference | `asyncio.wait_for(0.5s)` on each send |
| BUG-21 | HIGH | `/register` was completely open | Gated by `REGISTRATION_OPEN` env flag |
| BUG-22 | MEDIUM | `POST /auth/refresh` endpoint missing entirely | Implemented |
| BUG-23 | LOW | Email field used plain `str` | Replaced with `EmailStr` for Pydantic validation |
| BUG-24 | CRITICAL | Second occurrence of subscribe_camera not called | Fixed (different code path from BUG-12) |
| BUG-25 | LOW | RTSP URL accepted arbitrary strings | Validated to `rtsp://` or `rtsps://` only |
| BUG-26 | LOW | Camera list returned all rows, no pagination | `limit`/`offset` added |
| BUG-27 | LOW | `Depends()` parameters had `= None` defaults | Removed — masked required dependencies |
| BUG-28 | MEDIUM | Acknowledged count query used Python `False` in WHERE | Fixed to SQLAlchemy `True` — count was always 0 |
| BUG-29 | MEDIUM | Per-camera breakdown absent from PDF reports | Added to PDF and report summary |
| BUG-30 | LOW | Celery task created new SQLAlchemy engine per invocation | Module-level pool reused across invocations |
| BUG-31 | MEDIUM | Daily report queried wrong acknowledged count | Fixed (same root as BUG-28) |
| BUG-32 | HIGH | PDF download sent JWT as URL query param | Replaced with `fetch` + blob + `Authorization` header |
| BUG-33 | MEDIUM | `apiFetch` didn't retry on 401 | Auto-refreshes access token on 401 |
| BUG-34 | LOW | Canvas resized on every frame render | Resizes only when dimensions change |
| BUG-35 | LOW | New `Image` instance created per frame | Single instance reused — no per-frame GC pressure |
| BUG-36 | CRITICAL | `/snapshots/` was a public Nginx static mount | Replaced with authenticated `GET /api/v1/snapshots/{path}` |
| BUG-37 | MEDIUM | Violation alert list had no pagination | 50/page with Previous/Next controls |
| CSS | MEDIUM | Tailwind custom classes referenced but not defined | Added to `globals.css` |
| Settings | MEDIUM | Settings page called no real API | Wired to `GET`/`PUT /api/v1/config` |
| Zones | MEDIUM | Zone editor was UI-only — saved nothing | Saves to `POST /api/v1/cameras/{id}/zone` on submit |
| SITE_ID | MEDIUM | Every frontend page hardcoded `siteId=1` | Reads from Zustand store |

---

## Project structure

```
SentryLens/
├── .github/
│   └── workflows/                    # CI
├── backend/
│   ├── app/
│   │   ├── api/                      # Routers: cameras, violations, auth, config, snapshots
│   │   ├── core/                     # Settings (SECRET_KEY guard), JWT, security
│   │   ├── models/                   # SQLAlchemy ORM: Violation, Camera, User, Site
│   │   ├── schemas/                  # Pydantic v2: EmailStr, RTSP validator, pagination
│   │   ├── services/
│   │   │   ├── detection.py          # YOLOv8 loop: every N frames, zone polygon, NMS
│   │   │   ├── stream.py             # OpenCV RTSP reader, async queue, watchdog
│   │   │   ├── alert.py              # ViolationLogger, WS broadcaster, subscribe_camera()
│   │   │   ├── cooldown.py           # Redis cooldown: ALERT_COOLDOWN_SECONDS, multi-worker
│   │   │   └── report.py             # PDF: per-camera, hourly chart, acknowledged counts
│   │   ├── workers/
│   │   │   └── tasks.py              # Celery: daily_report, send_sms (run_in_executor)
│   │   └── cli.py                    # create-admin, purge-snapshots, seed-demo
│   ├── alembic/                      # Migration versions
│   └── Dockerfile
├── frontend/
│   ├── app/                          # Next.js 14 App Router
│   │   ├── dashboard/                # 4× WS canvas, paginated alerts, stat cards
│   │   ├── cameras/                  # Camera CRUD + zone polygon editor → API
│   │   ├── reports/                  # blob fetch PDF (JWT in Authorization header)
│   │   └── settings/                 # GET/PUT /api/v1/config
│   ├── components/                   # Shared UI components
│   ├── lib/
│   │   ├── api.ts                    # apiFetch with 401 auto-refresh
│   │   └── store.ts                  # Zustand: siteId, auth tokens
│   └── styles/globals.css            # Tailwind custom class definitions
├── ml/
│   └── training/
│       └── train.py                  # Roboflow download → Ultralytics fine-tune → .pt
├── docker/
│   └── nginx.conf                    # WS upgrade, authenticated /api/v1/snapshots/{path}
├── .env.example                      # 81 lines, every variable documented inline
├── docker-compose.yml                # Dev: bind mounts, unless-stopped, no resource limits
├── docker-compose.prod.yml           # Prod: built images, always, limits, GPU opt-in
└── DEPLOYMENT.md                     # 217 lines: Docker, GPU, model, HTTPS, monitoring, maintenance
```

---

## Hardware requirements

From `DEPLOYMENT.md` — exact numbers, not estimates:

| Hardware | Cameras handled |
|---|---|
| 4 cores · 8GB RAM · no GPU (CPU only) | 1–2 cameras max |
| 8 cores · 16GB RAM · RTX 3060 12GB | 4–5 cameras at 30fps source |
| 8 cores · 32GB RAM · RTX 4090 | 10–12 cameras |

Minimum server spec: Ubuntu 22.04 LTS · 4 cores · 8GB RAM · 50GB SSD · 100 Mbps.
Recommended: Ubuntu 24.04 LTS · 8 cores · 16GB RAM · 200GB NVMe · 1 Gbps · RTX 3060+.

---

## Known production issues

Directly from `DEPLOYMENT.md`:

| Issue | Cause | Fix |
|---|---|---|
| Camera shows offline immediately | RTSP path or credentials wrong | Check camera vendor docs for RTSP stream path |
| Latency grows over hours | RTSP buffer accumulation | Watchdog handles >30min staleness; restart backend if >60s |
| High false positive rate | Confidence threshold too low | Raise `VIOLATION_CONFIDENCE_THRESHOLD` to 0.80 |
| SMS alerts not sending | Twilio credentials wrong or unverified number | Check Twilio console error logs |
| GPU not detected | NVIDIA runtime not configured | Uncomment GPU section in `docker-compose.prod.yml` |
| Disk full | Snapshots accumulating | Run `purge-snapshots` or reduce `MAX_SNAPSHOT_AGE_DAYS` |

---

## Roadmap

- [ ] ONVIF auto-discovery — detect cameras on the network segment without manual RTSP entry
- [ ] Multi-site aggregation dashboard
- [ ] Webhook sink alongside Twilio SMS (Slack, Teams, PagerDuty)
- [ ] Harness detection via expanded custom dataset
- [ ] Custom class training UI (no CLI needed)
- [ ] Per-camera alert recipient routing

---

## Languages

Python `60.9%` · TypeScript `37.2%` · Other `1.9%`

---

<div align="center">

**MIT License** · built by [sat1828](https://github.com/sat1828)

<br/>

*The kind of attention to detail that only matters at 6am when someone forgets their hard hat.*

</div>
