#!/usr/bin/env python3
"""
Remove background from image corners and auto-crop to content bounds.

Uses flood-fill from corners and edge midpoints to remove uniform backgrounds,
then crops to the bounding box of remaining non-transparent pixels.

Params:
  alpha_threshold - Alpha threshold for transparency detection (default: "10")
  padding - Padding pixels around detected content (default: "0") 
  bg_tolerance - Color tolerance for background removal (default: "40")
"""
import io
from PIL import Image, ImageDraw
import numpy as np
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "alpha_threshold", "description": "Alpha threshold for transparency detection", "default_value": "10"},
    {"name": "padding", "description": "Padding pixels around detected content", "default_value": "0"},
    {"name": "bg_tolerance", "description": "Color tolerance for background removal", "default_value": "40"}
]

def remove_bg_corners(img, tolerance=40):
    """Use Pillow built-in floodfill from all 4 corners + edge midpoints to remove background."""
    img = img.copy()
    w, h = img.size
    # Seed points: 4 corners + 4 edge midpoints for better coverage
    seeds = [
        (0, 0), (w-1, 0), (0, h-1), (w-1, h-1),
        (w//2, 0), (w//2, h-1), (0, h//2), (w-1, h//2)
    ]
    transparent = (0, 0, 0, 0)
    for sx, sy in seeds:
        pixel = img.getpixel((sx, sy))
        # Only flood-fill if the pixel is mostly opaque (part of background)
        if len(pixel) >= 4 and pixel[3] < 20:
            continue  # already transparent, skip
        try:
            ImageDraw.floodfill(img, (sx, sy), transparent, thresh=tolerance)
        except Exception:
            pass
    return img

def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    alpha_threshold = int(params.get("alpha_threshold", "10"))
    padding = int(params.get("padding", "0"))
    bg_tolerance = int(params.get("bg_tolerance", "40"))

    img = Image.open(io.BytesIO(input_bytes)).convert("RGBA")

    # Step 1: Flood-fill from corners and edge midpoints to remove backgrounds
    img = remove_bg_corners(img, tolerance=bg_tolerance)

    # Step 2: Find bounding box of non-transparent pixels and crop
    arr = np.array(img)
    alpha = arr[:, :, 3]
    rows = np.any(alpha > alpha_threshold, axis=1)
    cols = np.any(alpha > alpha_threshold, axis=0)

    if not np.any(rows) or not np.any(cols):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png", trimmed=False, reason="fully_transparent")
        return

    row_indices = np.where(rows)[0]
    col_indices = np.where(cols)[0]
    rmin, rmax = row_indices[0], row_indices[-1]
    cmin, cmax = col_indices[0], col_indices[-1]
    
    h, w = arr.shape[:2]
    rmin = max(0, rmin - padding)
    rmax = min(h - 1, rmax + padding)
    cmin = max(0, cmin - padding)
    cmax = min(w - 1, cmax + padding)
    cropped = img.crop((cmin, rmin, cmax + 1, rmax + 1))

    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    orig_w, orig_h = img.size
    new_w, new_h = cropped.size
    write_output(
        buf.getvalue(), "image/png",
        trimmed=True,
        original_size=[orig_w, orig_h],
        trimmed_size=[new_w, new_h],
        crop_box=[int(cmin), int(rmin), int(cmax + 1), int(rmax + 1)],
        alpha_threshold=alpha_threshold,
        bg_tolerance=bg_tolerance,
        padding=padding,
    )

if __name__ == "__main__":
    main()
