"""
YOLOv8 PPE Detection Engine.
FIX BUG-4,5: honest comments — MISSING_HARNESS and NEAR_MISS are not detectable
              with the Roboflow 10-class dataset. Dead enum values documented clearly.
FIX BUG-6: ThreadPoolExecutor workers scaled to max(2, cpu_count//2).
FIX BUG-7: overcrowding check tied to zone polygons, not whole frame.
FIX BUG-9: get_running_loop() replaces deprecated get_event_loop().
"""
import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
from loguru import logger

from app.core.config import settings
from app.models.models import Severity, ViolationType, VIOLATION_LABELS, VIOLATION_SEVERITY


# ── Class map: Roboflow Construction Site Safety (10 classes) ─────────────────
# BUG-4 FIX documented: MISSING_HARNESS has no class in this dataset.
# BUG-5 FIX documented: NEAR_MISS requires trajectory ML not class detection.
# If you need harness or near-miss detection, use the CHV dataset or annotate
# custom footage and add classes 10+ to this map.
ROBOFLOW_CLASS_MAP: dict[int, Optional[ViolationType]] = {
    0: None,                             # Hardhat (present)
    1: None,                             # Mask (present)
    2: ViolationType.MISSING_HELMET,     # NO-Hardhat
    3: None,                             # NO-Mask (not tracked)
    4: ViolationType.MISSING_VEST,       # NO-Safety Vest
    5: None,                             # Person (zone/crowd logic below)
    6: None,                             # Safety Cone
    7: None,                             # Safety Vest (present)
    8: None,                             # Machinery
    9: None,                             # Vehicle
    # NOTE: No harness class exists in this dataset → MISSING_HARNESS never fires.
    # NOTE: NEAR_MISS requires separate trajectory analysis → not implemented here.
}

BBOX_COLORS: dict[Severity, tuple] = {
    Severity.CRITICAL: (0,   0, 220),
    Severity.HIGH:     (0,  60, 220),
    Severity.MEDIUM:   (0, 165, 255),
    Severity.LOW:      (0, 200, 100),
}

