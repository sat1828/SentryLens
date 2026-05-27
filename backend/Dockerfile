FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgomp1 libgl1-mesa-glx curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/models /app/snapshots /app/reports /app/celerybeat

# Pre-download YOLOv8m fallback weights so first startup doesn't fetch from internet
RUN python -c "from ultralytics import YOLO; YOLO('yolov8m.pt')" 2>/dev/null || echo "Model pre-download skipped (no internet)"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
