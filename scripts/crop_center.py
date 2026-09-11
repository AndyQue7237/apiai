#!/usr/bin/env python3
"""
Auto-crop an image to its content (removing a uniform background detected from
the top-left corner pixel), then optionally centre it on a chosen aspect ratio
with a margin.

Params:
  fuzz          - Colour tolerance for background matching (0-255, default "10")
  margin        - Margin around the content as % of its longest side (default "0" = tight)
  target_format - Output aspect ratio: original (default), 1:1, 3:4, 4:3, 9:16, 16:9.
                  Content is centred and padded (never cropped) to this aspect,
                  filled with the detected background colour.
"""
import io

import numpy as np
from PIL import Image
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "fuzz", "description": "Colour tolerance for background matching (0-255)", "default_value": "10"},
    {"name": "margin", "description": "Margin around the content as % of its longest side (0 = tight)", "default_value": "0"},
    {"name": "target_format", "description": "Output aspect ratio: original, 1:1, 3:4, 4:3, 9:16, 16:9. Content is centred and padded (no crop) to this aspect.", "default_value": "original"},
]

# Supported output aspect ratios (width / height)
ASPECTS = {"1:1": 1.0, "3:4": 3 / 4, "4:3": 4 / 3, "9:16": 9 / 16, "16:9": 16 / 9}


def content_bbox(img_rgb, bg_color, fuzz):
    """Bounding box of pixels whose Euclidean colour distance from bg_color > fuzz.
    Vectorised with numpy — the old per-pixel Python loop was very slow on large images."""
    arr = np.asarray(img_rgb, dtype=np.int16)
    diff = arr - np.asarray(bg_color, dtype=np.int16)
    dist = np.sqrt((diff.astype(np.float32) ** 2).sum(axis=2))
    ys, xs = np.where(dist > fuzz)
    if len(xs) == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def centre_on_canvas(img, fill, margin_px, target_format):
    """Add margin_px around img, then pad (never crop) to target_format, centred."""
    w, h = img.size
    base_w, base_h = w + 2 * margin_px, h + 2 * margin_px

    aspect = ASPECTS.get(target_format)
    if aspect is None:                    # 'original' -> just the margin box
        cw, ch = base_w, base_h
    elif base_w / base_h > aspect:        # too wide -> grow height
        cw, ch = base_w, int(round(base_w / aspect))
    else:                                 # too tall -> grow width
        cw, ch = int(round(base_h * aspect)), base_h

    canvas = Image.new(img.mode, (cw, ch), fill)
    mask = img if img.mode in ("RGBA", "LA") else None
    canvas.paste(img, ((cw - w) // 2, (ch - h) // 2), mask)
    return canvas


def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    try:
        fuzz = int(params.get("fuzz", "10"))
        if not (0 <= fuzz <= 255):
            write_error("fuzz must be between 0 and 255")
            return

        margin_pct = float(params.get("margin", "0") or "0")
        if margin_pct < 0:
            write_error("margin must be >= 0")
            return

        target_format = (params.get("target_format") or "original").strip().lower()
        if target_format != "original" and target_format not in ASPECTS:
            write_error("target_format must be one of: original, " + ", ".join(ASPECTS))
            return

        img = Image.open(io.BytesIO(input_bytes))
        has_alpha = img.mode in ("RGBA", "LA", "P")

        # Detect content on an RGB view; the bbox applies to the original (keeps alpha).
        rgb = img.convert("RGB")
        bg_color = rgb.getpixel((0, 0))          # top-left corner = background reference
        bbox = content_bbox(rgb, bg_color, fuzz)
        if bbox is None:
            write_error("no content detected (image looks uniform) — try a higher fuzz")
            return
        cropped = img.crop(bbox)

        # Nothing else requested: return the tight crop (old behaviour, unchanged).
        if margin_pct == 0 and target_format == "original":
            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
            write_output(buf.getvalue(), "image/png")
            return

        # Margin in px, relative to the content's longest side.
        margin_px = int(round(max(cropped.size) * margin_pct / 100.0))

        # Fill: transparent for images with alpha, else the detected background colour.
        if has_alpha:
            work, fill = cropped.convert("RGBA"), (0, 0, 0, 0)
        else:
            work, fill = cropped.convert("RGB"), bg_color

        result = centre_on_canvas(work, fill, margin_px, target_format)

        buf = io.BytesIO()
        result.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png")

    except Exception as e:
        write_error(f"processing failed: {str(e)}")


if __name__ == "__main__":
    main()
