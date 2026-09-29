#!/usr/bin/env python3
"""
Apply Gaussian blur effect to an image.

Params:
  radius - Blur radius in pixels (default: "5")
"""
import io
from PIL import Image, ImageFilter
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "radius", "description": "Blur radius in pixels", "default_value": "5"},
]

def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    try:
        img = Image.open(io.BytesIO(input_bytes))
        radius = float(params.get("radius", "5"))
        
        img = img.filter(ImageFilter.GaussianBlur(radius=radius))
        
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png")
        
    except Exception as e:
        write_error(str(e))

if __name__ == "__main__":
    main()
