from types import SimpleNamespace

import pytest

from fukidashi.translate import (FallbackTranslator, GeminiTranslator, GoogleTranslator,
                                 make_translator, translate_lines)
from fukidashi.config import Settings


class FakeClient:
    def __init__(self, text=None, exc=None):
        self.text, self.exc, self.prompts = text, exc, []
        self.models = self

    def generate_content(self, model, contents, config=None):
        self.prompts.append(contents)
        if self.exc:
            raise self.exc
        return SimpleNamespace(text=self.text)


class FakeGoogle:
    def __init__(self, src, tgt):
        pass

    def translate(self, t):
        return "g:" + t


def google():
    return GoogleTranslator(client_factory=FakeGoogle)


def test_google_parallel():
    assert google().translate(["a", "b"], "ja") == ["g:a", "g:b"]


def test_gemini_ok_single_call_with_all_lines():
    c = FakeClient('["one", "two"]')
    g = GeminiTranslator("k", client=c)
    assert g.translate(["い", "ろ"], "ja") == ["one", "two"]
    assert len(c.prompts) == 1 and "い" in c.prompts[0] and "ろ" in c.prompts[0]


def test_gemini_fenced_json():
    g = GeminiTranslator("k", client=FakeClient('```json\n["x"]\n```'))
    assert g.translate(["a"], "ja") == ["x"]


@pytest.mark.parametrize("client", [FakeClient('["only one"]'), FakeClient("garbage"),
                                    FakeClient(exc=TimeoutError("boom"))])
def test_fallback_to_google(client):
    f = FallbackTranslator(GeminiTranslator("k", client=client), google())
    assert f.translate(["a", "b"], "ja") == ["g:a", "g:b"]
    assert f.last_used == "google"


def test_fallback_not_used_on_success():
    f = FallbackTranslator(GeminiTranslator("k", client=FakeClient('["1","2"]')), google())
    assert f.translate(["a", "b"], "ja") == ["1", "2"] and f.last_used == "gemini"


def test_translate_lines_skips_noise():
    seen = []

    class T:
        name = "t"

        def translate(self, texts, s, t="en"):
            seen.append(texts)
            return [x + "!" for x in texts]

    assert translate_lines(T(), ["hi", "...", None, "", "yo"], "ja") == ["hi!", None, None, None, "yo!"]
    assert seen == [["hi", "yo"]]


def test_key_not_in_repr_and_selection():
    s = Settings(translator="gemini", gemini_api_key="SECRETKEY")
    t = make_translator(s)
    assert "SECRETKEY" not in repr(t.primary) and "SECRETKEY" not in repr(s)
    assert make_translator(Settings()).name == "google"


def test_settings_default_backend(monkeypatch):
    monkeypatch.delenv("TRANSLATOR", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert Settings.from_env(load_env_file=False).translator == "gemini"
    monkeypatch.delenv("GEMINI_API_KEY")
    assert Settings.from_env(load_env_file=False).translator == "google"
