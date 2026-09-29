#!/usr/bin/env python3
"""
Place a stylised advertising badge / text overlay on an image.

Produces Instagram-style promotional treatments such as "Summer Sale",
"Just In!", "50% Off", "New Arrival", etc.

Params:
  headline      - Main text line, e.g. "Summer Sale" (required)
  subline       - Optional smaller second line, e.g. "Up to 50% off"
  style         - Visual treatment to apply (default: "ribbon")
                  Options: ribbon, badge, sticker, pill, banner, tag
  position      - Where to place the overlay (default: "bottom-left")
                  Options: top-left, top-center, top-right,
                           center-left, center-center, center-right,
                           bottom-left, bottom-center, bottom-right
  color_scheme  - Colour palette (default: "coral")
                  Options: coral, midnight, lime, gold, pink, mono, sky
  font_size     - Headline font size in pixels, or "auto" (default: "auto")
  margin        - Gap from nearest edge in pixels (default: "30")
  text_padding  - Extra inner padding (px) between text and badge edges (default: "10")
  opacity       - Overall overlay opacity 0.0–1.0 (default: "1.0")
  rotation      - Rotate the badge in degrees, positive = clockwise (default: "0")
"""

import sys
import io
import math
import logging
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from script_io import read_input, write_output, write_error

log = logging.getLogger("advertising_badge")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")

# ── Parameter definitions ──────────────────────────────────────────────────────
PARAM_DEFS = [
    {
        "name": "headline",
        "description": "Main promotional text, e.g. Summer Sale, Just In!, New Arrival",
        "default_value": "",
        "required": True,
    },
    {
        "name": "subline",
        "description": "Optional smaller second line, e.g. Up to 50% off",
        "default_value": "",
    },
    {
        "name": "style",
        "description": "Visual treatment: ribbon, badge, sticker, pill, banner, tag",
        "default_value": "ribbon",
        "allowed_values": ["ribbon", "badge", "sticker", "pill", "banner", "tag"],
    },
    {
        "name": "position",
        "description": "Where to place the badge on the image",
        "default_value": "bottom-left",
        "allowed_values": [
            "top-left", "top-center", "top-right",
            "center-left", "center-center", "center-right",
            "bottom-left", "bottom-center", "bottom-right",
        ],
    },
    {
        "name": "color_scheme",
        "description": "Colour palette: coral, midnight, lime, gold, pink, mono, sky",
        "default_value": "coral",
        "allowed_values": ["coral", "midnight", "lime", "gold", "pink", "mono", "sky"],
    },
    {
        "name": "font_size",
        "description": "Headline font size in pixels, or auto to scale with image",
        "default_value": "auto",
    },
    {
        "name": "margin",
        "description": "Gap from nearest edges in pixels",
        "default_value": "30",
    },
    {
        "name": "text_padding",
        "description": "Extra inner padding in pixels between the text and the badge edges",
        "default_value": "10",
    },
    {
        "name": "opacity",
        "description": "Overall overlay opacity 0.0 (invisible) to 1.0 (fully opaque)",
        "default_value": "1.0",
    },
    {
        "name": "rotation",
        "description": "Badge rotation in degrees (positive = clockwise)",
        "default_value": "0",
    },
]

# ── Colour palettes ────────────────────────────────────────────────────────────
SCHEMES = {
    "coral":    {"bg": (255, 90, 75),    "bg2": (255, 130, 100),  "text": (255, 255, 255), "accent": (255, 220, 200)},
    "midnight": {"bg": (20, 20, 40),     "bg2": (40, 40, 80),     "text": (255, 255, 255), "accent": (150, 150, 255)},
    "lime":     {"bg": (50, 205, 100),   "bg2": (30, 170, 70),    "text": (255, 255, 255), "accent": (200, 255, 220)},
    "gold":     {"bg": (212, 175, 55),   "bg2": (180, 140, 20),   "text": (255, 255, 255), "accent": (255, 240, 180)},
    "pink":     {"bg": (255, 105, 180),  "bg2": (220, 60, 140),   "text": (255, 255, 255), "accent": (255, 210, 235)},
    "mono":     {"bg": (20, 20, 20),     "bg2": (60, 60, 60),     "text": (255, 255, 255), "accent": (180, 180, 180)},
    "sky":      {"bg": (30, 160, 230),   "bg2": (10, 120, 190),   "text": (255, 255, 255), "accent": (200, 235, 255)},
}

# ── Font loading ───────────────────────────────────────────────────────────────

_FONT_DIR = os.environ.get("FONT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts"))

