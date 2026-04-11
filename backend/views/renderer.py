from PIL import Image, ImageDraw, ImageFont

def render_translated_image(image_path, bboxes, translated_texts, output_filename="translated/translated_spanish_page.jpg"):
    print("4. Creating output image (View)...")
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Try to load a font, otherwise use default
    try:
        # standard windows font, change if on mac/linux
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()

    for i, box in enumerate(bboxes):
        x_min, y_min, x_max, y_max = box

        # Get the text (safely)
        if i < len(translated_texts):
            text = translated_texts[i]
        else:
            text = "..."

        # Draw white box (Simple Inpainting)
        draw.rectangle([x_min, y_min, x_max, y_max], fill="white", outline="black")
        draw.text((x_min + 5, y_min + 5), text, fill="black", font=font)

    img.save(output_filename)
    print(f"SUCCESS! Saved to {output_filename}")