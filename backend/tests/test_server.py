from fukidashi.config import Settings
from fukidashi.ocr import OCRUnavailableError
from fukidashi.server import create_app

from conftest import FakeDetector, FakeOCR, FakeTranslator, make_png


def post(client, data=None, lang="ja", ctype="image/png", name="a.png"):
    return client.post("/translate", files={"file": (name, data, ctype)}, data={"source_lang": lang})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok" and j["translator"] == "fake" and "ja" in j["languages"]


def test_translate_contract(client):
    r = post(client, make_png())
    assert r.status_code == 200
    j = r.json()
    assert j["width"] == 200 and j["height"] == 120
    assert j["data"][0]["box"] == [5, 5, 70, 70]
    assert j["data"][0]["text"] == "SRC0"
    assert j["data"][1]["kind"] == "text_free"
    assert all(len(d["box"]) == 4 for d in j["data"])


def test_default_lang_and_jpeg(client):
    r = client.post("/translate", files={"file": ("a.jpg", make_png(fmt="JPEG"), "image/jpeg")})
    assert r.status_code == 200


def test_too_large(client):
    r = post(client, b"\0" * (1024 * 1024 + 10))
    assert r.status_code == 413


def test_bad_image(client):
    assert post(client, b"not an image").status_code == 400


def test_bad_lang(client):
    assert post(client, make_png(), lang="xx").status_code == 400


def test_bad_content_type(client):
    assert post(client, make_png(), ctype="text/plain").status_code == 400


def test_ocr_unavailable_maps_to_501():
    class Bad(FakeOCR):
        def read_many(self, *a, **k):
            raise OCRUnavailableError("paddleocr missing")

    from fastapi.testclient import TestClient

    c = TestClient(create_app(Settings(rate_limit="0/minute"), detector=FakeDetector(), ocr=Bad(),
                              translator=FakeTranslator()))
    r = post(c, make_png(), lang="zh")
    assert r.status_code == 501 and "paddleocr" in r.json()["detail"]


def test_rate_limit():
    from fastapi.testclient import TestClient

    c = TestClient(create_app(Settings(rate_limit="1/minute"), detector=FakeDetector(), ocr=FakeOCR(),
                              translator=FakeTranslator()))
    assert post(c, make_png()).status_code == 200
    assert post(c, make_png()).status_code == 429


def test_cors_extension_origin(client):
    r = client.options("/translate", headers={"Origin": "chrome-extension://abcdefgh",
                                              "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "chrome-extension://abcdefgh"


def test_noise_not_translated():
    from fastapi.testclient import TestClient

    tr = FakeTranslator()
    c = TestClient(create_app(Settings(rate_limit="0/minute"), detector=FakeDetector(),
                              ocr=FakeOCR(["...", "hello"]), translator=tr))
    j = post(c, make_png()).json()
    assert tr.calls == [["hello"]]
    assert len(j["data"]) == 1 and j["data"][0]["text"] == "HELLO"
