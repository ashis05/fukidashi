"""Translation backends: `google` (deep_translator, per line, parallel) and `gemini` (whole page, one call)."""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol, Sequence

log = logging.getLogger("fukidashi.translate")

_GOOGLE_CODES = {"zh": "zh-CN", "jp": "ja"}
_LANG_NAMES = {
    "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "en": "English", "es": "Spanish",
    "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese", "ru": "Russian",
}


class Translator(Protocol):
    name: str

    def translate(self, texts: Sequence[str], source_lang: str, target_lang: str = "en") -> list[str]: ...


def needs_translation(text: str | None) -> bool:
    if text is None:
        return False
    t = text.strip()
    return bool(t) and any(ch.isalnum() for ch in t)


class GoogleTranslator:
    name = "google"

    def __init__(self, max_workers: int = 8, client_factory=None):
        self.max_workers = max_workers
        self._client_factory = client_factory

    def _client(self, src: str, tgt: str):
        if self._client_factory:
            return self._client_factory(src, tgt)
        from deep_translator import GoogleTranslator as GT

        return GT(source=_GOOGLE_CODES.get(src, src), target=_GOOGLE_CODES.get(tgt, tgt))

    def translate(self, texts, source_lang, target_lang="en"):
        texts = list(texts)
        if not texts:
            return []
        client = self._client(source_lang, target_lang)

        def one(t: str) -> str:
            try:
                return client.translate(t) or t
            except Exception as e:  # noqa: BLE001
                log.warning("google translate failed for one line: %s", e)
                return t

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(texts))) as ex:
            return list(ex.map(one, texts))


class GeminiTranslator:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite", timeout: float = 30.0, client=None):
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = client

    def __repr__(self) -> str:  # never expose the key
        return f"GeminiTranslator(model={self.model!r})"

    def _get_client(self):
        if self._client is None:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=int(self.timeout * 1000)),
            )
        return self._client

    def _prompt(self, texts, src, tgt) -> str:
        s, t = _LANG_NAMES.get(src, src), _LANG_NAMES.get(tgt, tgt)
        payload = json.dumps([{"id": i, "text": x} for i, x in enumerate(texts)], ensure_ascii=False)
        return (
            f"You are translating the speech bubbles of one comic/manga page from {s} to {t}. "
            "The lines are in reading order and belong to the same scene, so use context for tone, "
            "pronouns and continuity. Keep translations concise enough to fit in a speech bubble. "
            "Keep sound effects short. Do not add notes.\n"
            f"Return ONLY a JSON array of exactly {len(texts)} strings, the translation of each line "
            "in the same order.\n\nLines:\n" + payload
        )

    def translate(self, texts, source_lang, target_lang="en"):
        texts = list(texts)
        if not texts:
            return []
        from_cfg = {"response_mime_type": "application/json"}
        resp = self._get_client().models.generate_content(
            model=self.model, contents=self._prompt(texts, source_lang, target_lang), config=from_cfg
        )
        out = parse_json_array(getattr(resp, "text", "") or "", len(texts))
        return out


def parse_json_array(raw: str, expected: int) -> list[str]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    data = json.loads(raw)
    if isinstance(data, dict):  # tolerate {"translations": [...]}
        lists = [v for v in data.values() if isinstance(v, list)]
        data = lists[0] if lists else data
    if not isinstance(data, list) or len(data) != expected:
        raise ValueError(f"expected JSON array of {expected} items")
    out = []
    for item in data:
        if isinstance(item, dict):
            item = item.get("text") or item.get("translation") or ""
        out.append(str(item).strip())
    return out


class FallbackTranslator:
    """Try `primary`; on any failure fall back to `fallback`."""

    def __init__(self, primary: Translator, fallback: Translator):
        self.primary, self.fallback = primary, fallback
        self.name = primary.name
        self.last_used = primary.name

    def translate(self, texts, source_lang, target_lang="en"):
        try:
            res = self.primary.translate(texts, source_lang, target_lang)
            if len(res) != len(texts) or any(not r for r in res):
                raise ValueError("incomplete translation")
            self.last_used = self.primary.name
            return res
        except Exception as e:  # noqa: BLE001
            log.warning("%s translator failed (%s: %s); falling back to %s",
                        self.primary.name, type(e).__name__, _scrub(str(e)), self.fallback.name)
            self.last_used = self.fallback.name
            return self.fallback.translate(texts, source_lang, target_lang)


def _scrub(msg: str) -> str:
    return re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "<redacted>", msg)[:300]


def translate_lines(translator: Translator, lines: Sequence[str | None], source_lang: str, target_lang: str = "en"):
    """Translate only the lines that need it; others yield None. Result has same length as `lines`."""
    idx = [i for i, t in enumerate(lines) if needs_translation(t)]
    result: list[str | None] = [None] * len(lines)
    if not idx:
        return result
    done = translator.translate([lines[i].strip() for i in idx], source_lang, target_lang)  # type: ignore[union-attr]
    for i, t in zip(idx, done):
        result[i] = t
    return result


def make_translator(settings) -> Translator:
    google = GoogleTranslator()
    if settings.translator == "gemini" and settings.gemini_api_key:
        return FallbackTranslator(
            GeminiTranslator(settings.gemini_api_key, settings.gemini_model, settings.gemini_timeout), google
        )
    return google
