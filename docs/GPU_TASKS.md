# Fukidashi: work for the GPU machine

This is a brief for a coding agent (Claude Code) running on a PC with an NVIDIA GPU. Read it top to bottom, then work through the tasks **in order**. Earlier tasks are verification that later ones depend on.

## Context

Fukidashi translates manga in the browser. A Chrome extension (`frontend/`, Manifest V3, no build step) screenshots the visible tab and POSTs it to a local FastAPI server (`backend/fukidashi/`). The server detects text with RT-DETR (`ogkalu/comic-text-and-bubble-detector`, labels `bubble`, `text_bubble`, `text_free`), reads it with manga-ocr (Japanese) or PaddleOCR (others), translates the page with Gemini (one call, reading order) or Google Translate as fallback, and returns boxes + English. The extension draws white bubbles with the English over the page.

The backend and extension were rewritten on a machine **without a GPU**. The 30 pytest tests use fake models, so **the real model code has never run**. Treat `detector.py` `Detector.load/detect`, `ocr.py` `_make_manga_ocr/_make_paddle`, and `translate.py` `GeminiTranslator` as unverified.

Key files:
- `backend/fukidashi/pipeline.py`: `translate_page(image, source_lang, *, detector, ocr, translator) -> PageResult`
- `backend/fukidashi/detector.py`: `Detector` (lazy load, fp16 on cuda), `build_detections`, `nms`, `pair_with_bubbles`, `reading_order`
- `backend/fukidashi/ocr.py`: `OCR` (lazy per-language engines), `read_many`
- `backend/fukidashi/translate.py`: `GoogleTranslator`, `GeminiTranslator`, `FallbackTranslator`
- `backend/fukidashi/render.py`: `draw_translations` (used by the CLI)
- `backend/fukidashi/server.py`: `create_app(settings, *, detector, ocr, translator)`, `/translate`, `/health`, one-at-a-time GPU lock
- `backend/fukidashi/cli.py`: `python -m fukidashi translate <files|dirs> -o out/` and `serve`
- `frontend/background.js` (capture + fetch), `frontend/content.js` (overlay, toast), `frontend/popup.*`

## Ground rules

- Work on a branch per task group and open a PR against `master` (`gh pr create`). Do not push to `master`.
- Keep `cd backend && pytest` green. Add tests for new pure logic, using fakes like the existing suite, so it still runs without a GPU.
- Never commit `.env`, API keys, model weights, or copyrighted manga pages. Test images go in `backend/samples/` which must be gitignored (add it). The only images allowed in git are README screenshots in `docs/readme/` (crop or blur to a small excerpt, and use pages you are allowed to show).
- Heavy imports (torch, transformers, manga_ocr, paddleocr, lama, google.genai) stay lazy, inside functions.
- Keep the HTTP contract backward compatible: new response fields are fine, renamed ones are not.
- When something from this file is done, tick it here and update `README.md` (especially the **Limits** section) so the docs never claim more than the code does.
- Report real numbers you measured. Do not invent benchmarks.

---

## Part 1: verify on the GPU (do these first)

### 1.1 Environment
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt -r requirements-dev.txt
pytest
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```
Done when: tests pass and CUDA is visible. If a pinned lower bound in `requirements.txt` is wrong, fix it.

### 1.2 Batch CLI end to end
Put 5 to 10 raw manga pages (different series, some with free text and SFX) in `backend/samples/` and run:
```bash
python -m fukidashi translate samples/ -o out/ --lang ja
```
Fix whatever breaks. Likely suspects:
- **fp16:** `Detector.load` calls `model.half()` on cuda. If outputs are empty or NaN, or `post_process_object_detection` errors on dtype, keep the model in fp32, or cast `outputs.logits`/`pred_boxes` to float before post-processing. Compare detections fp16 vs fp32 on the same page; keep fp16 only if they match.
- `post_process_object_detection` signature or `target_sizes` device for the installed transformers version.
- manga-ocr first-run download and its device (it picks CUDA itself).
- `render.py` font: on Windows `FUKIDASHI_FONT` may need setting. Check that wrapped text fits.

Done when: every sample produces an output image, and you have looked at each one.

### 1.3 Tune detection
For the samples, dump the raw detections (label, score, box) and check:
- `DETECT_THRESHOLD` (default 0.4; `detect()` pre-filters at `min(thr, 0.3)`). Pick the value with the fewest misses without junk boxes.
- `pair_with_bubbles` (`min_inside=0.7`): does the English cover the whole bubble?
- `reading_order`: Japanese pages read right to left, top to bottom. Check a page with an irregular panel layout. If the row banding is wrong, improve it (e.g. order by panel first; a simple panel splitter on the white gutters is acceptable).
- Add any fixes as pure functions with unit tests.

### 1.4 Server + extension end to end
```bash
python -m fukidashi serve          # WARMUP=1 to load models at startup
```
Load `frontend/` unpacked in Chrome (`chrome://extensions` → Developer mode → Load unpacked). On a real manga reader site, check:
- Translate button, Alt+Shift+T, Alt+Shift+H, the toast, popup status.
- Overlay position on a page that scrolls the document, and on a reader that scrolls an inner container.
- Translate twice in a row: the second capture must not contain the first overlay.
- Auto mode across "next page" clicks, and after Chrome idles for a minute (service worker restart).
- A custom server URL (e.g. an ngrok tunnel) triggers the permission prompt and works after granting.
- With and without `GEMINI_API_KEY`: `/health` shows the translator, and the response `translator` field says which one was used. With Gemini, check the reply really is one item per line and in order.

