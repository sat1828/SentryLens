# SentryLens — Production Deployment Guide

## Prerequisites

| Requirement | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| CPU | 4 cores | 8 cores |
| RAM | 8 GB | 16 GB |
| GPU | None (CPU-only, slow) | NVIDIA RTX 3060+ (12 GB VRAM) |
| Disk | 50 GB SSD | 200 GB NVMe (snapshots grow) |
| Network | 100 Mbps | 1 Gbps (for multi-camera RTSP) |

**Cameras per GPU (at 30fps source, INFERENCE_EVERY_N_FRAMES=3):**
- No GPU (CPU): 1–2 cameras max
- RTX 3060 12GB: 4–5 cameras
- RTX 4090: 10–12 cameras

---

## Step 1 — Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
```

For GPU support (NVIDIA only):
```bash
# Install NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
# Uncomment gpu section in docker-compose.prod.yml
```

---

## Step 2 — Clone and configure

```bash
git clone https://github.com/your-org/sentrylens.git
cd sentrylens

cp .env.example .env
nano .env  # Fill in ALL required values (see below)
```

### Required .env values

```bash
SECRET_KEY=<64-char random string: openssl rand -hex 32>
POSTGRES_PASSWORD=<strong random password>
TWILIO_ACCOUNT_SID=<from twilio.com/console>
TWILIO_AUTH_TOKEN=<from twilio.com/console>
TWILIO_FROM_NUMBER=<your Twilio phone number>
DEFAULT_ALERT_RECIPIENTS=<+91XXXXXXXXXX,+44XXXXXXXXXX>
```

---

## Step 3 — Train and install the model

```bash
# On a machine with a GPU (can be different from the server):
cd ml/training
pip install ultralytics roboflow pyyaml
python train.py --roboflow-key YOUR_KEY --epochs 100

# Copy the model to the server
scp ml/output/sentrylens_best.pt user@server:/path/to/sentrylens/

# Put the model into the Docker volume
docker volume create sentrylens_model_data
docker run --rm \
  -v sentrylens_model_data:/data \
  -v $(pwd):/src alpine \
  cp /src/sentrylens_best.pt /data/
```

If you skip model training, SentryLens falls back to `yolov8m.pt` (COCO weights). **PPE classes will NOT be detected correctly** without the fine-tuned model.

---

## Step 4 — Deploy

```bash
# Build and start all services
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d

# Run DB migrations
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head

# Create first admin user
docker-compose -f docker-compose.prod.yml exec backend python -m app.cli create-admin

# Verify everything is running
docker-compose -f docker-compose.prod.yml ps
curl http://localhost/health
```

---

## Step 5 — Add cameras

```bash
# Option A: Via web dashboard at http://your-server-ip/dashboard/cameras

# Option B: Via API
curl -X POST http://localhost/api/v1/cameras/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CAM-01 Entry gate",
    "rtsp_url": "rtsp://192.168.1.100:554/stream1",
    "site_id": 1,
    "zone": "Zone A",
    "config": {"overcrowd_threshold": 6}
  }'
```

### RTSP troubleshooting

```bash
# Test RTSP from inside the backend container
docker-compose exec backend python -c "
import cv2
cap = cv2.VideoCapture('rtsp://192.168.1.100:554/stream1')
print('Opened:', cap.isOpened())
cap.release()
"

# Common fixes:
# 1. Wrong credentials: rtsp://admin:password@192.168.1.100:554/stream1
# 2. Wrong path: check camera manufacturer documentation for RTSP paths
# 3. Network: ensure backend container can reach camera IP (check firewall)
# 4. H.265: SentryLens uses OpenCV which handles H.264 better — set camera to H.264
```

---

## Step 6 — HTTPS (strongly recommended)

```bash
# Install certbot
sudo apt install certbot

# Get cert (replace with your domain)
sudo certbot certonly --standalone -d sentrylens.yourdomain.com

# Mount certs in nginx (edit docker-compose.prod.yml):
# volumes:
#   - /etc/letsencrypt:/etc/letsencrypt:ro

# Add SSL server block to docker/nginx.conf
# Auto-renewal via cron:
echo "0 0 1 * * root certbot renew --quiet && docker-compose -f /path/to/docker-compose.prod.yml restart nginx" | sudo tee /etc/cron.d/certbot
```

---

## Monitoring

```bash
# Live logs from all services
docker-compose -f docker-compose.prod.yml logs -f

# Backend only
docker-compose -f docker-compose.prod.yml logs -f backend

# Check stream status
curl -H "Authorization: Bearer TOKEN" http://localhost/api/v1/cameras/status

# Check violation count today
curl -H "Authorization: Bearer TOKEN" "http://localhost/api/v1/violations/stats?days=1"

# Disk usage (snapshots)
docker system df -v
du -sh $(docker volume inspect sentrylens_snapshot_data --format '{{.Mountpoint}}')
```

---

## Maintenance

```bash
# Purge old snapshots (>90 days)
docker-compose exec backend python -m app.cli purge-snapshots --older-than 90

# Generate today's report manually
docker-compose exec backend python -m app.cli seed-demo  # Demo only — do not use in prod

# Update to new version
git pull origin main
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker-compose -f docker-compose.prod.yml up -d --no-deps backend celery_worker
```

---

## Known production issues

| Issue | Cause | Fix |
|---|---|---|
| Camera shows offline immediately | RTSP path/credentials wrong | Check camera vendor docs |
| Latency grows over time | RTSP buffer accumulation | Watchdog already handles; restart backend if >30 min stale |
| High false positive rate | Confidence threshold too low | Increase `VIOLATION_CONFIDENCE_THRESHOLD` to 0.80 |
| SMS alerts not sending | Twilio credentials wrong or unverified number | Check Twilio console for error logs |
| GPU not detected | NVIDIA runtime not configured | Uncomment GPU section in docker-compose.prod.yml |
| Disk full | Snapshots accumulating | Run purge-snapshots or reduce `MAX_SNAPSHOT_AGE_DAYS` |
