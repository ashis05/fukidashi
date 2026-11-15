from PIL import Image

from fukidashi.ocr import OCR, OCRUnavailableError, UnsupportedLanguageError, is_noise, parse_paddle_result
from fukidashi.render import draw_translations, fit_text, get_font, wrap_text

import pytest


def test_wrap_and_fit():
    font = get_font(20)
    lines = wrap_text("hello wonderful world of manga", font, 100)
    assert len(lines) > 1
    assert all(font.getlength(l) <= 100 for l in lines)
    f, lines, fits = fit_text("A fairly long sentence that needs shrinking", 80, 60)
    assert fits and len(lines) * f.size <= 60 * 1.3
    assert all(f.getlength(l) <= 80.5 for l in lines)


def test_long_word_split():
    font = get_font(20)
    lines = wrap_text("Supercalifragilisticexpialidocious", font, 60)
    assert len(lines) > 1


def test_draw_changes_box_only():
    img = Image.new("RGB", (200, 100), "black")
    out = draw_translations(img, [((20, 20, 120, 80), "Hello there")])
    assert out.getpixel((25, 50)) == (255, 255, 255) or out.getpixel((70, 25)) == (255, 255, 255)
    assert out.getpixel((190, 90)) == (0, 0, 0)
    assert img.getpixel((50, 50)) == (0, 0, 0)  # input untouched


def test_ocr_lazy_cached_and_errors():
    built = []

    def factory():
        built.append(1)
        return lambda im: " text "

    ocr = OCR({"ja": factory})
    img = Image.new("RGB", (50, 50))
    assert ocr.read_many(img, [(0, 0, 20, 20), (0, 0, 30, 30)], "ja") == ["text", "text"]
    assert len(built) == 1
    with pytest.raises(UnsupportedLanguageError):
        ocr.read(img, (0, 0, 5, 5), "xx")

    def bad():
        raise OCRUnavailableError("nope")

    with pytest.raises(OCRUnavailableError):
        OCR({"ch": bad}).read(img, (0, 0, 20, 20), "zh")


def test_ocr_failure_marks_none():
    def f():
        def run(im):
            raise RuntimeError("x")
        return run

    assert OCR({"ja": f}).read_many(Image.new("RGB", (50, 50)), [(0, 0, 20, 20)], "ja") == [None]


def test_noise_and_paddle_parse():
    assert is_noise("...") and is_noise(" ") and not is_noise("a")
    assert parse_paddle_result([[[[0, 0], ("hello", 0.9)], [[0, 0], ("world", 0.9)]]]) == "hello world"
    assert parse_paddle_result([{"rec_texts": ["a", "b"]}]) == "a b"
    assert parse_paddle_result([None]) == ""
