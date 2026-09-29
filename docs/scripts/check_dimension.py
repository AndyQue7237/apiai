#!/usr/bin/env python3
"""
Check whether an image has sufficient minimum dimension (width or height).

Outputs the image unchanged plus a metadata field set to "true" or "false".
The field name is configurable via the `field` param so it can feed directly
into a condition node.

Use case: Conditional processing in pipelines - Recraft Vectorize requires
minimum dimension > 256 pixels.

Params:
  field      - metadata field name to write (default: "is_large_enough")
  min_pixels - minimum pixels for smallest side (default: 256)

Examples:
  1920x1080 with min_pixels=256 → is_large_enough: true (min=1080 > 256)
  200x300   with min_pixels=256 → is_large_enough: false (min=200 < 256)
  256x256   with min_pixels=256 → is_large_enough: false (min=256 not > 256)
"""
import sys
import json
import base64
import io
from PIL import Image


def check_dimension(img, min_pixels=256):
    """
    Check if image has sufficient minimum dimension.

    Args:
        img: PIL Image object
        min_pixels: Minimum pixels threshold for smallest side

    Returns:
        tuple: (is_large_enough: bool, metadata: dict)
    """
    width, height = img.size
    min_dimension = min(width, height)

    is_large_enough = min_dimension > min_pixels

    metadata = {
        "width": width,
        "height": height,
        "min_dimension": min_dimension,
        "threshold": min_pixels,
        "is_large_enough": is_large_enough
    }

    return is_large_enough, metadata


def main():
    data = json.load(sys.stdin)
    img_bytes = base64.b64decode(data["image"])
    img = Image.open(io.BytesIO(img_bytes))
    params = data.get("params", {})

    field = params.get("field", "is_large_enough")
    min_pixels = int(params.get("min_pixels", "256"))

    result, _ = check_dimension(img, min_pixels)

    # Pass image through as RGBA PNG
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
