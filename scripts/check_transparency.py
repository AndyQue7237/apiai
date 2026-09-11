#!/usr/bin/env python3
"""
Check whether an image has a transparent background.

Outputs the image unchanged plus a metadata field set to "true" or "false".
The field name is configurable via the `field` param so it can feed directly
into a condition node.

Params:
  field          - metadata field name to write (default: "is_transparent")
  threshold      - alpha value below which a pixel counts as transparent (default: 250)
  sample_percent - % of sampled pixels that must be transparent to qualify (default: 10)
"""
import sys
import json
import base64
import io
from PIL import Image


def has_transparency(img, threshold=250, sample_percent=10):
    """Return True if the image has meaningful transparency."""
    if img.mode not in ("RGBA", "LA", "PA"):
        return False

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    pixels = img.load()
    w, h = img.size

    transparent = 0
    total = 0

    step_x = max(1, w // 20)
    step_y = max(1, h // 20)

    for x in range(0, w, step_x):
        for y in range(0, h, step_y):
            _, _, _, a = pixels[x, y]
            total += 1
            if a < threshold:
                transparent += 1

    if total == 0:
        return False

    return (transparent / total * 100) > sample_percent


def main():
    data = json.load(sys.stdin)
    img_bytes = base64.b64decode(data["image"])
    img = Image.open(io.BytesIO(img_bytes))
    params = data.get("params", {})

    field = params.get("field", "is_transparent")
    threshold = int(params.get("threshold", "250"))
    sample_percent = int(params.get("sample_percent", "10"))

    result = has_transparency(img, threshold, sample_percent)

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
