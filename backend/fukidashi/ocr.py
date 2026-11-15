"""OCR: manga-ocr for Japanese, PaddleOCR (optional) for other languages. Engines load lazily."""
from __future__ import annotations

import logging
import threading
from typing import Callable

from PIL import Image

log = logging.getLogger("fukidashi.ocr")

# Source language -> PaddleOCR lang code
PADDLE_LANGS = {
    "zh": "ch",
    "ko": "korean",
    "en": "en",
    "es": "es",
    "fr": "fr",
    "de": "german",
    "it": "it",
    "pt": "pt",
    "ru": "ru",
}
SUPPORTED_LANGS = ["ja", *PADDLE_LANGS]


class OCRUnavailableError(RuntimeError):
    """An OCR backend needed for the requested language is not installed."""


class UnsupportedLanguageError(ValueError):
    pass


def is_supported(lang: str) -> bool:
    return lang in SUPPORTED_LANGS


def is_noise(text: str) -> bool:
    """True for empty OCR output or placeholders that shouldn't be translated."""
    t = text.strip()
    return not t or not any(ch.isalnum() for ch in t)


def parse_paddle_result(result) -> str:
    """Handle both the legacy ([[box,(text,conf)],...]) and the 3.x (dict with rec_texts) outputs."""
    if not result:
        return ""
    parts: list[str] = []
    for page in result:
        if page is None:
            continue
        if isinstance(page, dict) or hasattr(page, "get") and not isinstance(page, (list, tuple)):
            parts.extend(str(t) for t in (page.get("rec_texts") or []))
            continue
        for line in page:
            try:
                parts.append(str(line[1][0]))
            except (IndexError, TypeError):
                continue
    return " ".join(p for p in parts if p).strip()


class OCR:
    def __init__(self, engine_factories: dict[str, Callable[[], Callable[[Image.Image], str]]] | None = None):
        self._engines: dict[str, Callable[[Image.Image], str]] = {}
        self._lock = threading.Lock()
        self._factories = engine_factories or {}

    def loaded_engines(self) -> list[str]:
        return sorted(self._engines)

    def _engine_key(self, lang: str) -> str:
        if not is_supported(lang):
            raise UnsupportedLanguageError(f"Unsupported source language: {lang!r}")
        return "ja" if lang == "ja" else PADDLE_LANGS[lang]

    def _get(self, lang: str):
        key = self._engine_key(lang)
        with self._lock:
            eng = self._engines.get(key)
            if eng is None:
                factory = self._factories.get(key) or (
                    _make_manga_ocr if key == "ja" else (lambda k=key: _make_paddle(k))
                )
                eng = factory()
                self._engines[key] = eng
        return eng

    def warmup(self, lang: str = "ja") -> None:
        self._get(lang)

    def read(self, image: Image.Image, box, lang: str = "ja") -> str:
        """OCR one region. Returns '' if nothing is read."""
        engine = self._get(lang)
        w, h = image.size
        x1, y1, x2, y2 = (int(v) for v in box)
        crop = image.crop((max(0, x1), max(0, y1), min(w, x2), min(h, y2))).convert("RGB")
        if crop.width < 2 or crop.height < 2:
            return ""
        return (engine(crop) or "").strip()

    def read_many(self, image: Image.Image, boxes, lang: str = "ja") -> list[str | None]:
        """One entry per box; None marks an OCR failure (so it is not sent to the translator)."""
        out: list[str | None] = []
        for i, b in enumerate(boxes):
            try:
                out.append(self.read(image, b, lang))
            except (OCRUnavailableError, UnsupportedLanguageError):
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("OCR failed on region %d: %s", i, e)
                out.append(None)
        return out


def _make_manga_ocr():
    try:
        from manga_ocr import MangaOcr
    except ImportError as e:
        raise OCRUnavailableError("manga-ocr is not installed (pip install manga-ocr) - required for Japanese") from e
    log.info("Loading manga-ocr...")
    model = MangaOcr()
    return lambda img: model(img)


def _make_paddle(paddle_lang: str):
    try:
        from paddleocr import PaddleOCR
    except ImportError as e:
        raise OCRUnavailableError(
            "paddleocr is not installed; install requirements-paddle.txt to OCR non-Japanese text"
        ) from e
    logging.getLogger("ppocr").setLevel(logging.ERROR)
    log.info("Loading PaddleOCR (%s)...", paddle_lang)
    import numpy as np

    model = PaddleOCR(lang=paddle_lang)

    def run(img: Image.Image) -> str:
        arr = np.array(img)
        try:
            res = model.ocr(arr, cls=False)
        except TypeError:  # PaddleOCR 3.x dropped 'cls'
            res = model.ocr(arr)
        return parse_paddle_result(res)

    return run
