"""detect -> OCR -> translate, with injectable components."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict

from PIL import Image

from .detector import Detection
from .ocr import is_noise
from .translate import translate_lines

log = logging.getLogger("fukidashi.pipeline")


@dataclass
class Item:
    box: list[int]  # overlay box [x1,y1,x2,y2]
    text: str  # translation
    source: str  # OCR text
    kind: str
    text_box: list[int] = field(default_factory=list)

    def public(self) -> dict:
        return {"box": self.box, "text": self.text, "source": self.source, "kind": self.kind}


@dataclass
class PageResult:
    width: int
    height: int
    items: list[Item]
    elapsed_ms: int = 0
    translator: str = ""

    def to_dict(self) -> dict:
        return {
            "data": [i.public() for i in self.items],
            "width": self.width,
            "height": self.height,
            "elapsed_ms": self.elapsed_ms,
            "translator": self.translator,
        }


def translate_page(image: Image.Image, source_lang: str = "ja", target_lang: str = "en",
                   *, detector, ocr, translator) -> PageResult:
    t0 = time.perf_counter()
    image = image.convert("RGB")
    dets: list[Detection] = detector.detect(image, lang=source_lang)
    if not dets:
        return PageResult(image.width, image.height, [], int((time.perf_counter() - t0) * 1000),
                          getattr(translator, "name", ""))

    texts = ocr.read_many(image, [d.text_box for d in dets], source_lang)
    # None = OCR error, noise = nothing readable: neither is sent to the translator
    lines = [None if (t is None or is_noise(t)) else t for t in texts]
    translated = translate_lines(translator, lines, source_lang, target_lang)

    items = [
        Item(box=list(d.box), text=tr, source=src, kind=d.kind, text_box=list(d.text_box))
        for d, src, tr in zip(dets, texts, translated)
        if tr
    ]
    used = getattr(translator, "last_used", getattr(translator, "name", ""))
    return PageResult(image.width, image.height, items, int((time.perf_counter() - t0) * 1000), used)


__all__ = ["Item", "PageResult", "translate_page", "asdict"]
