#!/usr/bin/env python3
"""
Check whether an image has sufficient resolution (total pixels).

Outputs the image unchanged plus a metadata field set to "true" or "false".
The field name is configurable via the `field` param so it can feed directly
into a condition node.

Use case: Conditional upscaling in pipelines - only upscale low-res images.
Note: Replicate Upscaler has a limit of width * height > 2,000,000 pixels.

Params:
  field      - metadata field name to write (default: "is_high_resolution")
  max_pixels - total pixels (width x height) threshold (default: 2000000)

Examples:
  1920x1080 (2,073,600) with max_pixels=2000000 → is_high_resolution: true
  1000x1000 (1,000,000) with max_pixels=2000000 → is_high_resolution: false
"""
import sys
import json
import base64
import io
from PIL import Image


def check_resolution(img, max_pixels=2000000):
    """
    Check if image has sufficient resolution (total pixels).

    Args:
        img: PIL Image object
        max_pixels: Total pixels threshold (width x height)

    Returns:
        tuple: (is_high_resolution: bool, metadata: dict)
    """
    width, height = img.size
    total_pixels = width * height

    is_high_res = total_pixels >= max_pixels

    metadata = {
        "width": width,
        "height": height,
        "total_pixels": total_pixels,
        "threshold": max_pixels,
        "is_high_resolution": is_high_res
    }

    return is_high_res, metadata


def main():
    data = json.load(sys.stdin)
    img_bytes = base64.b64decode(data["image"])
    img = Image.open(io.BytesIO(img_bytes))
    params = data.get("params", {})

    field = params.get("field", "is_high_resolution")
    max_pixels = int(params.get("max_pixels", "2000000"))

    result, _ = check_resolution(img, max_pixels)

    # Pass image through as RGBA PNG (matches check_transparency.py)
    out = img.convert("RGBA")
    buf = io.BytesIO()
    out.save(buf, format="PNG")

    json.dump({
        "image": base64.b64encode(buf.getvalue()).decode(),
        "content_type": "image/png",
        field: result,
    }, sys.stdout)


if __name__ == "__main__":
    main()