FONT_DIRS = [
    _FONT_DIR,
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "/System/Library/Fonts",
    "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
]

BOLD_CANDIDATES = [
    "Montserrat-Bold.ttf", "Oswald-Bold.ttf", "PlayfairDisplay-Bold.ttf",
    "Inter-Bold.ttf", "Inter_Bold.ttf",
    "DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf",
    "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf",
    "Helvetica Bold.ttf", "helveticab.ttf",
]
REGULAR_CANDIDATES = [
    "OpenSans-Regular.ttf", "Lora-Regular.ttf", "Baloo2-Regular.ttf",
    "Inter-Regular.ttf", "Inter_Regular.ttf",
    "DejaVuSans.ttf", "Arial.ttf", "arial.ttf",
    "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf",
    "Helvetica.ttf", "helvetica.ttf",
]


def _find_font(candidates):
    for d in FONT_DIRS:
        for name in candidates:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None


def load_font(size, bold=False):
    path = _find_font(BOLD_CANDIDATES if bold else REGULAR_CANDIDATES)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    
    # Fallback to default font with better error handling
    try:
        return ImageFont.load_default(size)
    except (TypeError, AttributeError):
        # Older Pillow versions don't support size parameter
        return ImageFont.load_default()


# ── Helpers ────────────────────────────────────────────────────────────────────

def text_size(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font, anchor="lt")
    return bb[2], bb[3]


def anchor_position(bg_w, bg_h, overlay_w, overlay_h, position, margin):
    parts = position.split("-")
    vert  = parts[0] if len(parts) >= 1 else "bottom"
    horiz = parts[1] if len(parts) >= 2 else "left"

    if horiz == "left":
        x = margin
    elif horiz == "center":
        x = (bg_w - overlay_w) // 2
    else:
        x = bg_w - overlay_w - margin

    if vert == "top":
        y = margin
    elif vert == "center":
        y = (bg_h - overlay_h) // 2
    else:
        y = bg_h - overlay_h - margin

    return x, y


