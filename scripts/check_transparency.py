#!/usr/bin/env python3
"""
Check if an image has transparency and ensure RGBA mode.

Returns the image converted to RGBA. Adds a "has_transparency" field
to the output JSON (true/false) for use in pipeline decisions.

Params:
  threshold - Alpha threshold for "transparent" (default: 250)
  sample_percent - % of edge pixels that must be transparent (default: 10)
"""
import sys
import json
import base64
import io
from PIL import Image

try:
    from script_io import read_input, write_output, write_error
    HAS_SCRIPT_IO = True
except ImportError:
    HAS_SCRIPT_IO = False


def check_transparency(img, threshold=250, sample_percent=10):
    """Check if image has meaningful transparency."""
    if img.mode not in ('RGBA', 'LA', 'PA'):
        return False

    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    pixels = img.load()
    width, height = img.size

    transparent_count = 0
    total_checked = 0

    # Sample on a 20x20 grid
    step_x = max(1, width // 20)
    step_y = max(1, height // 20)

    for x in range(0, width, step_x):
        for y in range(0, height, step_y):
            _, _, _, a = pixels[x, y]
            total_checked += 1
            if a < threshold:
                transparent_count += 1

    if total_checked == 0:
        return False

    return (transparent_count / total_checked * 100) > sample_percent


def main():
    """Main entry point."""
    if HAS_SCRIPT_IO:
        # apiai.me runtime
        input_bytes, content_type, params = read_input()
        if not input_bytes:
            write_error("no input image provided")
            return

        img = Image.open(io.BytesIO(input_bytes))

        threshold = int(params.get("threshold", "250"))
        sample_percent = int(params.get("sample_percent", "10"))

        has_alpha = check_transparency(img, threshold, sample_percent)

        # Always output as RGBA PNG
        result = img.convert("RGBA")

        buf = io.BytesIO()
        result.save(buf, format="PNG")
        write_output(
            buf.getvalue(), "image/png",
            has_transparency=has_alpha,
        )
    else:
        # Local testing via stdin JSON
        data = json.load(sys.stdin)
        img_bytes = base64.b64decode(data["image"])
        img = Image.open(io.BytesIO(img_bytes))
        params = data.get("params", {})

        threshold = int(params.get("threshold", "250"))
        sample_percent = int(params.get("sample_percent", "10"))

        has_alpha = check_transparency(img, threshold, sample_percent)

        # Pass image through as RGBA PNG
        out = img.convert("RGBA")
        buf = io.BytesIO()
        out.save(buf, format="PNG")

        json.dump({
            "image": base64.b64encode(buf.getvalue()).decode(),
            "content_type": "image/png",
            "has_transparency": has_alpha,
        }, sys.stdout)


if __name__ == "__main__":
    main()
