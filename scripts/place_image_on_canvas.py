#!/usr/bin/env python3
"""
Place Image on Canvas — position a cut-out (transparent-background) subject on a
fixed-size canvas.

Finds the subject from the ALPHA channel (ignoring faint edge pixels), crops tight to it,
scales it to fill up to a chosen % of the canvas width and height (keeping proportions — the
image is never stretched), then places it on a fixed canvas. By default the subject is centred;
you can align it to an edge (top/bottom, left/right) and nudge it with an offset. The remaining
area is filled with a chosen background.

The canvas is a fixed size, so every output has the same dimensions — handy as a normalised
input to a downstream generative/edit step. The subject scales up until it touches whichever
bound (max_width or max_height) it reaches first, so its apparent size stays consistent. Set
the axis you care about tighter: max_height to size by height, max_width to size by width.

To ground a subject on a floor (air above, floor below): v_align = bottom, then y_offset a
few % up. To leave room for a logo/text on one side: h_align an edge, or use x_offset.

Note: a large offset can push the subject partly past a canvas edge — the overflow is simply
clipped. This is intentional (offsets are free positioning, not a bounded slider).

Params:
  canvas_width    - Output canvas width in pixels.
  canvas_height   - Output canvas height in pixels.
  max_width       - Subject is scaled to fill up to this % of the canvas width (keeps proportions).
  max_height      - Subject is scaled to fill up to this % of the canvas height (keeps proportions).
  h_align         - Horizontal placement: left, center, or right.
  x_offset        - Nudge left/right from that placement, as % of the canvas width.
  v_align         - Vertical placement: top, center, or bottom.
  y_offset        - Nudge up/down from that placement, as % of the canvas height.
  background      - Fill behind the subject: a hex colour like #e8e8e8, white, or transparent.
  min_opacity     - How solid a pixel must be (0-100%) to count as part of the subject; fainter
                    see-through edge pixels are treated as background.

Input:  PNG with a transparent background (a cut-out subject).
Output: RGBA PNG — the subject placed on the canvas.
"""
import io
import logging
import sys

from PIL import Image

try:
    from script_io import read_input, write_output, write_error
    SCRIPT_IO_AVAILABLE = True
except ImportError:  # local CLI runs without the apiai.me runtime
    SCRIPT_IO_AVAILABLE = False

log = logging.getLogger(__name__)

PARAM_DEFS = [
    {"name": "canvas_width", "description": "Output canvas width in pixels.", "default_value": "1280"},
    {"name": "canvas_height", "description": "Output canvas height in pixels.", "default_value": "960"},
    {"name": "max_width", "description": "Subject is scaled to fill up to this % of the canvas width, keeping proportions (never stretched). The tighter of max_width/max_height sets the size.", "default_value": "90"},
    {"name": "max_height", "description": "Subject is scaled to fill up to this % of the canvas height, keeping proportions (never stretched). The tighter of max_width/max_height sets the size.", "default_value": "90"},
    {"name": "h_align", "description": "Horizontal placement. Options: left, center, right.", "default_value": "center"},
    {"name": "x_offset", "description": "Nudge left/right from that placement, as % of the canvas width. Positive = right, negative = left.", "default_value": "0"},
    {"name": "v_align", "description": "Vertical placement. Options: top, center, bottom.", "default_value": "center"},
    {"name": "y_offset", "description": "Nudge up/down from that placement, as % of the canvas height. Positive = down, negative = up.", "default_value": "0"},
    {"name": "background", "description": "Fill behind the subject. Options: a hex colour like #e8e8e8, white, or transparent.", "default_value": "#e8e8e8"},
    {"name": "min_opacity", "description": "How solid a pixel must be (0-100%) to count as part of the subject; fainter see-through edge pixels are treated as background.", "default_value": "4"},
]

H_ALIGN = ("left", "center", "right")
V_ALIGN = ("top", "center", "bottom")

# Safety cap on the output canvas — guard against absurd canvas sizes exhausting memory.
MAX_OUTPUT_DIM = 8192