# BUG-6 FIX: scale workers to available CPU, not a hardcoded 2
import multiprocessing as _mp
_WORKER_COUNT = max(2, _mp.cpu_count() // 2)


@dataclass
class Detection:
    class_id:       int
    class_name:     str
    confidence:     float
    bbox:           List[float]           # [x1,y1,x2,y2] normalised 0-1
    violation_type: Optional[ViolationType] = None
    severity:       Optional[Severity]      = None


@dataclass
class InferenceResult:
    frame_id:        int
    camera_id:       int
    timestamp:       datetime
    detections:      List[Detection] = field(default_factory=list)
    violations:      List[Detection] = field(default_factory=list)
    person_count:    int             = 0
    annotated_frame: Optional[np.ndarray] = None
    inference_ms:    float           = 0.0


class PPEDetector:
    def __init__(self):
        self._model     = None
        self._executor  = ThreadPoolExecutor(max_workers=_WORKER_COUNT, thread_name_prefix="yolo")
        self._loaded    = False
        self._load_lock = asyncio.Lock()

    async def load(self) -> None:
        async with self._load_lock:
            if self._loaded:
                return
            loop = asyncio.get_running_loop()   # BUG-9 FIX
            await loop.run_in_executor(self._executor, self._load_model)
            self._loaded = True

    def _load_model(self) -> None:
        try:
            from ultralytics import YOLO
            path = settings.MODEL_PATH
            if os.path.exists(path):
                logger.info(f"Loading fine-tuned model: {path}")
                self._model = YOLO(path)
            else:
                logger.warning(
                    f"Custom model not at {path}. Falling back to {settings.FALLBACK_MODEL}. "
                    "PPE detection WILL NOT work correctly until you train and deploy the model."
                )
                self._model = YOLO(settings.FALLBACK_MODEL)
            self._model(np.zeros((640, 640, 3), dtype=np.uint8), verbose=False)  # warm-up
            logger.info(f"YOLOv8 loaded ({_WORKER_COUNT} inference workers).")
        except Exception as e:
            logger.error(f"Model load failed: {e}")
            raise

    async def infer(
        self,
        frame: np.ndarray,
        camera_id: int,
        frame_id: int,
        restricted_zone_polygons: Optional[List] = None,
        overcrowd_threshold: int = 6,
    ) -> InferenceResult:
        if not self._loaded:
            await self.load()
        loop = asyncio.get_running_loop()   # BUG-9 FIX
        return await loop.run_in_executor(
            self._executor,
            self._run_inference,
            frame.copy(), camera_id, frame_id,
            restricted_zone_polygons, overcrowd_threshold,
        )

    def _run_inference(
        self,
        frame: np.ndarray,
        camera_id: int,
        frame_id: int,
        restricted_zone_polygons: Optional[List],
        overcrowd_threshold: int,
    ) -> InferenceResult:
        t0   = time.perf_counter()
        h, w = frame.shape[:2]

        results = self._model(
            frame, conf=settings.INFERENCE_CONFIDENCE,
            iou=settings.NMS_IOU_THRESHOLD, verbose=False,
        )

        detections: List[Detection] = []
        violations: List[Detection] = []
        person_boxes: List[List[float]] = []

        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                cls_id   = int(box.cls[0])
                conf     = float(box.conf[0])
                x1,y1,x2,y2 = box.xyxyn[0].tolist()
                cls_name = self._model.names.get(cls_id, f"class_{cls_id}")
                det      = Detection(class_id=cls_id, class_name=cls_name, confidence=conf, bbox=[x1,y1,x2,y2])
                if cls_name.lower() == "person" or cls_id == 5:
                    person_boxes.append([x1, y1, x2, y2])
                vtype = ROBOFLOW_CLASS_MAP.get(cls_id)
                if vtype and conf >= settings.VIOLATION_CONFIDENCE_THRESHOLD:
                    det.violation_type = vtype
                    det.severity       = VIOLATION_SEVERITY[vtype]
                    violations.append(det)
                detections.append(det)

        # Restricted zone check
        if restricted_zone_polygons:
            for pb in person_boxes:
                cx, cy = (pb[0]+pb[2])/2, (pb[1]+pb[3])/2
                px, py = int(cx*w), int(cy*h)
                for poly in restricted_zone_polygons:
                    pts = np.array([[int(p[0]*w), int(p[1]*h)] for p in poly])
                    if cv2.pointPolygonTest(pts, (float(px), float(py)), False) >= 0:
                        violations.append(Detection(
                            class_id=-1, class_name="restricted_zone",
                            confidence=1.0, bbox=pb,
                            violation_type=ViolationType.RESTRICTED_ZONE,
                            severity=Severity.HIGH,
                        ))
                        break

        # BUG-7 FIX: scaffold overcrowding — only count persons INSIDE a
        # designated scaffold zone polygon, not the whole frame.
        # If no zones configured, fall back to full-frame count (legacy behaviour).
        if restricted_zone_polygons:
            for poly in restricted_zone_polygons:
                pts = np.array([[int(p[0]*w), int(p[1]*h)] for p in poly])
                in_zone = sum(
                    1 for pb in person_boxes
                    if cv2.pointPolygonTest(pts, (float(int((pb[0]+pb[2])/2*w)), float(int((pb[1]+pb[3])/2*h))), False) >= 0
                )
                if in_zone >= overcrowd_threshold:
                    violations.append(Detection(
                        class_id=-2, class_name="scaffold_overcrowd",
                        confidence=1.0, bbox=[0,0,1,1],
                        violation_type=ViolationType.SCAFFOLD_OVERCROWD,
                        severity=Severity.HIGH,
                    ))
        elif len(person_boxes) >= overcrowd_threshold:
            violations.append(Detection(
                class_id=-2, class_name="scaffold_overcrowd",
                confidence=1.0, bbox=[0,0,1,1],
                violation_type=ViolationType.SCAFFOLD_OVERCROWD,
                severity=Severity.HIGH,
            ))

        annotated    = self._annotate(frame, detections, violations)
        inference_ms = (time.perf_counter() - t0) * 1000

        return InferenceResult(
            frame_id=frame_id, camera_id=camera_id,
            timestamp=datetime.now(timezone.utc),
            detections=detections, violations=violations,
            person_count=len(person_boxes),
            annotated_frame=annotated, inference_ms=inference_ms,
        )

    def _annotate(self, frame: np.ndarray, detections: List[Detection], violations: List[Detection]) -> np.ndarray:
        h, w  = frame.shape[:2]
        out   = frame.copy()
        vtypes = {v.violation_type for v in violations}
        for det in detections:
            x1,y1,x2,y2 = det.bbox
            px1,py1 = int(x1*w), int(y1*h)
            px2,py2 = int(x2*w), int(y2*h)
            if det.violation_type:
                color, label, thick = BBOX_COLORS.get(det.severity,(0,0,220)), f"{VIOLATION_LABELS.get(det.violation_type,det.class_name)} {det.confidence:.2f}", 2
            else:
                color, label, thick = (60,200,60), f"{det.class_name} {det.confidence:.2f}", 1
            cv2.rectangle(out,(px1,py1),(px2,py2),color,thick)
            ly = max(py1-6,16)
            (lw,lh),_ = cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,0.45,1)
            cv2.rectangle(out,(px1,ly-lh-4),(px1+lw+4,ly+2),color,-1)
            cv2.putText(out,label,(px1+2,ly-1),cv2.FONT_HERSHEY_SIMPLEX,0.45,(255,255,255),1)
        if vtypes:
            ov = out.copy()
            cv2.rectangle(ov,(0,0),(w,28),(0,0,180),-1)
            cv2.addWeighted(ov,0.6,out,0.4,0,out)
            msg = "VIOLATION: " + ", ".join(VIOLATION_LABELS.get(vt,str(vt)) for vt in vtypes)
            cv2.putText(out,msg,(8,18),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),1)
        return out

    def encode_jpeg(self, frame: np.ndarray, quality: int = 80) -> bytes:
        _,buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes()

    def save_snapshot(self, frame: np.ndarray, camera_id: int, vtype: str) -> str:
        ts   = datetime.now(timezone.utc)
        sub  = Path(settings.SNAPSHOT_DIR) / str(ts.year) / f"{ts.month:02d}" / f"{ts.day:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        fname = f"cam{camera_id}_{vtype}_{ts.strftime('%H%M%S%f')}.jpg"
        fpath = sub / fname
        cv2.imwrite(str(fpath), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return str(fpath.relative_to(settings.SNAPSHOT_DIR))


detector = PPEDetector()