Fix bugs you find. Done when all of the above work.

### 1.5 Measure
Time it with models already loaded on a typical 1280×720 capture: detection, OCR, translation, total (`elapsed_ms`), plus VRAM use (`torch.cuda.max_memory_allocated`). Add a short **Performance** section to the README with the GPU name and the numbers.

### 1.6 README screenshots
Add a before/after pair (original crop vs translated crop) to `docs/readme/` and show it in the README under "How it works". Keep it a small excerpt. Also send the measured numbers to the portfolio owner (they go in the portfolio case study `web/src/content/cases/fukidashi.ts` in the separate `ashiswadhwani.in` repo; do not edit that repo unless asked).

---

## Part 2: features worth adding

Do these after Part 1, one PR each, in this order.

### 2.1 Real text removal (inpainting)
Goal: erase the original lettering and put the English on the original art, instead of a white box.

- **Text mask:** inside each `text_box`, threshold dark pixels (Otsu on the grey crop), dilate a few px, and only keep the mask inside the bubble when there is one. Keep this in a pure function with tests.
- **Inpainting:** LaMa (big-lama via a pip package such as `simple-lama-inpainting`, or the official checkpoint with torch) on a padded crop around each bubble, not the whole page. Lazy-load, keep it on GPU, behind the same lock. Make it optional: `INPAINT=lama|none` (default `none` until it is proven), and a `clean` form field on `/translate`.
- **Fast path:** for plain white bubbles (most pixels near white), just fill the mask with the bubble's median background colour. Skip the model; it is faster and just as good.
- **API:** when `clean=1`, each item gets `patch`: a base64 PNG of the cleaned crop, plus `patch_box` (where it goes). Old clients ignore it.
- **Extension:** if `patch` is present, draw it as the bubble background (an `<img>` at `patch_box`) with the English on top, no white fill. Add a popup toggle "Clean bubbles (slower)".
- **CLI:** `--clean` renders onto the inpainted page.
- Measure the added time per page and put it in the README. Done when a bubble over screentone or art looks clean with no white box.

### 2.2 Result cache
Goal: going back a page, or re-translating the same screen, is instant.

- **Server:** an LRU cache (e.g. 512 entries) keyed by a perceptual hash (dHash 16×16) of the uploaded image + `source_lang` + translator. On a hit, return the cached result with `"cached": true`. Also cache OCR→translation per line text, so the same line is never sent to Gemini twice.
- **Extension:** keep the last result per (tab URL, scroll position) in `chrome.storage.session`. If the user returns to the same spot, redraw without a request.
- Tests for the hash-keyed cache (same image hits, a changed image misses).

### 2.3 Translate ahead (stretch; needs a design decision first)
The screenshot approach can only see the current screen, so "translate the next page in advance" needs a second input path:
- The content script lists the large `<img>` elements on the page (and the next-page link's images if the reader preloads them). The background fetches those image URLs (needs host permission for the image CDN) and posts them to a new `/translate` mode that takes an image URL or bytes plus the element's on-page size. Boxes are then mapped onto the `<img>` element rather than the viewport.
- This also enables translating a long vertical webtoon strip in one pass, not just the visible part.
- Write a short design note in the PR first (permissions it needs, how boxes map onto `<img>` elements, canvas-tainting/CORS issues), then build it behind a popup option "Image mode (beta)". Keep screenshot mode as the default.

### 2.4 Docker with GPU
- `backend/Dockerfile` on an `nvidia/cuda` runtime base (or `pytorch/pytorch` CUDA runtime image), installing requirements, running `python -m fukidashi serve --host 0.0.0.0`.
- `docker-compose.yml` with `deploy.resources.reservations.devices` (nvidia, all GPUs), a named volume for the Hugging Face cache (`HF_HOME`) so models download once, `env_file: .env` (optional), port 8000 bound to `127.0.0.1` only.
- README section "Run with Docker". Done when `docker compose up` serves `/health` with `device: cuda`.

---

## Finish

When a part is done: update the README, tick the boxes below, and list in the PR description what you verified by hand and what you could not.

- [ ] 1.1 Environment
- [ ] 1.2 Batch CLI end to end
- [ ] 1.3 Detection tuning
- [ ] 1.4 Server + extension end to end
- [ ] 1.5 Performance numbers
- [ ] 1.6 README screenshots
- [ ] 2.1 Inpainting
- [ ] 2.2 Result cache
- [ ] 2.3 Translate ahead / image mode
- [ ] 2.4 Docker with GPU