def resolve_background(value):
    """Map a background param to an RGBA fill tuple. Raises ValueError on a bad value."""
    s = (value or "transparent").strip().lower()
    if s == "transparent":
        return (0, 0, 0, 0)
    if s == "white":
        return (255, 255, 255, 255)
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            try:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
            except ValueError:
                pass
    raise ValueError("background must be 'transparent', 'white', or a hex colour like #e8e8e8")


def clean_number(n):
    """Drop the trailing .0 on whole numbers (60 not 60.0) for cleaner metadata."""
    return int(n) if n == int(n) else n


def subject_bbox(img_rgba, alpha_threshold):
    """Bounding box of pixels whose alpha > alpha_threshold (ignores ghost/edge pixels)."""
    alpha = img_rgba.split()[3]
    mask = alpha.point(lambda p: 255 if p > alpha_threshold else 0)
    return mask.getbbox()


def place(content, canvas_w, canvas_h, max_width, max_height,
          h_align, x_offset, v_align, y_offset, fill):
    """Scale `content` (RGBA) to fill up to max_width% / max_height% of the canvas (keeping
    proportions — never stretched), then align it on a fixed canvas (with an optional % nudge
    on each axis). The tighter bound sets the size. Returns (image, scale, bound_by)."""
    fit_w = (canvas_w * max_width / 100.0) / content.width
    fit_h = (canvas_h * max_height / 100.0) / content.height
    s = min(fit_w, fit_h)
    bound_by = "width" if fit_w <= fit_h else "height"  # the tighter bound sets the size
    scaled = content.resize((round(content.width * s), round(content.height * s)))
    sw, sh = scaled.size

    x = {"left": 0, "center": (canvas_w - sw) // 2, "right": canvas_w - sw}[h_align]
    y = {"top": 0, "center": (canvas_h - sh) // 2, "bottom": canvas_h - sh}[v_align]
    x += int(round(canvas_w * x_offset / 100.0))
    y += int(round(canvas_h * y_offset / 100.0))

    if fill[3] == 255:  # opaque fill — paste onto an RGB canvas (subject's alpha = paste mask)
        canvas = Image.new("RGB", (canvas_w, canvas_h), fill[:3])
        canvas.paste(scaled, (x, y), scaled)
        canvas = canvas.convert("RGBA")
    else:               # transparent/translucent fill — composite onto an RGBA canvas
        canvas = Image.new("RGBA", (canvas_w, canvas_h), fill)
        layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        layer.paste(scaled, (x, y), scaled)
        canvas = Image.alpha_composite(canvas, layer)

    return canvas, s, bound_by


def process(input_bytes, params):
    """Core: crop to the alpha subject + place it on the canvas. Returns (png_bytes, meta).
    Raises ValueError with a clear, user-facing message on bad input/params."""
    canvas_w = int(params.get("canvas_width") or "1280")
    canvas_h = int(params.get("canvas_height") or "960")
    if canvas_w < 1 or canvas_h < 1:
        raise ValueError("canvas_width and canvas_height must be >= 1")
    if max(canvas_w, canvas_h) > MAX_OUTPUT_DIM:
        raise ValueError(f"canvas may not exceed {MAX_OUTPUT_DIM}px on a side")

    max_width = float(params.get("max_width") or "90")
    max_height = float(params.get("max_height") or "90")
    if not (0 < max_width <= 100):
        raise ValueError("max_width must be between 0 (exclusive) and 100")
    if not (0 < max_height <= 100):
        raise ValueError("max_height must be between 0 (exclusive) and 100")

    h_align = (params.get("h_align") or "center").strip().lower()
    if h_align not in H_ALIGN:
        raise ValueError("h_align must be one of: " + ", ".join(H_ALIGN))
    v_align = (params.get("v_align") or "center").strip().lower()
    if v_align not in V_ALIGN:
        raise ValueError("v_align must be one of: " + ", ".join(V_ALIGN))

    x_offset = float(params.get("x_offset") or "0")
    y_offset = float(params.get("y_offset") or "0")
    if not (-100 <= x_offset <= 100):
        raise ValueError("x_offset must be between -100 and 100")
    if not (-100 <= y_offset <= 100):
        raise ValueError("y_offset must be between -100 and 100")

    min_opacity = float(params.get("min_opacity") or "4")
    if not (0 <= min_opacity <= 100):
        raise ValueError("min_opacity must be between 0 and 100")
    alpha_threshold = round(min_opacity / 100.0 * 255)  # % -> 0-255 for the alpha test

    fill = resolve_background(params.get("background"))

    img = Image.open(io.BytesIO(input_bytes)).convert("RGBA")
    original_size = img.size

    bbox = subject_bbox(img, alpha_threshold)
    if bbox is None:
        raise ValueError("no subject found (image is fully transparent below min_opacity)")
    content = img.crop(bbox)

    result, scale, bound_by = place(
        content, canvas_w, canvas_h, max_width, max_height,
        h_align, x_offset, v_align, y_offset, fill,
    )
    result = result.convert("RGBA")

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    meta = {
        "original_size": f"{original_size[0]}x{original_size[1]}",
        "content_size": f"{content.size[0]}x{content.size[1]}",
        "final_size": f"{result.size[0]}x{result.size[1]}",
        "bound_by": bound_by,          # which bound set the size: "width" or "height"
        "upscaled": scale > 1.0,       # true if the subject was scaled up (watch for softness)
        "max_width": clean_number(max_width),
        "max_height": clean_number(max_height),
        "h_align": h_align,
        "x_offset": clean_number(x_offset),
        "v_align": v_align,
        "y_offset": clean_number(y_offset),
        "background": (params.get("background") or "transparent").strip().lower(),
        "min_opacity": clean_number(min_opacity),
    }
    log.debug("placed %s -> %s on %dx%d canvas (bound_by=%s, upscaled=%s)",
              meta["content_size"], meta["final_size"], canvas_w, canvas_h, bound_by, scale > 1.0)
    return buf.getvalue(), meta


def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return
    try:
        png_bytes, meta = process(input_bytes, params)
    except ValueError as e:
        write_error(str(e))
        return
    except Exception as e:
        write_error(f"processing failed: {str(e)}")
        return
    write_output(png_bytes, "image/png", **meta)


def run_local_cli():
    """Run the node without the apiai.me runtime: read a file, write a file."""
    import argparse

    ap = argparse.ArgumentParser(description="Place a cut-out image on a fixed canvas, fit within a box.")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--canvas_width", default="1280")
    ap.add_argument("--canvas_height", default="960")
    ap.add_argument("--max_width", default="90")
    ap.add_argument("--max_height", default="90")
    ap.add_argument("--h_align", default="center")
    ap.add_argument("--x_offset", default="0")
    ap.add_argument("--v_align", default="center")
    ap.add_argument("--y_offset", default="0")
    ap.add_argument("--background", default="#e8e8e8")
    ap.add_argument("--min_opacity", default="4")
    a = ap.parse_args()

    with open(a.input, "rb") as f:
        data = f.read()
    params = {
        "canvas_width": a.canvas_width,
        "canvas_height": a.canvas_height,
        "max_width": a.max_width,
        "max_height": a.max_height,
        "h_align": a.h_align,
        "x_offset": a.x_offset,
        "v_align": a.v_align,
        "y_offset": a.y_offset,
        "background": a.background,
        "min_opacity": a.min_opacity,
    }
    png_bytes, meta = process(data, params)
    with open(a.output, "wb") as f:
        f.write(png_bytes)
    print("OK", meta)


if __name__ == "__main__":
    # main() is only reached when script_io imported successfully; a failed import routes to
    # the local CLI instead, so main() never calls a missing read_input/write_output.
    if SCRIPT_IO_AVAILABLE and len(sys.argv) <= 1:
        main()
    else:
        run_local_cli()
