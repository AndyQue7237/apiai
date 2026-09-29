#!/usr/bin/env python3
"""Convert an image to grayscale."""
import sys
import json
import base64
import io
from PIL import Image
from script_io import read_input, write_output, write_error


def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    img = Image.open(io.BytesIO(input_bytes))

    # Convert to grayscale, preserving transparency if present
    if img.mode == "RGBA":
        r, g, b, a = img.split()
        grey = img.convert("L")
        result = Image.merge("RGBA", (grey, grey, grey, a))
    elif img.mode == "LA":
        l, a = img.split()
        result = Image.merge("LA", (l, a))
    else:
        result = img.convert("L").convert("RGB")

    buf = io.BytesIO()
    has_alpha = result.mode in ("RGBA", "LA")
    fmt = "PNG" if has_alpha or content_type == "image/png" else "JPEG"
    ct = "image/png" if has_alpha else (content_type or "image/png")
    result.save(buf, format=fmt)
    write_output(buf.getvalue(), ct)


if __name__ == "__main__":
    main()
