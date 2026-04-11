from PIL import Image
from manga_ocr import MangaOcr
from paddleocr import PaddleOCR
import numpy as np
import logging

# Silence PaddleOCR logs
logging.getLogger("ppocr").setLevel(logging.ERROR)

print("⏳ Loading OCR Models... (This happens only once)")

# 1. Initialize MangaOCR (Best for Japanese)
manga_model = MangaOcr()

# 2. Initialize PaddleOCR (Best for Chinese & Spanish)
ocr_zh = PaddleOCR(lang='ch')
ocr_es = PaddleOCR(lang='es')

print("🚀 OCR Systems Ready!")


def read_text_from_crops(image_path, bboxes, lang='ja'):
    """
    Extracts text from bounding boxes using the appropriate OCR model.
    """
    img = Image.open(image_path).convert('RGB')
    extracted_texts = []

    print(f"--- 📖 Reading {len(bboxes)} bubbles (Mode: {lang.upper()}) ---")

    for i, box in enumerate(bboxes):
        x, y, x_max, y_max = box

        # Safety Check: Ensure box is within image bounds
        if x < 0: x = 0
        if y < 0: y = 0
        if x_max > img.width: x_max = img.width
        if y_max > img.height: y_max = img.height

        # Crop the bubble
        crop = img.crop((x, y, x_max, y_max))

        try:
            # --- JAPANESE MODE (Vertical Text) ---
            if lang == 'ja':
                text = manga_model(crop)

            # --- CHINESE MODE (Horizontal Text) ---
            elif lang == 'zh':
                crop_np = np.array(crop)
                # THE FIX: Removed 'cls' entirely
                result = ocr_zh.ocr(crop_np)
                text = parse_paddle_result(result)

            # --- SPANISH MODE (Latin Text) ---
            elif lang == 'es':
                crop_np = np.array(crop)
                # THE FIX: Removed 'cls' entirely
                result = ocr_es.ocr(crop_np)
                text = parse_paddle_result(result)

            else:
                text = "Error: Unknown Lang"

            # Cleanup text
            text = text.strip()
            if not text:
                text = "..."

            extracted_texts.append(text)

        except Exception as e:
            print(f"❌ OCR Error on bubble {i}: {e}")
            extracted_texts.append("Error")

    return extracted_texts


def parse_paddle_result(result):
    """
    Helper to extract just the text string from PaddleOCR's complex output.
    """
    if not result or result[0] is None:
        return ""

    # Paddle returns: [[[[points], "text", conf], ...]]
    text_lines = [line[1][0] for line in result[0]]
    return " ".join(text_lines)