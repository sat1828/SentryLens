<div align="center">

<!-- Banner — generated SVG -->
<img src="<img width="1136" height="301" alt="image" src="https://github.com/user-attachments/assets/e5cb01fb-c788-474c-bb43-1a6159e5cbcc" />
" alt="SentryLens — Real-time PPE compliance AI" width="100%"/>

<br/>

[![Python](https://img.shields.io/badge/Python-3.11-3776ab?logo=python&logoColor=white&labelColor=0d1117)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white&labelColor=0d1117)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-white?logo=nextdotjs&logoColor=white&labelColor=0d1117)](https://nextjs.org)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-f78166?labelColor=0d1117)](https://ultralytics.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=white&labelColor=0d1117)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-cooldown%20%26%20queue-dc382d?logo=redis&logoColor=white&labelColor=0d1117)](https://redis.io)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ed?logo=docker&logoColor=white&labelColor=0d1117)](https://docker.com)
[![License](https://img.shields.io/badge/license-MIT-56d364?labelColor=0d1117)](LICENSE)

<br/>

> **Eyes on every site. Always.**
>
> SentryLens plugs into your existing CCTV/IP cameras via RTSP, runs YOLOv8 inference frame-by-frame, fires SMS alerts the moment someone skips a helmet, and ships OSHA-ready PDF compliance reports — all without touching your camera hardware.

</div>

---

## What this actually does

A construction worker walks onto site without a hard hat. Within 3–15 seconds (network dependent) your site manager gets a Twilio SMS with a link to the violation snapshot. The dashboard, live on any browser, shows all four camera feeds with bounding boxes annotated in real time over WebSocket. By end of day, a Celery job generates a PDF report breaking down violations per camera, per hour, with acknowledged vs unacknowledged counts — OSHA-ready, no spreadsheet involved.

That's the whole pitch. No cloud subscription. Runs entirely on your own server.

---

## Architecture

<div align="center">
<img src="docs/arch.svg" alt="SentryLens system architecture diagram" width="100%"/>
</div>

The system splits cleanly into four concerns:

**Video ingestion** — OpenCV pulls RTSP streams asynchronously into per-camera frame queues. A watchdog thread monitors staleness and reconnects automatically. Inference runs every N frames (configurable) to manage GPU load, scaled to `max(2, cpu_count//2)` threads on CPU-only.

**Detection + alerting** — YOLOv8 (fine-tuned on the Roboflow 10-class PPE dataset) annotates frames with bounding boxes. Violations trigger the alert engine, which checks a Redis-backed cooldown store (shared across all uvicorn workers — fixed a nasty dual-cooldown bug) before placing a Twilio call in an executor so it never blocks the event loop.

**Storage + reporting** — Violations land in PostgreSQL via SQLAlchemy 2.0 async. Celery handles daily PDF generation and ships it on a cron schedule. Snapshots are served through an authenticated API endpoint — never a public static mount.

**Frontend** — Next.js 14 App Router with Zustand for global state. The live feed consumes WebSocket frames (authenticated via `?token=` query param). The JWT access token auto-refreshes on 401 — no stale session pop-ups. PDF downloads happen as blob fetches so the token never touches a URL.

---

## Dashboard

<div align="center">
<img src="docs/dashboard_mockup.svg" alt="SentryLens dashboard UI mockup" width="100%"/>
</div>

The dashboard surfaces four things that actually matter on a site:

- **Live annotated feed** — four camera streams simultaneously, bounding boxes colour-coded by violation type, polygon zone overlays editable from the browser
- **Violation log** — paginated (50/page), filterable, acknowledgeable with a timestamp
- **7-day compliance trend** — per-camera breakdown, not just a site-wide number
- **OSHA PDF** — blob-downloaded via authenticated fetch, per-camera stats included

---

## Stack

| Layer | What's running |
|---|---|
| AI model | YOLOv8 (Ultralytics) — fine-tuned on Roboflow PPE dataset |
| Backend | FastAPI 0.111 · Python 3.11 · uvicorn |
| Video ingestion | OpenCV RTSP → async frame queue · watchdog |
| Live streaming | WebSocket — annotated JPEG, JWT auth via `?token=` |
| Database | PostgreSQL 15 · SQLAlchemy 2.0 async · Alembic |
| Task queue | Celery · Redis broker |
| Alerting | Twilio SMS — `run_in_executor`, non-blocking |
| Cooldown | Redis — shared across workers, no race conditions |
| Frontend | Next.js 14 App Router · Tailwind CSS · Zustand |
| Auth | JWT access + refresh — auto-refreshes on 401 |
| Containers | Docker · Docker Compose (dev + prod configs) |
| Reverse proxy | Nginx — WebSocket upgrade, no public `/snapshots/` |

---

## Honest performance numbers

This matters. I'm not going to put 95% mAP in the README and let you find out the hard way on a dusty site at 6am.

| Metric | What you might see |
|---|---|
| Detection mAP | 65–80% on real construction cameras (dusty, low-res, night) |
| Alert latency | 3–15s depending on network and RTSP buffer |
| Live feed latency | 250–600ms over WebSocket JPEG |
| False positive rate | 8–20% without site-specific model tuning |
| Cameras per RTX 3060 12GB | 4–5 at 30fps source, `INFERENCE_EVERY_N_FRAMES=3` |
| Cameras without GPU | 1–2 max (CPU inference is slow) |
| **Harness detection** | **Not possible** — not in the Roboflow 10-class dataset |
| **Near-miss detection** | **Not implemented** — requires trajectory modelling |

The PPE classes the model actually knows: `helmet`, `no-helmet`, `vest`, `no-vest`, `gloves`, `no-gloves`, `boots`, `person`, `mask`, `no-mask`.

If you need harness detection, you need a custom dataset. `ml/training/train.py` handles the fine-tuning pipeline — bring your own Roboflow key.

---

## Quickstart

```bash
git clone https://github.com/sat1828/SentryLens
cd SentryLens
cp .env.example .env
# Fill in SECRET_KEY, TWILIO_*, DASHBOARD_URL — see below
```

```bash
docker-compose up --build
```

```bash
# In a second terminal, after services start:
docker-compose exec backend alembic upgrade head
docker-compose exec backend python -m app.cli create-admin

# Open http://localhost:3000
```

Add your first camera from the dashboard or via the API:

```bash
curl -X POST http://localhost/api/v1/cameras/ \
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

---

## Environment variables

Every key is documented in `.env.example`. The ones that will actually bite you if you skip them:

| Variable | Why it matters |
|---|---|
| `SECRET_KEY` | Must be ≥32 chars and not the default. Server **refuses to start** in production if you leave it as-is. |
| `DASHBOARD_URL` | Full URL of your deployment — embedded in every SMS alert link. Hardcoded localhost was [BUG-16]. |
| `REGISTRATION_OPEN` | Set `false` in production. Otherwise anyone can register an account. |
| `TWILIO_ACCOUNT_SID` | All three Twilio vars required for SMS. Missing any one = silent failure. |
| `TWILIO_AUTH_TOKEN` | ↑ |
| `TWILIO_FROM_NUMBER` | ↑ |
| `MODEL_PATH` | Path to your fine-tuned `.pt` inside the container. Falls back to `yolov8m.pt` (COCO) without PPE classes. |

---

## Training your own model

```bash
cd ml/training
pip install ultralytics roboflow pyyaml
python train.py --roboflow-key YOUR_KEY --epochs 100
```

Output lands in `ml/output/sentrylens_best.pt`. Copy it into the Docker volume:

```bash
docker volume create sentrylens_model_data
docker run --rm \
  -v sentrylens_model_data:/data \
  -v $(pwd):/src alpine \
  cp /src/sentrylens_best.pt /data/
```

Without the fine-tuned model, SentryLens falls back to COCO weights and misclassifies helmets as "sports ball" roughly 30% of the time on real sites.

---

## Production deployment

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the full walkthrough. The short version:

```bash
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker-compose -f docker-compose.prod.yml exec backend python -m app.cli create-admin
```

**GPU support** (NVIDIA only): install the NVIDIA Container Toolkit, then uncomment the GPU section in `docker-compose.prod.yml`. Without it you get CPU inference at ~5fps — fine for testing, painful at scale.

**HTTPS**: strongly recommended. `DEPLOYMENT.md` has a certbot + Let's Encrypt walkthrough with auto-renewal via cron.

**Hardware baseline:**

| Setup | What it handles |
|---|---|
| 4 cores, 8GB RAM, no GPU | 1–2 cameras (slow) |
| 8 cores, 16GB RAM, RTX 3060 | 4–5 cameras at 30fps |
| 8 cores, 32GB RAM, RTX 4090 | 10–12 cameras |

---

## Bug fixes shipped (31 addressed from original review)

The original codebase had some sharp edges. Here's what was fixed before this version:

**Critical (would fail in production)**
- Server refused to start with default `SECRET_KEY` → now enforced at startup
- WebSocket had no auth → `?token=` query param added
- `/snapshots/` was a public static mount → replaced with authenticated `/api/v1/snapshots/{path}`
- `ViolationLogger.subscribe_camera()` wasn't being called on `POST /cameras/` → fixed

**High (data loss or blocking behaviour)**
- Twilio call was blocking the event loop → moved to `run_in_executor`
- `DASHBOARD_URL` was hardcoded to localhost in SMS body → configurable
- `/register` was open to anyone → gated by `REGISTRATION_OPEN` env flag
- PDF downloaded by putting JWT in the URL → now blob fetch, token stays in header

**Medium (correctness)**
- Dual cooldown dicts across the codebase → unified into `cooldown.py` backed by Redis
- Overcrowding check was counting whole-frame, not polygon zone → fixed
- `global_alert_callbacks` didn't include new cameras → fixed
- `asyncio.wait_for(0.5s)` on WebSocket send → drops slow clients instead of crashing
- `POST /auth/refresh` endpoint was missing → implemented
- Acknowledged count used `False` instead of SQLAlchemy `True` in the WHERE → fixed
- Per-camera breakdown was missing from PDF and report summary → added
- `apiFetch` didn't auto-refresh on 401 → added
- Alert list had no pagination → 50/page with Previous/Next controls
- All pages had hardcoded `siteId=1` → reads from Zustand store

**Low (papercuts)**
- Canvas resized on every frame → resizes only on dimension change
- Single `Image` instance reused across frames → no per-frame GC pressure
- All Tailwind custom classes now defined in `globals.css`

---

## Project structure

```
SentryLens/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers — cameras, violations, auth, config
│   │   ├── core/         # Settings, JWT, security
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic v2 request/response schemas
│   │   ├── services/
│   │   │   ├── detection.py      # YOLOv8 inference loop
│   │   │   ├── stream.py         # OpenCV RTSP reader + watchdog
│   │   │   ├── alert.py          # Violation logger, WS broadcaster
│   │   │   ├── cooldown.py       # Redis-backed cooldown (multi-worker safe)
│   │   │   └── report.py         # PDF generation
│   │   ├── tasks/        # Celery tasks — daily report, Twilio SMS
│   │   └── cli.py        # create-admin, purge-snapshots, seed-demo
│   ├── alembic/          # DB migration versions
│   └── requirements.txt
├── frontend/
│   ├── app/              # Next.js 14 App Router pages
│   │   ├── dashboard/    # Live feed, alerts, reports
│   │   ├── cameras/      # Camera management + zone editor
│   │   └── settings/     # Site config (calls real GET/PUT /api/v1/config)
│   ├── components/       # Shared UI components
│   ├── lib/
│   │   ├── api.ts        # apiFetch with 401 auto-refresh
│   │   └── store.ts      # Zustand — siteId, auth tokens
│   └── styles/globals.css
├── ml/
│   └── training/
│       └── train.py      # Roboflow download → Ultralytics fine-tune
├── docker/
│   └── nginx.conf        # WS upgrade, authenticated snapshot serving
├── .github/workflows/    # CI
├── docker-compose.yml         # Dev
├── docker-compose.prod.yml    # Production (GPU-ready)
├── .env.example
└── DEPLOYMENT.md
```

---

## Known limitations

- **Harness and near-miss** detection are not possible with the current 10-class dataset. The README previously claimed otherwise. It can't detect what it was never trained on.
- **H.265 streams** work but OpenCV handles H.264 better. Set your cameras to H.264 if you're seeing decode errors.
- **False positives spike** in low light, heavy dust, and partial occlusion. `VIOLATION_CONFIDENCE_THRESHOLD=0.80` reduces noise at the cost of missed detections.
- **Disk fills up** if you don't purge snapshots. Run `python -m app.cli purge-snapshots --older-than 90` or set `MAX_SNAPSHOT_AGE_DAYS` in `.env`.
- **RTSP buffer drift** causes growing latency on long-running streams. The watchdog catches >30-minute staleness and reconnects — but restart the backend service if you see latency creeping past a minute.

---

## Roadmap

- [ ] ONVIF camera discovery (auto-detect cameras on the network segment)
- [ ] Multi-site dashboard with site-level aggregation
- [ ] Alarms API (webhook sink alongside Twilio SMS)
- [ ] Custom class training pipeline UI
- [ ] Harness detection via expanded dataset

---

## License

MIT. Do what you want with it.

---

<div align="center">
Built with unreasonable attention to the details that actually matter on a construction site.<br/>
<strong>sat1828</strong>
</div>
