"""Command line: `python -m fukidashi translate ...` and `python -m fukidashi serve`."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def collect_images(paths) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out.extend(sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS))
        elif p.is_file():
            out.append(p)
        else:
            print(f"warning: {p} not found", file=sys.stderr)
    return out


def cmd_translate(args) -> int:
    from PIL import Image

    from .config import Settings
    from .detector import Detector
    from .ocr import OCR
    from .pipeline import translate_page
    from .render import draw_translations
    from .translate import make_translator

    settings = Settings.from_env()
    images = collect_images(args.inputs)
    if not images:
        print("no input images", file=sys.stderr)
        return 2
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    detector = Detector(threshold=args.threshold or settings.detect_threshold)
    ocr, translator = OCR(), make_translator(settings)
    for path in images:
        with Image.open(path) as im:
            img = im.convert("RGB")
        res = translate_page(img, args.lang, "en", detector=detector, ocr=ocr, translator=translator)
        rendered = draw_translations(img, [(i.box, i.text) for i in res.items], settings.font or None)
        dest = out_dir / f"{path.stem}.{args.format}"
        rendered.save(dest, quality=92) if args.format == "jpg" else rendered.save(dest)
        print(f"{path} -> {dest} ({len(res.items)} bubbles, {res.elapsed_ms} ms)")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .config import Settings

    s = Settings.from_env()
    uvicorn.run("fukidashi.server:get_app", factory=True, host=args.host or s.host, port=args.port or s.port)
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="fukidashi")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("translate", help="translate image files or folders")
    t.add_argument("inputs", nargs="+")
    t.add_argument("-o", "--output", default="out")
    t.add_argument("--lang", default="ja")
    t.add_argument("--format", choices=["jpg", "png"], default="jpg")
    t.add_argument("--threshold", type=float, default=None)
    t.set_defaults(func=cmd_translate)
    s = sub.add_parser("serve", help="run the HTTP server")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.set_defaults(func=cmd_serve)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
