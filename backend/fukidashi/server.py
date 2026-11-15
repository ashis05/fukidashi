"""FastAPI server used by the Fukidashi Chrome extension."""
from __future__ import annotations

import io
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image

from . import __version__
from .config import Settings
from .ocr import OCR, SUPPORTED_LANGS, OCRUnavailableError, is_supported
from .pipeline import translate_page

log = logging.getLogger("fukidashi.server")

Image.MAX_IMAGE_PIXELS = 60_000_000  # decompression-bomb guard (PIL warns >, errors at 2x)
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
MAX_SIDE = 4096  # downscale huge screenshots before inference (boxes are scaled back)


class RateLimiter:
    """Tiny in-memory sliding-window limiter, e.g. '30/minute'."""

    _UNITS = {"second": 1, "minute": 60, "hour": 3600}

    def __init__(self, spec: str):
        self.limit, self.window = 0, 60
        try:
            n, per = spec.split("/")
            self.limit = int(n)
            self.window = self._UNITS[per.strip().lower().rstrip("s")]
        except (ValueError, KeyError):
            self.limit = 0  # disabled
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def _err(status: int, msg: str) -> JSONResponse:
    return JSONResponse({"detail": msg}, status_code=status)


def create_app(settings: Settings | None = None, *, detector=None, ocr=None, translator=None) -> FastAPI:
    settings = settings or Settings.from_env()
    if detector is None:
        from .detector import Detector

        detector = Detector(threshold=settings.detect_threshold)
    if ocr is None:
        ocr = OCR()
    if translator is None:
        from .translate import make_translator

        translator = make_translator(settings)

    lock = threading.Lock()  # one inference at a time (GPU)
    limiter = RateLimiter(settings.rate_limit)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.warmup:
            def _warm():
                try:
                    detector.load()
                    ocr.warmup("ja")
                except Exception as e:  # noqa: BLE001
                    log.warning("warmup failed: %s", e)
            threading.Thread(target=_warm, daemon=True).start()
        yield

    app = FastAPI(title="Fukidashi", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_origin_regex=r"^chrome-extension://.+$",
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.state.settings = settings

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "version": __version__,
            "device": getattr(detector, "device", None),
            "detector_loaded": bool(getattr(detector, "loaded", False)),
            "ocr_engines": ocr.loaded_engines() if hasattr(ocr, "loaded_engines") else [],
            "translator": getattr(translator, "name", "unknown"),
            "languages": SUPPORTED_LANGS,
        }

    @app.post("/translate")
    async def translate(request: Request, file: UploadFile = File(...), source_lang: str = Form("ja")):
        client = request.client.host if request.client else "?"
        if not limiter.allow(client):
            return _err(429, "Rate limit exceeded")
        source_lang = (source_lang or "ja").strip().lower()
        if not is_supported(source_lang):
            return _err(400, f"Unsupported source_lang {source_lang!r}. Supported: {', '.join(SUPPORTED_LANGS)}")
        if file.content_type and file.content_type.lower() not in ALLOWED_TYPES and \
                not file.content_type.lower().startswith("application/octet"):
            return _err(400, f"Unsupported content type {file.content_type!r}; send a JPEG/PNG/WebP image")

        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > settings.max_upload_bytes + 64 * 1024:
            return _err(413, f"Upload too large (max {settings.max_upload_mb} MB)")
        data = await file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            return _err(413, f"Upload too large (max {settings.max_upload_mb} MB)")

        try:
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()
            image = Image.open(io.BytesIO(data))
            image.load()
            image = image.convert("RGB")
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            return _err(400, "Image dimensions too large")
        except Exception:  # noqa: BLE001
            return _err(400, "Could not decode image")

        scale = 1.0
        if max(image.size) > MAX_SIDE:
            scale = MAX_SIDE / max(image.size)
            image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)

        def work():
            with lock:
                return translate_page(image, source_lang, "en", detector=detector, ocr=ocr, translator=translator)

        try:
            result = await run_in_threadpool(work)
        except OCRUnavailableError as e:
            return _err(501, str(e))
        except Exception:  # noqa: BLE001
            log.exception("translate failed")
            return _err(500, "Internal error while translating")

        payload = result.to_dict()
        if scale != 1.0:
            inv = 1 / scale
            for it in payload["data"]:
                it["box"] = [round(v * inv) for v in it["box"]]
            payload["width"], payload["height"] = round(result.width * inv), round(result.height * inv)
        return payload

    return app


def get_app() -> FastAPI:
    """uvicorn factory: `uvicorn fukidashi.server:get_app --factory`."""
    return create_app()
