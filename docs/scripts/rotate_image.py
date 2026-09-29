#!/usr/bin/env python3
"""
Rotate an image by a specified angle.

Params:
  angle - rotation angle in degrees (default: "90")
  expand - whether to expand canvas to fit rotated image (default: "true")
"""
import io
from PIL import Image
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "angle", "description": "Rotation angle in degrees", "default_value": "90"},
    {"name": "expand", "description": "Expand canvas to fit rotated image", "default_value": "true", "allowed_values": ["true", "false"]},
]

def process(img, params):
    """Rotate the image by the specified angle."""
    angle = float(params.get("angle", "90"))
    expand = params.get("expand", "true").lower() == "true"
    
    img = img.convert("RGBA")
    img = img.rotate(angle, expand=expand, resample=Image.BICUBIC)
    
    return img

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
