#!/usr/bin/env python3
"""
Flip an image horizontally or vertically.

Params:
  direction - Direction to flip: "horizontal" or "vertical" (default: "horizontal")
"""
import io
from PIL import Image
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "direction", "description": "Direction to flip the image", "default_value": "horizontal", "allowed_values": ["horizontal", "vertical"]},
]

def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    try:
        img = Image.open(io.BytesIO(input_bytes))
        
        direction = params.get("direction", "horizontal").lower()
        
        if direction == "vertical":
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        else:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png")
        
    except Exception as e:
        write_error(f"failed to process image: {str(e)}")

if __name__ == "__main__":
    main()
