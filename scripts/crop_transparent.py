#!/usr/bin/env python3
"""
Crop Transparent — crop a cut-out (transparent-background) image to its subject,
then frame it on a chosen aspect ratio.

Finds the subject from the ALPHA channel (ignoring faint edge pixels), crops tight
to it, then optionally pads it — centred — onto a target aspect ratio. You can either
add a fixed pixel margin, or scale the subject to a % of the output's longest side
(e.g. make it fill 75% of a square). The padding can be transparent, white, or a hex
colour.

Params:
  format          - Output aspect ratio: original, 1:1, square, 3:4, 4:3, 3:2, 2:3,
                    9:16, 16:9, 4:5. Content is centred and padded (never cropped).
  subject_scale   - Scale the subject to this % of the output's longest side (adds
                    padding around it). 0 = off. Needs a format other than original.
  margin          - Padding around the subject in pixels. Ignored when subject_scale is set.
  background      - Padding fill: transparent (default), white, or a hex colour like #ffffff.
  alpha_threshold - Min alpha (0-255) for a pixel to count as subject (ignores faint edges).

Input:  PNG with a transparent background (a cut-out subject).
Output: RGBA PNG, cropped + framed.

Note: param names + defaults match the earlier live node so existing pipelines keep working;
`subject_scale` and `background` are new optional params (off by default).
"""
import io
import sys

from PIL import Image

try:
    from script_io import read_input, write_output, write_error
    SCRIPT_IO_AVAILABLE = True
except ImportError:  # local CLI runs without the apiai.me runtime
    SCRIPT_IO_AVAILABLE = False

PARAM_DEFS = [
    {"name": "format", "description": "Output aspect ratio. Options: original, 1:1, square, 3:4, 4:3, 3:2, 2:3, 9:16, 16:9, 4:5. Subject is centred and padded (never cropped).", "default_value": "square"},
    {"name": "subject_scale", "description": "Scale the subject to this % of the output's longest side, padding around it (e.g. 75). 0 = off. Needs a format other than original.", "default_value": "0"},
    {"name": "margin", "description": "Padding around the subject in pixels. Ignored when subject_scale is set.", "default_value": "10"},
    {"name": "background", "description": "Padding fill colour. Options: transparent, white, or a hex colour like #ffffff.", "default_value": "transparent"},
    {"name": "alpha_threshold", "description": "Minimum alpha (0-255) for a pixel to count as the subject — ignores faint semi-transparent edge pixels.", "default_value": "10"},
]

# Supported output aspect ratios (width / height). Superset of the earlier node's options
# plus 3:4 (so it also covers the sibling crop node's set); "original" = no aspect change.
ASPECTS = {
    "square": 1.0, "1:1": 1.0,
    "3:4": 3 / 4, "4:3": 4 / 3,
    "3:2": 3 / 2, "2:3": 2 / 3,
    "9:16": 9 / 16, "16:9": 16 / 9,
    "4:5": 4 / 5,
}

# Safety cap on the output canvas — a very small subject_scale (e.g. 1 = subject is 1% of the
# frame) would otherwise blow the canvas up ~100x and exhaust memory. Fail clearly instead.
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
    raise ValueError("background must be 'transparent', 'white', or a hex colour like #ffffff")


def subject_bbox(img_rgba, alpha_threshold):
    """Bounding box of pixels whose alpha > alpha_threshold (ignores ghost/edge pixels)."""
    alpha = img_rgba.split()[3]
    mask = alpha.point(lambda p: 255 if p > alpha_threshold else 0)
    return mask.getbbox()


