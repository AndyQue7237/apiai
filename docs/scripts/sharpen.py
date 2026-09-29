#!/usr/bin/env python3
"""
Apply unsharp mask filter to sharpen an image.

Params:
  radius - Blur radius for the mask (default: "2.0")
  percent - Sharpening strength percentage (default: "150")
  threshold - Minimum contrast threshold (default: "3")
"""
import io
from PIL import Image, ImageFilter
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "radius", "description": "Blur radius for the mask", "default_value": "2.0"},
    {"name": "percent", "description": "Sharpening strength percentage", "default_value": "150"},
    {"name": "threshold", "description": "Minimum contrast threshold", "default_value": "3"},
]


def process(img, params):
    """Apply unsharp mask filter to the image."""
    radius = float(params.get("radius", "2.0"))
    percent = int(params.get("percent", "150"))
    threshold = int(params.get("threshold", "3"))
    
    return img.filter(ImageFilter.UnsharpMask(
        radius=radius, percent=percent, threshold=threshold
    ))


def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    try:
        img = Image.open(io.BytesIO(input_bytes))
        result = process(img, params)
        
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png")
    except Exception as e:
        write_error(str(e))


if __name__ == "__main__":
    main()
