import torch
from PIL import Image
from transformers import RTDetrForObjectDetection, RTDetrImageProcessor

# --- GLOBAL VARIABLES ---
_model = None
_processor = None
MODEL_ID = "ogkalu/comic-text-and-bubble-detector"


def get_detector():
    global _model, _processor
    if _model is None:
        print("⏳ Loading Detector model... (This happens only once)")
        _processor = RTDetrImageProcessor.from_pretrained(MODEL_ID)
        _model = RTDetrForObjectDetection.from_pretrained(MODEL_ID)

        if torch.cuda.is_available():
            print("🚀 Detector using CUDA (GPU)!")
            _model.to('cuda')
        else:
            print("⚠️ Detector using CPU")
    return _model, _processor


def detect_bubbles(image_path):
    model, processor = get_detector()

    print(f"Analyzing: {image_path}...")
    image = Image.open(image_path).convert("RGB")

    # Prepare image
    inputs = processor(images=image, return_tensors="pt")

    # Move inputs to GPU if model is on GPU
    if torch.cuda.is_available():
        inputs = {k: v.to('cuda') for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    # Post-process
    # Note: target_sizes must be on CPU for the processor
    target_sizes = torch.tensor([image.size[::-1]])

    results = processor.post_process_object_detection(
        outputs, target_sizes=target_sizes, threshold=0.3
    )

    bboxes = []
    for result in results:
        for score, label_id, box in zip(result["scores"], result["labels"], result["boxes"]):
            # label 0 = text
            if score > 0.4 and label_id == 0:
                # box is likely on GPU, move to CPU for list conversion
                box = box.cpu().tolist()
                bboxes.append([int(x) for x in box])

    return bboxes