def frame(content, fmt, subject_scale, margin_px, fill):
    """Centre `content` (RGBA) on a canvas: either scaled to subject_scale% of the
    longest side, or with a fixed pixel margin, padded to `fmt`. Never crops."""
    cw, ch = content.size

    if fmt == "original":
        canvas_w, canvas_h = cw + 2 * margin_px, ch + 2 * margin_px
    else:
        aspect = ASPECTS[fmt]
        if subject_scale > 0:
            # Size the canvas so the subject's longest side is subject_scale% of the
            # canvas's longest side. No resampling — just more padding around the subject.
            canvas_long = max(cw, ch) / (subject_scale / 100.0)
            if aspect >= 1.0:  # landscape/square -> width is the longest side
                canvas_w, canvas_h = canvas_long, canvas_long / aspect
            else:              # portrait -> height is the longest side
                canvas_w, canvas_h = canvas_long * aspect, canvas_long
            canvas_w, canvas_h = int(round(canvas_w)), int(round(canvas_h))
        else:
            base_w, base_h = cw + 2 * margin_px, ch + 2 * margin_px
            if base_w / base_h > aspect:  # too wide -> grow height
                canvas_w, canvas_h = base_w, int(round(base_w / aspect))
            else:                         # too tall -> grow width
                canvas_w, canvas_h = int(round(base_h * aspect)), base_h

    # Never crop: the canvas is at least the subject's size.
    canvas_w, canvas_h = max(canvas_w, cw), max(canvas_h, ch)

    if max(canvas_w, canvas_h) > MAX_OUTPUT_DIM:
        raise ValueError(
            f"output would be {canvas_w}x{canvas_h}px, over the {MAX_OUTPUT_DIM}px limit — "
            "raise subject_scale (or lower the margin)"
        )

    canvas = Image.new("RGBA", (canvas_w, canvas_h), fill)
    canvas.paste(content, ((canvas_w - cw) // 2, (canvas_h - ch) // 2), content)
    return canvas


def process(input_bytes, params):
    """Core: crop to the alpha subject + frame it. Returns (png_bytes, meta).
    Raises ValueError with a clear, user-facing message on bad input/params."""
    fmt = (params.get("format") or "square").strip().lower()
    if fmt not in ASPECTS and fmt != "original":
        raise ValueError("format must be one of: original, " + ", ".join(ASPECTS))

    subject_scale = float(params.get("subject_scale") or "0")
    if not (0 <= subject_scale <= 100):
        raise ValueError("subject_scale must be between 0 and 100")
    if subject_scale > 0 and fmt == "original":
        raise ValueError("subject_scale needs a format other than original")

    margin_px = int(params.get("margin") or "10")  # fallback must match the PARAM_DEFS default
    if margin_px < 0:
        raise ValueError("margin must be >= 0")

    alpha_threshold = int(params.get("alpha_threshold") or "10")
    if not (0 <= alpha_threshold <= 255):
        raise ValueError("alpha_threshold must be between 0 and 255")

    fill = resolve_background(params.get("background"))

    img = Image.open(io.BytesIO(input_bytes)).convert("RGBA")
    original_size = img.size

    bbox = subject_bbox(img, alpha_threshold)
    if bbox is None:
        raise ValueError("no subject found (image is fully transparent below the alpha threshold)")
    content = img.crop(bbox)

    result = frame(content, fmt, subject_scale, margin_px, fill).convert("RGBA")

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    meta = {
        "original_size": f"{original_size[0]}x{original_size[1]}",
        "content_size": f"{content.size[0]}x{content.size[1]}",
        "final_size": f"{result.size[0]}x{result.size[1]}",
        "format": fmt,
        # Drop the trailing .0 on whole numbers (75 not 75.0) for cleaner downstream reads.
        "subject_scale": int(subject_scale) if subject_scale == int(subject_scale) else subject_scale,
        "margin": margin_px,
        "background": (params.get("background") or "transparent").strip().lower(),
        "alpha_threshold": alpha_threshold,
    }
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

    ap = argparse.ArgumentParser(description="Crop a transparent cut-out to its subject and frame it.")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--format", default="square")
    ap.add_argument("--subject_scale", default="0")
    ap.add_argument("--margin", default="10")
    ap.add_argument("--background", default="transparent")
    ap.add_argument("--alpha_threshold", default="10")
    a = ap.parse_args()

    with open(a.input, "rb") as f:
        data = f.read()
    params = {
        "format": a.format,
        "subject_scale": a.subject_scale,
        "margin": a.margin,
        "background": a.background,
        "alpha_threshold": a.alpha_threshold,
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
