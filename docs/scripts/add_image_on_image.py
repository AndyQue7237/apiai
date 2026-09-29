#!/usr/bin/env python3
"""
Place a logo / watermark image on top of a background image.

Params:
  overlay_image - PNG/JPEG logo to place on the background, uploaded as a file (required)
  position      - Placement on the canvas (default: "bottom-right")
                  Options: top-left, top-center, top-right,
                           center-left, center-center, center-right,
                           bottom-left, bottom-center, bottom-right
  scale         - Resize logo before placing:
                    0.01–1.0  = fraction of background width (e.g. 0.2 = 20 %)
                    >1        = pixel width (e.g. 200 = 200 px wide)
                  (default: "0.2")
  margin        - Gap from the nearest edges in pixels (default: "20")
  opacity       - Logo transparency 0.0 (invisible) to 1.0 (fully opaque) (default: "1.0")
  dropshadow    - Add a soft drop shadow beneath the logo (default: "false")
"""

import io
import logging
import sys
from PIL import Image, ImageFilter

from script_io import read_input, write_output, write_error

try:
    from script_io import decode_param_image
except ImportError:
    import base64 as _b64
    def decode_param_image(s): return _b64.b64decode(s)

log = logging.getLogger("image_logo_overlay")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")

PARAM_DEFS = [
    {
        "name": "overlay_image",
        "description": "PNG or JPEG logo / watermark to place on the image",
        "default_value": "",
        "required": True,
        "is_image": True
    },
    {
        "name": "position",
        "description": "Where to place the logo on the background image",
        "default_value": "bottom-right",
        "allowed_values": [
            "top-left", "top-center", "top-right",
            "center-left", "center-center", "center-right",
            "bottom-left", "bottom-center", "bottom-right"
        ]
    },
    {
        "name": "scale",
        "description": "Logo size: 0.01–1.0 = fraction of background width (0.2 = 20%), values above 1 = pixel width",
        "default_value": "0.2"
    },
    {
        "name": "margin",
        "description": "Gap from the nearest edges in pixels",
        "default_value": "20"
    },
    {
        "name": "opacity",
        "description": "Logo opacity from 0.0 (invisible) to 1.0 (fully opaque)",
        "default_value": "1.0"
    },
    {
        "name": "dropshadow",
        "description": "Add a soft drop shadow beneath the logo",
        "default_value": "false",
        "allowed_values": ["true", "false"]
    }
]


def compute_position(bg_w, bg_h, logo_w, logo_h, position, margin):
    """Return (x, y) top-left corner for the logo given the position name."""
    parts = position.split("-")
    if len(parts) == 2:
        vert, horiz = parts[0], parts[1]
    else:
        vert, horiz = "bottom", "right"

    if horiz == "left":
        x = margin
    elif horiz == "center":
        x = (bg_w - logo_w) // 2
    else:  # right
        x = bg_w - logo_w - margin

    if vert == "top":
        y = margin
    elif vert == "center":
        y = (bg_h - logo_h) // 2
    else:  # bottom
        y = bg_h - logo_h - margin

    # Ensure bounds
    x = max(0, min(x, bg_w - logo_w))
    y = max(0, min(y, bg_h - logo_h))

    return x, y


def apply_dropshadow(logo):
    """Add a drop shadow to the logo image."""
    shadow_offset = max(2, logo.width // 25)
    blur_radius = max(1, shadow_offset // 2)
    pad = shadow_offset * 2

    # Create shadow from logo alpha channel
    shadow_alpha = logo.split()[3].point(lambda v: int(v * 0.55))
    shadow_layer = Image.new("RGBA", logo.size, (0, 0, 0, 0))
    shadow_layer.putalpha(shadow_alpha)
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    # Combine shadow and logo on expanded canvas
    combined = Image.new("RGBA", (logo.width + pad, logo.height + pad), (0, 0, 0, 0))
    combined.paste(shadow_layer, (shadow_offset, shadow_offset), shadow_layer)
    combined.paste(logo, (0, 0), logo)

    return combined


def main():
    input_bytes, content_type, params = read_input()

    if not input_bytes:
        write_error("No background image provided")
        return

    overlay_b64 = params.get("overlay_image", "").strip()
    if not overlay_b64:
        write_error("overlay_image parameter is required")
        return

    position = params.get("position", "bottom-right").strip().lower()
    margin = int(params.get("margin", "20"))
    opacity = float(params.get("opacity", "1.0"))
    opacity = max(0.0, min(1.0, opacity))
    dropshadow = params.get("dropshadow", "false").strip().lower() in ("true", "1", "yes")

    try:
        scale = float(params.get("scale", "0.2"))
    except ValueError:
        scale = 0.2

    # Decode images
    try:
        bg = Image.open(io.BytesIO(input_bytes)).convert("RGBA")
    except Exception as e:
        write_error(f"Could not open background image: {e}")
        return

    try:
        logo_bytes = decode_param_image(overlay_b64)
        logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    except Exception as e:
        write_error(f"Could not decode overlay_image: {e}")
        return

    bg_w, bg_h = bg.size

    # Scale logo
    if scale <= 1.0:
        target_w = max(1, int(bg_w * scale))
    else:
        target_w = max(1, int(scale))
    
    ratio = target_w / logo.width
    target_h = max(1, int(logo.height * ratio))
    logo = logo.resize((target_w, target_h), Image.LANCZOS)

    # Apply opacity
    if opacity < 1.0:
        r, g, b, a = logo.split()
        a = a.point(lambda v: int(v * opacity))
        logo = Image.merge("RGBA", (r, g, b, a))

    # Add drop shadow if requested
    if dropshadow:
        logo = apply_dropshadow(logo)

    # Compute placement
    x, y = compute_position(bg_w, bg_h, logo.width, logo.height, position, margin)

    log.info("placing logo %dx%d at (%d,%d) pos=%s opacity=%.2f shadow=%s",
             logo.width, logo.height, x, y, position, opacity, dropshadow)

    # Composite
    result = bg.copy()
    result.paste(logo, (x, y), logo)

    # Encode output
    out_buf = io.BytesIO()
    result.convert("RGB").save(out_buf, format="PNG")
    write_output(out_buf.getvalue(), "image/png")


if __name__ == "__main__":
    main()
