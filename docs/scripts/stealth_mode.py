#!/usr/bin/env python3
"""
Stealth Mode — black-on-black embroidery preparation.

Converts a transparent logo to a tone-on-tone greyscale version:
1. Convert to greyscale
2. Normalize luminance to 0–85 range (based on actual min/max)
3. Fade dark tones (0–50) to transparent

Result: Only the lightest ~40% of tones remain visible as grey,
perfect for embroidery on black fabric where dark areas show through.

Params:
  fade_start  - Luminance below this = fully transparent (default: 0)
  fade_end    - Luminance above this = fully opaque (default: 50)
  max_lum     - Maximum output luminance (default: 85)
"""
import io
from PIL import Image
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "fade_start", "description": "Luminance below this = fully transparent", "default_value": "0"},
    {"name": "fade_end", "description": "Luminance above this = fully opaque", "default_value": "50"},
    {"name": "max_lum", "description": "Maximum output luminance", "default_value": "85"}
]


def process(img, params):
    fade_start = int(params.get("fade_start", "0"))
    fade_end = int(params.get("fade_end", "50"))
    max_output_lum = int(params.get("max_lum", "85"))

    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    grayscale = img.convert('L')

    stealth = Image.new('RGBA', img.size, (0, 0, 0, 0))
    px_orig = img.load()
    px_gray = grayscale.load()
    px_out = stealth.load()

    # Find actual luminance range (skip fully transparent pixels)
    min_lum = 255
    max_lum = 0
    has_visible_pixels = False
    
    for y in range(img.height):
        for x in range(img.width):
            _, _, _, a = px_orig[x, y]
            if a > 0:
                has_visible_pixels = True
                lum = px_gray[x, y]
                min_lum = min(min_lum, lum)
                max_lum = max(max_lum, lum)

    # Handle edge case where image has no visible pixels
    if not has_visible_pixels:
        return stealth

    lum_range = max(max_lum - min_lum, 1)

    # Remap luminance to stealth palette + fade dark tones
    for y in range(img.height):
        for x in range(img.width):
            _, _, _, a = px_orig[x, y]
            if a == 0:
                continue

            lum = px_gray[x, y]

            # Normalize to [0, max_output_lum]
            normalized = (lum - min_lum) / lum_range
            stealth_lum = int(normalized * max_output_lum)
            color = (stealth_lum, stealth_lum, stealth_lum)

            # Fade dark tones
            if stealth_lum <= fade_start:
                px_out[x, y] = color + (0,)
            elif stealth_lum < fade_end:
                fade_ratio = (stealth_lum - fade_start) / (fade_end - fade_start)
                px_out[x, y] = color + (int(a * fade_ratio),)
            else:
                px_out[x, y] = color + (a,)

    return stealth


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
