from models.detector import detect_bubbles
from models.ocr import read_text_from_crops
from models.translator import translate_texts
from views.renderer import render_translated_image

def process_manga_page(image_path):
    print(f"--- Processing {image_path} ---")

    # 1. Detection (Model)
    print("1. Running Text Detection...")
    bboxes = detect_bubbles(image_path)
    if not bboxes:
        print("No text bubbles found! Exiting.")
        return

    # 2. OCR (Model)
    print(f"2. Running OCR on {len(bboxes)} bubbles...")
    original_texts = read_text_from_crops(image_path, bboxes)

    # 3. Translation (Model)
    print("3. Translating text...")
    try:
        translated_texts = translate_texts(original_texts)
    except Exception as e:
        print(f"Translation failed: {e}")
        translated_texts = ["Error"] * len(original_texts)

    # 4. Draw Results (View)
    render_translated_image(image_path, bboxes, translated_texts)