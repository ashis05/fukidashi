"""Speech-bubble / text detection using ogkalu/comic-text-and-bubble-detector (RT-DETR)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from PIL import Image

MODEL_ID = "ogkalu/comic-text-and-bubble-detector"

BUBBLE = "bubble"
TEXT_BUBBLE = "text_bubble"
TEXT_FREE = "text_free"

Box = tuple[float, float, float, float]


@dataclass
class Detection:
    """A text region to OCR, plus the box to draw the overlay on."""

    text_box: tuple[int, int, int, int]  # OCR crop
    box: tuple[int, int, int, int]  # overlay box (bubble outline when known)
    kind: str  # text_bubble | text_free
    score: float = 0.0


# ---------------------------------------------------------------- geometry
def iou(a: Sequence[float], b: Sequence[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _area(b: Sequence[float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inside_fraction(inner: Sequence[float], outer: Sequence[float]) -> float:
    ix = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    iy = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    a = _area(inner)
    return (ix * iy) / a if a > 0 else 0.0


def nms(items: list[tuple[Box, float]], iou_threshold: float = 0.5) -> list[tuple[Box, float]]:
    """Greedy non-maximum suppression. Also drops boxes mostly contained in a higher-scoring one."""
    kept: list[tuple[Box, float]] = []
    for box, score in sorted(items, key=lambda t: t[1], reverse=True):
        dup = False
        for kb, _ in kept:
            if iou(box, kb) > iou_threshold or _inside_fraction(box, kb) > 0.9:
                dup = True
                break
        if not dup:
            kept.append((box, score))
    return kept


def pair_with_bubbles(
    texts: list[tuple[Box, float, str]],
    bubbles: list[Box],
    min_inside: float = 0.7,
) -> list[Detection]:
    """For each text region choose the smallest bubble that mostly contains it as overlay box."""
    out: list[Detection] = []
    for box, score, kind in texts:
        tb = tuple(int(round(v)) for v in box)
        overlay = tb
        if kind == TEXT_BUBBLE:
            best, best_area = None, None
            for bb in bubbles:
                if _inside_fraction(box, bb) >= min_inside:
                    a = _area(bb)
                    if best is None or a < best_area:
                        best, best_area = bb, a
            if best is not None:
                overlay = tuple(int(round(v)) for v in best)
        out.append(Detection(text_box=tb, box=overlay, kind=kind, score=float(score)))  # type: ignore[arg-type]
    return out


def reading_order(dets: list[Detection], lang: str = "ja") -> list[Detection]:
    """Sort into reading order. Rows are banded by vertical overlap; ja is right-to-left."""
    if not dets:
        return []
    rtl = lang in ("ja", "jp")
    by_top = sorted(dets, key=lambda d: (d.box[1] + d.box[3]) / 2)
    rows: list[list[Detection]] = []
    row_bounds: list[tuple[float, float]] = []
    for d in by_top:
        cy = (d.box[1] + d.box[3]) / 2
        h = d.box[3] - d.box[1]
        placed = False
        for i, (top, bottom) in enumerate(row_bounds):
            # same row if the centre falls within the row band (shrunk a bit)
            margin = 0.15 * (bottom - top)
            if top + margin <= cy <= bottom - margin or abs(cy - (top + bottom) / 2) < 0.25 * h:
                rows[i].append(d)
                row_bounds[i] = (min(top, d.box[1]), max(bottom, d.box[3]))
                placed = True
                break
        if not placed:
            rows.append([d])
            row_bounds.append((d.box[1], d.box[3]))
    order = sorted(range(len(rows)), key=lambda i: row_bounds[i][0])
    result: list[Detection] = []
    for i in order:
        cx = lambda d: (d.box[0] + d.box[2]) / 2  # noqa: E731
        result.extend(sorted(rows[i], key=cx, reverse=rtl))
    return result


def build_detections(
    raw: list[tuple[str, Box, float]],
    lang: str = "ja",
    threshold: float = 0.4,
    nms_iou: float = 0.5,
) -> list[Detection]:
    """raw = [(label_name, box, score)] -> ordered Detections. Pure python, easy to test."""
    raw = [r for r in raw if r[2] >= threshold]
    bubbles = [b for b, _ in nms([(r[1], r[2]) for r in raw if r[0] == BUBBLE], nms_iou)]
    texts: list[tuple[Box, float, str]] = []
    for kind in (TEXT_BUBBLE, TEXT_FREE):
        for box, score in nms([(r[1], r[2]) for r in raw if r[0] == kind], nms_iou):
            texts.append((box, score, kind))
    # a text_free box overlapping a text_bubble box is the same text
    tb = [t for t in texts if t[2] == TEXT_BUBBLE]
    texts = [t for t in texts if t[2] == TEXT_BUBBLE or not any(iou(t[0], o[0]) > nms_iou for o in tb)]
    return reading_order(pair_with_bubbles(texts, bubbles), lang)


# ------------------------------------------------------------------ device
def pick_device() -> str:
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


class Detector:
    """Lazy-loading RT-DETR wrapper. Model loads on first use (or load())."""

    def __init__(self, model_id: str = MODEL_ID, threshold: float = 0.4, device: str | None = None):
        self.model_id = model_id
        self.threshold = threshold
        self.device = device
        self._model = None
        self._processor = None
        self._id2label: dict[int, str] = {}

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        from transformers import RTDetrForObjectDetection, RTDetrImageProcessor

        self.device = self.device or pick_device()
        self._processor = RTDetrImageProcessor.from_pretrained(self.model_id)
        model = RTDetrForObjectDetection.from_pretrained(self.model_id)
        if self.device == "cuda":
            model = model.half()
        model.to(self.device).eval()
        self._model = model
        self._id2label = {int(k): str(v).lower() for k, v in model.config.id2label.items()}

    def detect(self, image: Image.Image, lang: str = "ja", threshold: float | None = None) -> list[Detection]:
        import torch

        self.load()
        thr = self.threshold if threshold is None else threshold
        image = image.convert("RGB")
        inputs = self._processor(images=image, return_tensors="pt")
        dtype = next(self._model.parameters()).dtype
        inputs = {
            k: (v.to(self.device, dtype=dtype) if v.is_floating_point() else v.to(self.device))
            for k, v in inputs.items()
        }
        with torch.no_grad():
            outputs = self._model(**inputs)
        target = torch.tensor([image.size[::-1]], device=outputs.logits.device)
        results = self._processor.post_process_object_detection(
            outputs, target_sizes=target, threshold=min(thr, 0.3)
        )
        raw: list[tuple[str, Box, float]] = []
        for res in results:
            for score, label_id, box in zip(res["scores"], res["labels"], res["boxes"]):
                name = self._id2label.get(int(label_id))
                if name is None:
                    continue
                b = [float(x) for x in box.float().cpu().tolist()]
                raw.append((name, (b[0], b[1], b[2], b[3]), float(score)))
        w, h = image.size
        dets = build_detections(raw, lang=lang, threshold=thr)
        for d in dets:
            d.text_box = _clamp(d.text_box, w, h)
            d.box = _clamp(d.box, w, h)
        return [d for d in dets if d.text_box[2] > d.text_box[0] and d.text_box[3] > d.text_box[1]]


def _clamp(b, w: int, h: int):
    return (max(0, b[0]), max(0, b[1]), min(w, b[2]), min(h, b[3]))
