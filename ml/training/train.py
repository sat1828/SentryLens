#!/usr/bin/env python3
"""
SentryLens — YOLOv8 PPE Detection Training Pipeline
═══════════════════════════════════════════════════

Downloads the Roboflow Construction Site Safety dataset, fine-tunes
YOLOv8m (medium — best accuracy/speed tradeoff), and exports the
trained model to /output/sentrylens_best.pt ready for deployment.

REQUIREMENTS:
  pip install ultralytics roboflow torch torchvision pyyaml

USAGE:
  # Basic — uses pretrained YOLOv8m, 100 epochs, GPU if available
  python train.py --roboflow-key YOUR_API_KEY

  # Longer training run
  python train.py --roboflow-key YOUR_API_KEY --epochs 200

  # CPU-only (slow — use GPU if at all possible)
  python train.py --roboflow-key YOUR_API_KEY --device cpu

RESEARCH NOTES:
  - YOLOv8m achieves ~95% mAP on the Roboflow Construction Safety
    dataset IN CONTROLLED CONDITIONS. Real-site performance is 65-80%.
  - YOLOv8l/x gives better accuracy but 2-3× slower inference.
    At 5 cameras × 30fps, YOLOv8m on RTX 3060 is the practical ceiling.
  - The Roboflow dataset (2,801 images, 10 classes) is well-curated
    but lacks night/rain/dust augmentation. Add your own site images
    for maximum production accuracy.
  - Dataset: https://universe.roboflow.com/roboflow-universe-projects/construction-site-safety
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
import yaml

# ─── CLI args ─────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="SentryLens YOLOv8 Training Pipeline")
    p.add_argument("--roboflow-key", required=True, help="Roboflow API key")
    p.add_argument("--workspace", default="roboflow-universe-projects", help="Roboflow workspace")
    p.add_argument("--project", default="construction-site-safety", help="Roboflow project slug")
    p.add_argument("--version", type=int, default=1, help="Dataset version")
    p.add_argument("--model", default="yolov8m.pt", choices=["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt"], help="Base model")
    p.add_argument("--epochs", type=int, default=100, help="Training epochs")
    p.add_argument("--imgsz", type=int, default=640, help="Input image size")
    p.add_argument("--batch", type=int, default=16, help="Batch size (-1 = auto)")
    p.add_argument("--device", default="0", help="Device: '0' for GPU, 'cpu' for CPU")
    p.add_argument("--output", default="./output", help="Output directory for trained model")
    p.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    p.add_argument("--skip-download", action="store_true", help="Skip dataset download (use existing ./dataset)")
    return p.parse_args()


# ─── Dataset download ─────────────────────────────────────────────────────────

def download_dataset(args) -> str:
    """Download from Roboflow. Returns path to data.yaml."""
    print("\n[1/4] Downloading Roboflow dataset...")
    from roboflow import Roboflow

    rf = Roboflow(api_key=args.roboflow_key)
    project = rf.workspace(args.workspace).project(args.project)
    dataset = project.version(args.version).download("yolov8")

    dataset_path = dataset.location
    yaml_path = os.path.join(dataset_path, "data.yaml")

    # Fix absolute paths in data.yaml (required for Ultralytics)
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    data["path"] = dataset_path
    with open(yaml_path, "w") as f:
        yaml.dump(data, f, sort_keys=False)

    print(f"    Dataset downloaded to: {dataset_path}")
    print(f"    Classes: {data.get('names', [])}")
    print(f"    nc: {data.get('nc', '?')}")
    return yaml_path


# ─── Training ─────────────────────────────────────────────────────────────────

def train(args, yaml_path: str):
    """Fine-tune YOLOv8 on the PPE dataset."""
    from ultralytics import YOLO

    print(f"\n[2/4] Training YOLOv8 ({args.model}) for {args.epochs} epochs...")
    print(f"      Device: {args.device} | Batch: {args.batch} | ImgSz: {args.imgsz}")

    model = YOLO(args.model)

    results = model.train(
        data=yaml_path,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        resume=args.resume,

        # Augmentation — critical for construction site variability
        # HSV jitter simulates different lighting/dust conditions
        hsv_h=0.015,      # Hue variation
        hsv_s=0.7,        # Saturation variation
        hsv_v=0.4,        # Value/brightness variation
        flipud=0.0,        # Workers aren't upside down
        fliplr=0.5,        # Mirror image — valid for most PPE checks
        mosaic=1.0,        # Mosaic augmentation — improves small object detection
        degrees=10.0,      # Rotation — simulates tilted cameras

        # Optimizer
        optimizer="AdamW",
        lr0=0.001,
        cos_lr=True,       # Cosine LR decay

        # Output
        project="runs/train",
        name="sentrylens",
        exist_ok=True,

        # Logging
        plots=True,        # Save training curves
        save=True,
        save_period=10,    # Checkpoint every 10 epochs

        # Verbosity
        verbose=True,
    )

    return results


# ─── Validation ───────────────────────────────────────────────────────────────

def validate(args, yaml_path: str):
    """Run validation on the best checkpoint and print metrics."""
    from ultralytics import YOLO

    print("\n[3/4] Validating best model...")
    best_pt = "runs/train/sentrylens/weights/best.pt"

    if not os.path.exists(best_pt):
        print("    WARNING: best.pt not found. Skipping validation.")
        return

    model = YOLO(best_pt)
    metrics = model.val(data=yaml_path, device=args.device, imgsz=args.imgsz)

    print(f"\n    ── Validation Results ──────────────────")
    print(f"    mAP50:    {metrics.box.map50:.4f}")
    print(f"    mAP50-95: {metrics.box.map:.4f}")
    print(f"    Precision:{metrics.box.mp:.4f}")
    print(f"    Recall:   {metrics.box.mr:.4f}")
    print(f"    ────────────────────────────────────────")

    if metrics.box.map50 < 0.7:
        print("\n    ⚠  mAP50 below 0.70. Consider:")
        print("       - More training epochs (--epochs 200)")
        print("       - Adding site-specific images to the dataset")
        print("       - Checking for class imbalance in your dataset")
        print("       - Using a larger base model (yolov8l.pt)")


# ─── Export ───────────────────────────────────────────────────────────────────

def export_model(args):
    """Copy best.pt to output directory for deployment."""
    print(f"\n[4/4] Exporting model to {args.output}...")
    os.makedirs(args.output, exist_ok=True)

    best_pt = "runs/train/sentrylens/weights/best.pt"
    if not os.path.exists(best_pt):
        print("    ERROR: best.pt not found. Training may have failed.")
        sys.exit(1)

    dest = os.path.join(args.output, "sentrylens_best.pt")
    shutil.copy2(best_pt, dest)

    # Also copy training results plots
    results_dir = "runs/train/sentrylens"
    for f in ["results.png", "confusion_matrix.png", "PR_curve.png", "F1_curve.png"]:
        src = os.path.join(results_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(args.output, f))

    size_mb = os.path.getsize(dest) / 1e6
    print(f"    Model saved: {dest} ({size_mb:.1f} MB)")
    print(f"\n    ✓ Deploy by mounting {dest} to /app/models/sentrylens_best.pt")
    print(f"      in your Docker container (see docker-compose.yml model_data volume)")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    print("═" * 60)
    print("  SentryLens YOLOv8 Training Pipeline")
    print("═" * 60)

    if args.skip_download:
        yaml_path = "./dataset/data.yaml"
        print(f"[1/4] Skipping download. Using: {yaml_path}")
    else:
        yaml_path = download_dataset(args)

    train(args, yaml_path)
    validate(args, yaml_path)
    export_model(args)

    print("\n" + "═" * 60)
    print("  Training complete.")
    print("  Next: place sentrylens_best.pt in docker/model_data/")
    print("  and restart the backend container.")
    print("═" * 60)


if __name__ == "__main__":
    main()
