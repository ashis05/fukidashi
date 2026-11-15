import io

import pytest
from PIL import Image

from fukidashi.config import Settings
from fukidashi.detector import Detection
from fukidashi.server import create_app


class FakeDetector:
    device = "cpu"
    loaded = True

    def __init__(self, dets=None):
        self.dets = dets if dets is not None else [
            Detection((10, 10, 60, 60), (5, 5, 70, 70), "text_bubble", 0.9),
            Detection((100, 20, 150, 50), (100, 20, 150, 50), "text_free", 0.8),
        ]

    def detect(self, image, lang="ja", threshold=None):
        return list(self.dets)

    def load(self):
        pass


class FakeOCR:
    def __init__(self, texts=None):
        self.texts = texts

    def read_many(self, image, boxes, lang="ja"):
        return self.texts or [f"src{i}" for i in range(len(boxes))]

    def loaded_engines(self):
        return []

    def warmup(self, lang="ja"):
        pass


class FakeTranslator:
    name = "fake"

    def __init__(self):
        self.calls = []

    def translate(self, texts, source_lang, target_lang="en"):
        self.calls.append(list(texts))
        return [t.upper() for t in texts]


def make_png(size=(200, 120), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, "gray").save(buf, fmt)
    return buf.getvalue()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    app = create_app(Settings(max_upload_mb=1, rate_limit="0/minute"),
                     detector=FakeDetector(), ocr=FakeOCR(), translator=FakeTranslator())
    return TestClient(app)
