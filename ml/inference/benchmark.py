#!/usr/bin/env python3
"""
SentryLens — Inference Benchmark
──────────────────────────────────
Tests your trained model's speed and accuracy before deployment.
Run this BEFORE putting the model in production.

Usage:
  python benchmark.py --model /path/to/sentrylens_best.pt --source /path/to/test/images
  python benchmark.py --model /path/to/sentrylens_best.pt --rtsp rtsp://192.168.1.10:554/stream1
"""

import argparse
import time
import statistics
from pathlib import Path

import cv2
import numpy as np


def benchmark_images(model_path: str, image_dir: str, n_runs: int = 50):
    from ultralytics import YOLO

    print(f"\nLoading model: {model_path}")
    model = YOLO(model_path)

    images = list(Path(image_dir).glob("**/*.jpg")) + list(Path(image_dir).glob("**/*.png"))
    if not images:
        print("No images found in", image_dir)
        return

    print(f"Found {len(images)} images. Running {n_runs} inference passes...\n")

    latencies = []
    violation_counts: dict = {}

    for i in range(min(n_runs, len(images))):
        img_path = str(images[i % len(images)])
        frame = cv2.imread(img_path)
        if frame is None:
            continue

        t0 = time.perf_counter()
        results = model(frame, verbose=False, conf=0.65)
        ms = (time.perf_counter() - t0) * 1000
        latencies.append(ms)

        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names.get(cls_id, f"cls_{cls_id}")
                violation_counts[cls_name] = violation_counts.get(cls_name, 0) + 1

    if not latencies:
        print("No valid results.")
        return

    print("─" * 50)
    print(f"  Inference latency (ms)")
    print(f"  Mean:   {statistics.mean(latencies):.1f} ms")
    print(f"  Median: {statistics.median(latencies):.1f} ms")
    print(f"  P95:    {sorted(latencies)[int(len(latencies)*0.95)]:.1f} ms")
    print(f"  Min:    {min(latencies):.1f} ms")
    print(f"  Max:    {max(latencies):.1f} ms")
    print(f"\n  Estimated max FPS: {1000/statistics.mean(latencies):.1f}")
    print(f"\n  Detection counts across {n_runs} frames:")
    for cls_name, count in sorted(violation_counts.items(), key=lambda x: -x[1]):
        print(f"    {cls_name:<25} {count:>4}")
    print("─" * 50)

    # Honest assessment
    mean_ms = statistics.mean(latencies)
    if mean_ms < 30:
        cams = int(1000 / mean_ms / 3)  # at INFERENCE_EVERY_N_FRAMES=3
        print(f"\n  ✓ At 30fps (inference every 3rd frame):")
        print(f"    Can handle ~{cams} concurrent camera streams on this hardware.")
    else:
        print(f"\n  ⚠  Inference at {mean_ms:.0f}ms is slow for real-time use.")
        print(f"     Consider: GPU acceleration, YOLOv8n (smaller model), or higher INFERENCE_EVERY_N_FRAMES.")


def benchmark_rtsp(model_path: str, rtsp_url: str, duration_sec: int = 30):
    from ultralytics import YOLO

    print(f"\nConnecting to RTSP: {rtsp_url}")
    cap = cv2.VideoCapture(rtsp_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("ERROR: Could not open RTSP stream. Check URL and network.")
        return

    model = YOLO(model_path)

    print(f"Running for {duration_sec}s...\n")
    t_start = time.time()
    frame_count = 0
    inference_count = 0
    latencies = []
    dropped = 0

    while time.time() - t_start < duration_sec:
        ret, frame = cap.read()
        if not ret:
            dropped += 1
            if dropped > 50:
                print("Too many dropped frames. RTSP stream likely disconnected.")
                break
            continue
        dropped = 0
        frame_count += 1

        # Inference every 3rd frame
        if frame_count % 3 != 0:
            continue
        inference_count += 1

        t0 = time.perf_counter()
        model(frame, verbose=False, conf=0.65)
        latencies.append((time.perf_counter() - t0) * 1000)

    cap.release()
    elapsed = time.time() - t_start

    print("─" * 50)
    print(f"  Stream test complete ({elapsed:.1f}s)")
    print(f"  Frames received:  {frame_count}")
    print(f"  Inferences run:   {inference_count}")
    print(f"  Source FPS:       {frame_count/elapsed:.1f}")
    if latencies:
        print(f"  Mean inference:   {statistics.mean(latencies):.1f}ms")
    print("─" * 50)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, help="Path to .pt model file")
    p.add_argument("--source", help="Directory of test images")
    p.add_argument("--rtsp", help="RTSP URL to benchmark live stream")
    p.add_argument("--runs", type=int, default=50, help="Number of inference runs (image mode)")
    p.add_argument("--duration", type=int, default=30, help="Benchmark duration in seconds (RTSP mode)")
    args = p.parse_args()

    if args.rtsp:
        benchmark_rtsp(args.model, args.rtsp, args.duration)
    elif args.source:
        benchmark_images(args.model, args.source, args.runs)
    else:
        print("Provide --source (image dir) or --rtsp (stream URL)")


if __name__ == "__main__":
    main()