def add_shadow(layer, blur=6, offset=(3, 3), shadow_color=(0, 0, 0, 120)):
    """Return a soft drop-shadow layer the same size as `layer`."""
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    # Use alpha channel of layer as shadow mask
    alpha = layer.getchannel("A")
    shadow_solid = Image.new("RGBA", layer.size, shadow_color)
    shadow.paste(shadow_solid, mask=alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    result = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    result.paste(shadow, offset, shadow)
    result.paste(layer, (0, 0), layer)
    return result


# ── Style renderers ────────────────────────────────────────────────────────────

def render_ribbon(headline, subline, scheme, font_size, bg_w, text_padding=0):
    """Diagonal corner ribbon."""
    pad_x, pad_y = 20 + text_padding, 12 + text_padding
    font_h  = load_font(font_size, bold=True)
    font_s  = load_font(max(10, font_size - 6), bold=False)

    # Measure on temp canvas
    tmp = Image.new("RGBA", (1, 1))
    d   = ImageDraw.Draw(tmp)
    hw, hh = text_size(d, headline, font_h)
    sw, sh = (text_size(d, subline, font_s) if subline else (0, 0))

    width  = max(hw, sw) + pad_x * 2
    height = hh + (sh + 6 if subline else 0) + pad_y * 2

    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # Gradient-ish background (two rects)
    d.rectangle([0, 0, width, height // 2], fill=scheme["bg"] + (255,))
    d.rectangle([0, height // 2, width, height], fill=scheme["bg2"] + (255,))

    # Accent line top
    d.rectangle([0, 0, width, 4], fill=scheme["accent"] + (220,))

    # Text
    ty = pad_y
    d.text(((width - hw) // 2, ty), headline, font=font_h, fill=scheme["text"] + (255,), anchor="lt")
    if subline:
        ty += hh + 6
        d.text(((width - sw) // 2, ty), subline, font=font_s, fill=scheme["accent"] + (220,), anchor="lt")

    return layer


def render_badge(headline, subline, scheme, font_size, bg_w, text_padding=0):
    """Circular / oval badge."""
    font_h = load_font(font_size, bold=True)
    font_s = load_font(max(10, font_size - 8), bold=False)

    tmp = Image.new("RGBA", (1, 1))
    d   = ImageDraw.Draw(tmp)
    hw, hh = text_size(d, headline, font_h)
    sw, sh = (text_size(d, subline, font_s) if subline else (0, 0))

    pad = font_size + text_padding
    inner_w = max(hw, sw)
    inner_h = hh + (sh + 8 if subline else 0)
    diameter = max(inner_w, inner_h) + pad * 2
    size = diameter

    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # Outer ring
    d.ellipse([0, 0, size - 1, size - 1], fill=scheme["bg"] + (255,))
    ring = 4
    d.ellipse([ring, ring, size - 1 - ring, size - 1 - ring],
              fill=scheme["bg2"] + (255,))

    # Inner accent ring
    d.ellipse([ring + 6, ring + 6, size - 1 - ring - 6, size - 1 - ring - 6],
              outline=scheme["accent"] + (180,), width=2)

    cy = (size - inner_h) // 2
    d.text(((size - hw) // 2, cy), headline, font=font_h, fill=scheme["text"] + (255,), anchor="lt")
    if subline:
        d.text(((size - sw) // 2, cy + hh + 8), subline, font=font_s,
               fill=scheme["accent"] + (220,), anchor="lt")

    return layer


def render_sticker(headline, subline, scheme, font_size, bg_w, text_padding=0):
    """Rounded-rect sticker with a thick border."""
    font_h = load_font(font_size, bold=True)
    font_s = load_font(max(10, font_size - 6), bold=False)

    tmp = Image.new("RGBA", (1, 1))
    d   = ImageDraw.Draw(tmp)
    hw, hh = text_size(d, headline, font_h)
    sw, sh = (text_size(d, subline, font_s) if subline else (0, 0))

    pad_x, pad_y = 24 + text_padding, 16 + text_padding
    w = max(hw, sw) + pad_x * 2
    h = hh + (sh + 8 if subline else 0) + pad_y * 2
    r = 18  # corner radius

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=scheme["bg"] + (255,))
    border = 3
    d.rounded_rectangle([border, border, w - 1 - border, h - 1 - border],
                        radius=r - border, outline=scheme["accent"] + (200,), width=2)

    ty = pad_y
    d.text(((w - hw) // 2, ty), headline, font=font_h, fill=scheme["text"] + (255,), anchor="lt")
    if subline:
        ty += hh + 8
        d.text(((w - sw) // 2, ty), subline, font=font_s, fill=scheme["accent"] + (220,), anchor="lt")

    return layer


def render_pill(headline, subline, scheme, font_size, bg_w, text_padding=0):
    """Capsule / pill shape."""
    font_h = load_font(font_size, bold=True)
    font_s = load_font(max(10, font_size - 6), bold=False)

    tmp = Image.new("RGBA", (1, 1))
    d   = ImageDraw.Draw(tmp)
    hw, hh = text_size(d, headline, font_h)
    sw, sh = (text_size(d, subline, font_s) if subline else (0, 0))

    pad_x, pad_y = 30 + text_padding, 14 + text_padding
    w = max(hw, sw) + pad_x * 2
    h = hh + (sh + 8 if subline else 0) + pad_y * 2
    r = h // 2  # full pill

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=scheme["bg"] + (255,))

    ty = pad_y
    d.text(((w - hw) // 2, ty), headline, font=font_h, fill=scheme["text"] + (255,), anchor="lt")
    if subline:
        ty += hh + 8
        d.text(((w - sw) // 2, ty), subline, font=font_s, fill=scheme["accent"] + (220,), anchor="lt")

    return layer


def render_banner(headline, subline, scheme, font_size, bg_w, text_padding=0):
    """Full-width horizontal banner bar (always spans full width)."""
    font_h = load_font(font_size, bold=True)
    font_s = load_font(max(10, font_size - 6), bold=False)

    tmp = Image.new("RGBA", (1, 1))
    d   = ImageDraw.Draw(tmp)
    hw, hh = text_size(d, headline, font_h)
    sw, sh = (text_size(d, subline, font_s) if subline else (0, 0))

    pad_y = 18 + text_padding
    w = bg_w
    h = hh + (sh + 8 if subline else 0) + pad_y * 2

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([0, 0, w, h], fill=scheme["bg"] + (230,))
    d.rectangle([0, 0, w, 4], fill=scheme["accent"] + (230,))
    d.rectangle([0, h - 4, w, h], fill=scheme["accent"] + (230,))

    ty = pad_y
    d.text(((w - hw) // 2, ty), headline, font=font_h, fill=scheme["text"] + (255,), anchor="lt")
    if subline:
        ty += hh + 8
        d.text(((w - sw) // 2, ty), subline, font=font_s, fill=scheme["accent"] + (220,), anchor="lt")

    return layer


def render_tag(headline, subline, scheme, font_size, bg_w, text_padding=0):
    """Price-tag shape with a small hole cutout."""
    font_h = load_font(font_size, bold=True)
    font_s = load_font(max(10, font_size - 6), bold=False)

    tmp = Image.new("RGBA", (1, 1))
    d   = ImageDraw.Draw(tmp)
    hw, hh = text_size(d, headline, font_h)
    sw, sh = (text_size(d, subline, font_s) if subline else (0, 0))

    pad_x, pad_y = 22 + text_padding, 14 + text_padding
    hole = 14  # hole diameter at top
    w = max(hw, sw) + pad_x * 2
    h = hh + (sh + 8 if subline else 0) + pad_y * 2 + hole

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # Tag body
    body_h = h - hole // 2
    d.rounded_rectangle([0, hole // 2, w - 1, body_h], radius=10,
                        fill=scheme["bg"] + (255,))

    # Create hole using a mask approach
    mask = Image.new("L", (w, h), 255)
    mask_draw = ImageDraw.Draw(mask)
    hx = (w - hole) // 2
    mask_draw.ellipse([hx, 0, hx + hole, hole], fill=0)
    
    # Apply mask to layer
    layer.putalpha(mask)
    
    # Add hole outline
    d.ellipse([hx + 2, 2, hx + hole - 2, hole - 2],
              outline=scheme["accent"] + (200,), width=2)

    ty = hole // 2 + pad_y
    d.text(((w - hw) // 2, ty), headline, font=font_h, fill=scheme["text"] + (255,), anchor="lt")
    if subline:
        ty += hh + 8
        d.text(((w - sw) // 2, ty), subline, font=font_s, fill=scheme["accent"] + (220,), anchor="lt")

    return layer


RENDERERS = {
    "ribbon":  render_ribbon,
    "badge":   render_badge,
    "sticker": render_sticker,
    "pill":    render_pill,
    "banner":  render_banner,
    "tag":     render_tag,
}


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("No input image provided")
        return

    headline = params.get("headline", "").strip()
    if not headline:
        write_error("headline parameter is required")
        return

    subline      = params.get("subline", "").strip()
    style        = params.get("style", "ribbon").strip().lower()
    position     = params.get("position", "bottom-left").strip().lower()
    color_scheme = params.get("color_scheme", "coral").strip().lower()
    
    # Parameter validation with better error handling
    try:
        margin = max(0, int(params.get("margin", "30")))
        text_padding = max(0, int(params.get("text_padding", "10")))
        opacity = max(0.0, min(1.0, float(params.get("opacity", "1.0"))))
        rotation = float(params.get("rotation", "0"))
    except (ValueError, TypeError):
        write_error("Invalid numeric parameter values")
        return

    if style not in RENDERERS:
        style = "ribbon"
    if color_scheme not in SCHEMES:
        color_scheme = "coral"

    scheme = SCHEMES[color_scheme]
    renderer = RENDERERS[style]

    try:
        # Load background
        bg = Image.open(io.BytesIO(input_bytes)).convert("RGBA")
        bg_w, bg_h = bg.size

        # Auto font size: ~10% of shortest side, clamped 24–200px
        raw_fs = params.get("font_size", "auto").strip().lower()
        if raw_fs == "auto":
            font_size = max(24, min(int(min(bg_w, bg_h) * 0.10), 200))
        else:
            try:
                font_size = max(10, int(raw_fs))
            except (ValueError, TypeError):
                font_size = max(24, min(int(min(bg_w, bg_h) * 0.10), 200))

        # Render badge layer
        overlay = renderer(headline, subline, scheme, font_size, bg_w, text_padding)

        # Rotate if requested
        if rotation != 0:
            overlay = overlay.rotate(rotation, expand=True, resample=Image.BICUBIC)

        # Apply opacity
        if opacity < 1.0:
            r, g, b, a = overlay.split()
            a = a.point(lambda v: int(v * opacity))
            overlay = Image.merge("RGBA", (r, g, b, a))

        # Add drop shadow
        overlay = add_shadow(overlay, blur=8, offset=(4, 4))

        # Position on background
        ow, oh = overlay.size
        x, y = anchor_position(bg_w, bg_h, ow, oh, position, margin)
        
        # Banner style special positioning (always full width and positioned at edges)
        if style == "banner":
            x = 0
            if position.startswith("top"):
                y = 0
            elif position.startswith("center"):
                y = (bg_h - oh) // 2
            else:
                y = bg_h - oh

        out = bg.copy()
        out.paste(overlay, (x, y), overlay)

        buf = io.BytesIO()
        # Keep as RGBA to preserve transparency
        out.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png")

    except Exception as e:
        write_error(f"Processing failed: {str(e)}")


if __name__ == "__main__":
    main()
