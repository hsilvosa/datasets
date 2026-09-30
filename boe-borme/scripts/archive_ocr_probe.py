"""Verify the installed OCR engine using an in-memory Spanish test image."""
from __future__ import annotations

import io
import json

from PIL import Image, ImageDraw, ImageFont
from rapidocr_onnxruntime import RapidOCR


def main():
    image = Image.new("RGB", (1100, 180), "white")
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(image).text((25, 30), "Boletín Oficial del Estado. Artículo 1. Texto íntegro.",
                              fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    result, _ = RapidOCR()(buffer.getvalue())
    lines = [{"text": line[1], "confidence": float(line[2])} for line in (result or [])]
    if not lines:
        raise RuntimeError("OCR engine returned no text from the probe")
    print(json.dumps({"ocr_available": True, "lines": lines}, ensure_ascii=False))


if __name__ == "__main__":
    main()
