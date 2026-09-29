#!/usr/bin/env python3
"""
Adjust image brightness and contrast levels.

Params:
  brightness - brightness multiplier (default: "1.0")
  contrast - contrast multiplier (default: "1.0")
"""
import io
from PIL import Image, ImageEnhance
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "brightness", "description": "Brightness multiplier (0.1 = very dark, 1.0 = normal, 2.0 = very bright)", "default_value": "1.0"},
    {"name": "contrast", "description": "Contrast multiplier (0.1 = low contrast, 1.0 = normal, 2.0 = high contrast)", "default_value": "1.0"},
]

def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    try:
        img = Image.open(io.BytesIO(input_bytes))

        brightness = float(params.get("brightness", "1.0"))
        contrast = float(params.get("contrast", "1.0"))

        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png")

    except Exception as e:
        write_error(str(e))

if __name__ == "__main__":
    main()
