"""Runtime settings, read from environment variables (and a .env file if python-dotenv exists)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    max_upload_mb: int = 10
    detect_threshold: float = 0.4
    translator: str = "google"  # "google" | "gemini"
    gemini_api_key: str = field(default="", repr=False)
    gemini_model: str = "gemini-2.5-flash-lite"
    gemini_timeout: float = 30.0
    allowed_origins: list[str] = field(default_factory=list)
    font: str = ""
    rate_limit: str = "30/minute"
    warmup: bool = False

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @classmethod
    def from_env(cls, load_env_file: bool = True) -> "Settings":
        if load_env_file:
            _load_dotenv()
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        translator = os.environ.get("TRANSLATOR", "").strip().lower() or ("gemini" if key else "google")
        if translator not in ("google", "gemini"):
            translator = "google"
        origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
        return cls(
            host=os.environ.get("HOST", "127.0.0.1"),
            port=_int("PORT", 8000),
            max_upload_mb=_int("MAX_UPLOAD_MB", 10),
            detect_threshold=_float("DETECT_THRESHOLD", 0.4),
            translator=translator,
            gemini_api_key=key,
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite").strip() or "gemini-2.5-flash-lite",
            gemini_timeout=_float("GEMINI_TIMEOUT", 30.0),
            allowed_origins=origins,
            font=os.environ.get("FUKIDASHI_FONT", "").strip(),
            rate_limit=os.environ.get("RATE_LIMIT", "30/minute").strip(),
            warmup=_bool("WARMUP"),
        )
