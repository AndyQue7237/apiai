#!/usr/bin/env python3
"""
Place a stylised advertising badge / text overlay on a video.

Same badge styles as advertising_badge.py, applied as a static overlay
on every frame via ffmpeg.

Input : video file (binary via SCRIPT_INPUT_FILE)
Output: composited video (MP4)

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
  start_time    - When to show badge, in seconds (default: "0")
  end_time      - When to hide badge, in seconds; 0 = until end (default: "0")
  fade_in       - Fade-in duration in seconds (default: "0")
  fade_out      - Fade-out duration in seconds (default: "0")
  crf           - Encoding quality, lower = better quality (default: "23")
  preset        - Encoding speed tradeoff (default: "medium")
"""

import sys
import io
import math
import json
import logging
import os
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from script_io import read_params, input_path, output_path, finish, write_error

log = logging.getLogger("advertising_badge_video")
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
        "description": "Where to place the badge on the video",
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
        "description": "Headline font size in pixels, or auto to scale with video",
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
    {
        "name": "start_time",
        "description": "When to show the badge, in seconds from start (0 = always visible)",
        "default_value": "0",
    },
    {
        "name": "end_time",
        "description": "When to hide the badge, in seconds (0 = visible until end)",
        "default_value": "0",
    },
    {
        "name": "fade_in",
        "description": "Seconds to fade the badge in (0 = instant appear)",
        "default_value": "0",
    },
    {
        "name": "fade_out",
        "description": "Seconds to fade the badge out (0 = instant disappear)",
        "default_value": "0",
    },
    {
        "name": "crf",
        "description": "Video quality 0-51: lower = better quality but larger file",
        "default_value": "23",
    },
    {
        "name": "preset",
        "description": "Encoding speed tradeoff: faster = quicker encode but larger file",
        "default_value": "medium",
        "allowed_values": ["ultrafast", "superfast", "veryfast", "faster", "fast",
                           "medium", "slow", "slower", "veryslow"],
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
FONT_DIRS = [
    os.path.join(os.path.dirname(__file__), "..", "fonts"),
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
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ── Helpers ────────────────────────────────────────────────────────────────────

def text_size(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font, anchor="lt")
    return bb[2], bb[3]


def add_shadow(layer, blur=6, offset=(3, 3), shadow_color=(0, 0, 0, 120)):
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
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
    pad_x, pad_y = 20 + text_padding, 12 + text_padding
    font_h = load_font(font_size, bold=True)
    font_s = load_font(max(10, font_size - 6), bold=False)
    tmp = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(tmp)
    hw, hh = text_size(d, headline, font_h)
    sw, sh = (text_size(d, subline, font_s) if subline else (0, 0))
    width  = max(hw, sw) + pad_x * 2
    height = hh + (sh + 6 if subline else 0) + pad_y * 2
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([0, 0, width, height // 2], fill=scheme["bg"] + (255,))
    d.rectangle([0, height // 2, width, height], fill=scheme["bg2"] + (255,))
    d.rectangle([0, 0, width, 4], fill=scheme["accent"] + (220,))
    ty = pad_y
    d.text(((width - hw) // 2, ty), headline, font=font_h, fill=scheme["text"] + (255,), anchor="lt")
    if subline:
        ty += hh + 6
        d.text(((width - sw) // 2, ty), subline, font=font_s, fill=scheme["accent"] + (220,), anchor="lt")
    return layer


def render_badge(headline, subline, scheme, font_size, bg_w, text_padding=0):
    font_h = load_font(font_size, bold=True)
    font_s = load_font(max(10, font_size - 8), bold=False)
    tmp = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(tmp)
    hw, hh = text_size(d, headline, font_h)
    sw, sh = (text_size(d, subline, font_s) if subline else (0, 0))
    pad = font_size + text_padding
    inner_w = max(hw, sw)
    inner_h = hh + (sh + 8 if subline else 0)
    size = max(inner_w, inner_h) + pad * 2
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([0, 0, size - 1, size - 1], fill=scheme["bg"] + (255,))
    ring = 4
    d.ellipse([ring, ring, size - 1 - ring, size - 1 - ring], fill=scheme["bg2"] + (255,))
    d.ellipse([ring + 6, ring + 6, size - 1 - ring - 6, size - 1 - ring - 6],
              outline=scheme["accent"] + (180,), width=2)
    cy = (size - inner_h) // 2
    d.text(((size - hw) // 2, cy), headline, font=font_h, fill=scheme["text"] + (255,), anchor="lt")
    if subline:
        d.text(((size - sw) // 2, cy + hh + 8), subline, font=font_s,
               fill=scheme["accent"] + (220,), anchor="lt")
    return layer


def render_sticker(headline, subline, scheme, font_size, bg_w, text_padding=0):
    font_h = load_font(font_size, bold=True)
    font_s = load_font(max(10, font_size - 6), bold=False)
    tmp = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(tmp)
    hw, hh = text_size(d, headline, font_h)
    sw, sh = (text_size(d, subline, font_s) if subline else (0, 0))
    pad_x, pad_y = 24 + text_padding, 16 + text_padding
    w = max(hw, sw) + pad_x * 2
    h = hh + (sh + 8 if subline else 0) + pad_y * 2
    r = 18
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
    font_h = load_font(font_size, bold=True)
    font_s = load_font(max(10, font_size - 6), bold=False)
    tmp = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(tmp)
    hw, hh = text_size(d, headline, font_h)
    sw, sh = (text_size(d, subline, font_s) if subline else (0, 0))
    pad_x, pad_y = 30 + text_padding, 14 + text_padding
    w = max(hw, sw) + pad_x * 2
    h = hh + (sh + 8 if subline else 0) + pad_y * 2
    r = h // 2
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
    font_h = load_font(font_size, bold=True)
    font_s = load_font(max(10, font_size - 6), bold=False)
    tmp = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(tmp)
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
    font_h = load_font(font_size, bold=True)
    font_s = load_font(max(10, font_size - 6), bold=False)
    tmp = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(tmp)
    hw, hh = text_size(d, headline, font_h)
    sw, sh = (text_size(d, subline, font_s) if subline else (0, 0))
    pad_x, pad_y = 22 + text_padding, 14 + text_padding
    hole = 14
    w = max(hw, sw) + pad_x * 2
    h = hh + (sh + 8 if subline else 0) + pad_y * 2 + hole
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    body_h = h - hole // 2
    d.rounded_rectangle([0, hole // 2, w - 1, body_h], radius=10, fill=scheme["bg"] + (255,))
    hx = (w - hole) // 2
    d.ellipse([hx, 0, hx + hole, hole], fill=(0, 0, 0, 0))
    d.ellipse([hx + 2, 2, hx + hole - 2, hole - 2], outline=scheme["accent"] + (200,), width=2)
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

# ── ffmpeg position expressions ────────────────────────────────────────────────
# W/H = video dimensions, w/h = overlay dimensions, {m} = margin
POSITIONS = {
    "top-left":       ("{m}",        "{m}"),
    "top-center":     ("(W-w)/2",    "{m}"),
    "top-right":      ("W-w-{m}",    "{m}"),
    "center-left":    ("{m}",        "(H-h)/2"),
    "center-center":  ("(W-w)/2",    "(H-h)/2"),
    "center-right":   ("W-w-{m}",    "(H-h)/2"),
    "bottom-left":    ("{m}",        "H-h-{m}"),
    "bottom-center":  ("(W-w)/2",    "H-h-{m}"),
    "bottom-right":   ("W-w-{m}",    "H-h-{m}"),
}


def _probe_video(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            info = json.loads(r.stdout)
            stream = info.get("streams", [{}])[0]
            fmt = info.get("format", {})
            w = int(stream.get("width", 0))
            h = int(stream.get("height", 0))
            dur = float(fmt.get("duration", 0))
            return w, h, dur
    except Exception as e:
        log.debug("ffprobe failed: %s", e)
    return None, None, None


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # Path API rather than read_input(): the video is already a file on disk and
    # the result is expected as a file on disk. Loading it in between costs two
    # full copies of the media in this process — which is what pushed a 512 MB
    # container over the edge on a script that never touches a single frame.
    content_type, params = read_params()

    headline = params.get("headline", "").strip()
    if not headline:
        write_error("headline parameter is required")
        return

    subline      = params.get("subline", "").strip()
    style        = params.get("style", "ribbon").strip().lower()
    position     = params.get("position", "bottom-left").strip().lower()
    color_scheme = params.get("color_scheme", "coral").strip().lower()
    margin       = int(params.get("margin", "30"))
    text_padding = int(params.get("text_padding", "10"))
    opacity      = max(0.0, min(1.0, float(params.get("opacity", "1.0"))))
    rotation     = float(params.get("rotation", "0"))
    start_time   = float(params.get("start_time", "0"))
    end_time     = float(params.get("end_time", "0"))
    fade_in      = float(params.get("fade_in", "0"))
    fade_out     = float(params.get("fade_out", "0"))
    crf          = params.get("crf", "23")
    preset       = params.get("preset", "medium")

    if style not in RENDERERS:
        style = "ribbon"
    if color_scheme not in SCHEMES:
        color_scheme = "coral"

    scheme   = SCHEMES[color_scheme]
    renderer = RENDERERS[style]
    pos_key  = position if position in POSITIONS else "bottom-left"

    with tempfile.TemporaryDirectory() as tmpdir:
        in_path      = input_path(tmpdir)   # the runner's file; nothing is copied
        badge_path   = os.path.join(tmpdir, "badge.png")
        out_path     = output_path(tmpdir)  # ffmpeg writes the result in place

        if not os.path.exists(in_path) or os.path.getsize(in_path) == 0:
            write_error("No input video provided")
            return

        vid_w, vid_h, duration = _probe_video(in_path)
        log.info("input: %sx%s %.1fs, %.1f MB", vid_w, vid_h, duration or 0,
                 os.path.getsize(in_path) / (1024 * 1024))

        # Auto font size based on video dimensions
        raw_fs = params.get("font_size", "auto").strip().lower()
        if raw_fs == "auto":
            ref = min(vid_w, vid_h) if vid_w else 720
            font_size = max(24, min(int(ref * 0.10), 200))
        else:
            font_size = max(10, int(raw_fs))

        # For banner style we need the video width; use vid_w or a safe fallback
        bg_w_for_banner = vid_w if vid_w else 1280

        # Render badge layer
        overlay = renderer(headline, subline, scheme, font_size,
                           bg_w_for_banner, text_padding)

        # Rotate if requested
        if rotation != 0:
            overlay = overlay.rotate(-rotation, expand=True, resample=Image.BICUBIC)

        # Apply opacity baked into the PNG alpha channel
        if opacity < 1.0:
            r_ch, g_ch, b_ch, a_ch = overlay.split()
            a_ch = a_ch.point(lambda v: int(v * opacity))
            overlay = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))

        # Add drop shadow
        overlay = add_shadow(overlay, blur=8, offset=(4, 4))

        # Save badge as PNG
        overlay.save(badge_path, format="PNG")

        # ── Build ffmpeg filter_complex ────────────────────────────────────────
        x_tpl, y_tpl = POSITIONS[pos_key]
        x_expr = x_tpl.replace("{m}", str(margin))
        y_expr = y_tpl.replace("{m}", str(margin))

        # For banner: x is always 0, ignore margin
        if style == "banner":
            x_expr = "0"

        ovr_parts = ["[1:v]format=rgba"]

        # Fade in/out on alpha
        if fade_in > 0:
            ovr_parts.append(f"fade=t=in:st={start_time}:d={fade_in}:alpha=1")
        if fade_out > 0:
            if duration and end_time > 0:
                fade_start = end_time - fade_out
            elif duration:
                fade_start = duration - fade_out
            else:
                fade_start = 0
            fade_start = max(0.0, fade_start)
            ovr_parts.append(f"fade=t=out:st={fade_start}:d={fade_out}:alpha=1")

        filter_complex = ",".join(ovr_parts) + "[ovr];"
        overlay_expr = f"[0:v][ovr]overlay={x_expr}:{y_expr}"

        if start_time > 0 or end_time > 0:
            if end_time > 0:
                overlay_expr += f":enable='between(t,{start_time},{end_time})'"
            else:
                overlay_expr += f":enable='gte(t,{start_time})'"

        filter_complex += overlay_expr

        # If fading, the badge PNG must be a real stream with a timeline, not a
        # single still frame. -loop 1 alone makes an INFINITE source with no
        # framerate: it generates frames as fast as the CPU allows while the
        # h264 decode plods along, and overlay queues the excess until the
        # container dies. -shortest stops the muxer, not the filter graph.
        # Pinning the framerate and capping the duration bounds the source, so
        # it ends with the video instead of racing ahead of it.
        needs_loop = fade_in > 0 or fade_out > 0
        if needs_loop:
            badge_input = ["-loop", "1", "-framerate", "30"]
            if duration and duration > 0:
                badge_input += ["-t", str(duration)]
            badge_input += ["-i", badge_path]
        else:
            badge_input = ["-i", badge_path]

        cmd = [
            "ffmpeg", "-y",
            "-i", in_path,
            *badge_input,
            "-filter_complex", filter_complex,
            # ffmpeg sizes its thread pool from the HOST's cpu count, not the
            # container's quota, and x264 holds frame buffers plus a lookahead
            # queue per thread. On a small instance that is hundreds of MB for
            # a 1080p encode, allocated within seconds of the encode starting
            # and entirely independent of how big the input file is.
            "-threads", "2",
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            # Lookahead is the other per-thread buffer worth capping.
            "-x264-params", "rc-lookahead=10:sync-lookahead=0",
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            # The runner's output file has no .mp4 suffix, so the muxer cannot
            # be inferred from the name and has to be stated.
            "-f", "mp4",
        ]
        if needs_loop:
            cmd.append("-shortest")
        cmd.append(out_path)

        log.info("running ffmpeg: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            log.error("ffmpeg stderr: %s", result.stderr[-2000:])
            write_error(f"ffmpeg failed: {result.stderr[-500:]}")
            return

        finish(out_path, "video/mp4")


if __name__ == "__main__":
    main()
