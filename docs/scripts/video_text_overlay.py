#!/usr/bin/env python3
"""
Add timed text overlay to a video using ffmpeg drawtext filters.

Receives a video via script_io, burns text into the video,
and outputs the result as MP4.

The 'prompt' param supports two formats:

  1. Timestamped entries (subtitle-style):
       00:00:01 - Hi, I am the first line
       00:01:12 - And I am the second one
     Entries can be separated by newlines or semicolons (for API use):
       00:00:01 - First; 00:00:03 - Second; 00:00:06 - Third
     Each entry appears at its timestamp and disappears when the next starts.
     The last entry stays until the video ends.
     Timestamps can be HH:MM:SS, MM:SS, or bare seconds (e.g. "5").

  2. Plain text (no timestamps):
       Hello World
     Behaves like a single overlay for the full video duration.

Params:
  prompt       - Text to display, plain or timestamped lines (required)
  font         - Font style preset (default: "modern")
                 Options: modern, classic, typewriter, strong, elegant,
                          literature, neon, comic, poster, signature,
                          editor, bubble, deco, squeeze,
                          sans, sans-bold, serif, serif-bold, mono, mono-bold
  fontsize     - Font size in pixels (default: "48")
  fontcolor    - Text colour (default: "white")
  position     - Named preset (default: "bottom-center")
                 Options: bottom-center, bottom-left, bottom-right,
                          top-center, top-left, top-right,
                          center-left, center, center-right
  margin       - Distance from edge in pixels (default: "40")
  borderw      - Text outline width, 0=off (default: "2")
  bordercolor  - Outline colour (default: "black")
  shadowx      - Drop shadow X offset, 0=off (default: "0")
  shadowy      - Drop shadow Y offset, 0=off (default: "0")
  shadowcolor  - Shadow colour (default: "black@0.6")
  box          - Background box: "1" or "0" (default: "0")
  boxcolor     - Box colour with alpha (default: "black@0.5")
  boxborderw   - Padding inside box in pixels (default: "10")
  fade_in      - Fade-in seconds per entry (default: "0")
  fade_out     - Fade-out seconds per entry (default: "0")
  animation    - Effect: none, scroll-up, scroll-down, scroll-left,
                          scroll-right, typewriter (default: "none")
  scroll_speed - Pixels per second for scroll modes (default: "50")
  typewriter_speed - Seconds between words in typewriter mode (default: "0.3")
  max_width    - Auto-wrap at this character count, 0=off (default: "0")
  line_spacing - Extra spacing between lines in pixels (default: "0")
  crf          - Encoding quality, lower = better (default: "23")
  preset       - Encoding speed tradeoff (default: "medium")
"""
import sys
import subprocess
import tempfile
import os
import re
import time
import logging
from collections import deque
from script_io import read_params, input_path, output_path, finish, write_error

log = logging.getLogger("video_text_overlay")
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG,
                    format="%(name)s %(levelname)s: %(message)s")


# ── Parameter definitions (picked up by admin "Scan Script") ──
PARAM_DEFS = [
    {"name": "prompt", "description": "Text to burn onto the video. Plain text shows for the full duration. For timed entries use semicolons: 00:00:01 - Hello; 00:00:05 - World", "default_value": "", "required": True},
    {"name": "font", "description": "Font style preset", "default_value": "modern", "allowed_values": ["modern", "classic", "typewriter", "strong", "elegant", "literature", "neon", "comic", "poster", "signature", "editor", "bubble", "deco", "squeeze", "sans", "sans-bold", "serif", "serif-bold", "mono", "mono-bold"]},
    {"name": "fontsize", "description": "Font size in pixels", "default_value": "48"},
    {"name": "fontcolor", "description": "Text colour name or hex (e.g. white, red, #FF8800)", "default_value": "white"},
    {"name": "position", "description": "Where the text appears on screen", "default_value": "bottom-center", "allowed_values": ["bottom-center", "bottom-left", "bottom-right", "top-center", "top-left", "top-right", "center-left", "center", "center-right"]},
    {"name": "margin", "description": "Distance from the edge in pixels", "default_value": "40"},
    {"name": "borderw", "description": "Text outline thickness in pixels (0 = no outline)", "default_value": "2"},
    {"name": "bordercolor", "description": "Outline colour name or hex", "default_value": "black"},
    {"name": "shadowx", "description": "Drop-shadow horizontal offset in pixels (0 = no shadow)", "default_value": "0"},
    {"name": "shadowy", "description": "Drop-shadow vertical offset in pixels (0 = no shadow)", "default_value": "0"},
    {"name": "shadowcolor", "description": "Shadow colour with optional opacity (e.g. black@0.6)", "default_value": "black@0.6"},
    {"name": "box", "description": "Show a background box behind the text", "default_value": "0", "allowed_values": ["0", "1"]},
    {"name": "boxcolor", "description": "Background box colour with opacity (e.g. black@0.5)", "default_value": "black@0.5"},
    {"name": "boxborderw", "description": "Padding inside the background box in pixels", "default_value": "10"},
    {"name": "fade_in", "description": "Seconds to fade text in (0 = instant appear)", "default_value": "0"},
    {"name": "fade_out", "description": "Seconds to fade text out (0 = instant disappear)", "default_value": "0"},
    {"name": "crf", "description": "Video quality 0-51: lower = better quality but larger file", "default_value": "23"},
    {"name": "preset", "description": "Encoding speed: faster encodes quicker but larger file", "default_value": "medium", "allowed_values": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]},
    {"name": "animation", "description": "Text animation: none (static), scroll-up/down/left/right, or typewriter (word-by-word reveal)", "default_value": "none", "allowed_values": ["none", "scroll-up", "scroll-down", "scroll-left", "scroll-right", "typewriter"]},
    {"name": "scroll_speed", "description": "Scroll speed in pixels per second (scroll animations only)", "default_value": "50"},
    {"name": "typewriter_speed", "description": "Seconds between each word appearing (typewriter animation only)", "default_value": "0.3"},
    {"name": "max_width", "description": "Max characters per line for auto-wrapping (0 = no wrap)", "default_value": "0"},
    {"name": "line_spacing", "description": "Extra spacing between lines in pixels", "default_value": "0"}
]


# ── Curated font map ──
# Friendly names → fontfile paths. Bundled Google Fonts (OFL-licensed)
# live in /app/fonts/ in Docker; locally resolve via FONT_DIR env var.
_FONT_DIR = os.environ.get("FONT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts"))

# Instagram-inspired style categories
FONTS = {
    # ── Style presets (bundled Google Fonts) ──
    "modern":     os.path.join(_FONT_DIR, "Montserrat-Bold.ttf"),
    "classic":    os.path.join(_FONT_DIR, "OpenSans-Regular.ttf"),
    "typewriter": os.path.join(_FONT_DIR, "CourierPrime-Regular.ttf"),
    "strong":     os.path.join(_FONT_DIR, "Anton-Regular.ttf"),
    "elegant":    os.path.join(_FONT_DIR, "PlayfairDisplay-Bold.ttf"),
    "literature": os.path.join(_FONT_DIR, "Lora-Regular.ttf"),
    "neon":       os.path.join(_FONT_DIR, "Pacifico-Regular.ttf"),
    "comic":      os.path.join(_FONT_DIR, "ComicNeue-Regular.ttf"),
    "poster":     os.path.join(_FONT_DIR, "AbrilFatface-Regular.ttf"),
    "signature":  os.path.join(_FONT_DIR, "DancingScript-Regular.ttf"),
    "editor":     os.path.join(_FONT_DIR, "LibreBaskerville-Regular.ttf"),
    "bubble":     os.path.join(_FONT_DIR, "Baloo2-Regular.ttf"),
    "deco":       os.path.join(_FONT_DIR, "PoiretOne-Regular.ttf"),
    "squeeze":    os.path.join(_FONT_DIR, "Oswald-Bold.ttf"),
    # ── Legacy aliases (mapped to bundled equivalents) ──
    "sans":       os.path.join(_FONT_DIR, "OpenSans-Regular.ttf"),
    "sans-bold":  os.path.join(_FONT_DIR, "Montserrat-Bold.ttf"),
    "serif":      os.path.join(_FONT_DIR, "Lora-Regular.ttf"),
    "serif-bold": os.path.join(_FONT_DIR, "PlayfairDisplay-Bold.ttf"),
    "mono":       os.path.join(_FONT_DIR, "CourierPrime-Regular.ttf"),
    "mono-bold":  os.path.join(_FONT_DIR, "CourierPrime-Regular.ttf"),
}

# ── Position presets ──
# {m} replaced with margin value at runtime.
POSITIONS = {
    "top-left":      ("{m}",            "{m}"),
    "top-center":    ("(w-text_w)/2",   "{m}"),
    "top-right":     ("w-text_w-{m}",   "{m}"),
    "center-left":   ("{m}",            "(h-text_h)/2"),
    "center":        ("(w-text_w)/2",   "(h-text_h)/2"),
    "center-right":  ("w-text_w-{m}",   "(h-text_h)/2"),
    "bottom-left":   ("{m}",            "h-text_h-{m}"),
    "bottom-center": ("(w-text_w)/2",   "h-text_h-{m}"),
    "bottom-right":  ("w-text_w-{m}",   "h-text_h-{m}"),
}

# ── Validation ──
_SAFE_TEXT = re.compile(r"^[\w\s.,!?:;\-'/\"()&@#%+=$€£¥°©®™\n\r]*$", re.UNICODE)
_SAFE_COLOR = re.compile(r"^[\w@#.]+$")
_TS_LINE = re.compile(r"^\s*(\d{1,2}(?::\d{2}){0,2})\s*[-–]\s*(.+)$")


def _parse_timestamp(ts):
    parts = [float(p) for p in ts.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def _parse_timed_text(raw):
    # Split on newlines or semicolons (semicolons handy for single-line API calls)
    parts = re.split(r'[\n;]', raw.strip())
    lines = [l.strip() for l in parts if l.strip()]
    log.debug("parse_timed_text: %d parts after split: %r", len(lines), lines)
    if not lines:
        return None
    entries = []
    for line in lines:
        m = _TS_LINE.match(line)
        if not m:
            log.debug("parse_timed_text: line did NOT match timestamp pattern: %r", line)
            return None
        entries.append((_parse_timestamp(m.group(1)), m.group(2).strip()))
    entries.sort(key=lambda e: e[0])
    log.debug("parse_timed_text: parsed %d timed entries: %r", len(entries), entries)
    return entries


def _sanitise_text(text):
    if not _SAFE_TEXT.match(text):
        raise ValueError(f"text contains disallowed characters: {text!r}")
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "'\\\\\\''")
    text = text.replace("\n", "\\n")
    text = text.replace("\r", "")
    text = text.replace(":", "\\:")
    return text


def _validate_color(value, name):
    if value and not _SAFE_COLOR.match(value):
        raise ValueError(f"{name} contains disallowed characters")
    return value


def _resolve_font(name):
    key = name.strip().lower()
    if key not in FONTS:
        raise ValueError(
            f"unknown font '{name}'. Options: {', '.join(sorted(FONTS))}"
        )
    path = FONTS[key]
    if not os.path.isfile(path):
        log.warning("font file not found: %s — falling back to modern", path)
        fallback_path = FONTS.get("modern")
        if fallback_path and os.path.isfile(fallback_path):
            path = fallback_path
        else:
            raise RuntimeError("no fonts available - check FONT_DIR")
    return path


def _resolve_position(name, margin):
    key = name.strip().lower()
    if key not in POSITIONS:
        raise ValueError(
            f"unknown position '{name}'. "
            f"Options: {', '.join(sorted(POSITIONS))}"
        )
    x_tpl, y_tpl = POSITIONS[key]
    return x_tpl.replace("{m}", str(margin)), y_tpl.replace("{m}", str(margin))


def _wrap_text(text, max_width):
    """Wrap text at word boundaries to fit within max_width characters per line."""
    if max_width <= 0:
        return text
    words = text.split()
    if not words:
        return text
    lines = []
    current = []
    length = 0
    for word in words:
        added = len(word) + (1 if current else 0)
        if length + added > max_width and current:
            lines.append(' '.join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += added
    if current:
        lines.append(' '.join(current))
    return '\n'.join(lines)


def _build_drawtext(text, style, start_secs=None, end_secs=None):
    safe = _sanitise_text(text)
    font_file = style["font_file"].replace(":", "\\:")
    animation = style.get("animation", "none")
    scroll_speed = int(style.get("scroll_speed", "50"))
    s = start_secs if start_secs is not None else 0

    # Position — overridden by scroll animations
    x_expr = style['x']
    y_expr = style['y']
    if animation == 'scroll-up':
        y_expr = f"h-(t-{s})*{scroll_speed}"
    elif animation == 'scroll-down':
        y_expr = f"-text_h+(t-{s})*{scroll_speed}"
    elif animation == 'scroll-left':
        x_expr = f"w-(t-{s})*{scroll_speed}"
    elif animation == 'scroll-right':
        x_expr = f"-text_w+(t-{s})*{scroll_speed}"

    dt = (
        f"drawtext=text='{safe}'"
        f":fontfile='{font_file}'"
        f":fontsize={style['fontsize']}"
        f":fontcolor={style['fontcolor']}"
        f":x={x_expr}:y={y_expr}"
    )

    # Line spacing
    line_spacing = int(style.get("line_spacing", "0"))
    if line_spacing > 0:
        dt += f":line_spacing={line_spacing}"

    # Text outline
    if int(style["borderw"]) > 0:
        dt += f":borderw={style['borderw']}:bordercolor={style['bordercolor']}"

    # Drop shadow
    if int(style["shadowx"]) != 0 or int(style["shadowy"]) != 0:
        dt += (f":shadowx={style['shadowx']}"
               f":shadowy={style['shadowy']}"
               f":shadowcolor={style['shadowcolor']}")

    # Background box
    if style["box"] == "1":
        dt += f":box=1:boxcolor={style['boxcolor']}:boxborderw={style['boxborderw']}"

    # Time window + optional fade
    fade_in = float(style["fade_in"])
    fade_out = float(style["fade_out"])

    if fade_in > 0 or fade_out > 0:
        alpha_parts = []
        if fade_in > 0:
            alpha_parts.append(f"min(1\\,(t-{s})/{fade_in})")
        if fade_out > 0 and end_secs is not None:
            alpha_parts.append(f"min(1\\,({end_secs}-t)/{fade_out})")
        if alpha_parts:
            dt += ":alpha='" + "*".join(alpha_parts) + "'"

    # Visibility window
    conditions = []
    if start_secs is not None and start_secs > 0:
        conditions.append(f"gte(t\\,{start_secs})")
    if end_secs is not None:
        conditions.append(f"lt(t\\,{end_secs})")
    if conditions:
        dt += ":enable='" + "*".join(conditions) + "'"

    log.debug("drawtext filter: %s", dt)
    return dt


def _build_typewriter_filters(text, style, start_secs=None, end_secs=None):
    """Build word-by-word typewriter reveal as a chain of drawtext filters."""
    words = text.split()
    if not words:
        return []
    s = start_secs if start_secs is not None else 0
    speed = float(style.get("typewriter_speed", "0.3"))
    sub_style = dict(style, animation='none')  # no scroll inside typewriter

    filters = []
    for i in range(len(words)):
        partial = ' '.join(words[:i + 1])
        w_start = s + i * speed
        w_end = s + (i + 1) * speed if i < len(words) - 1 else end_secs
        filters.append(_build_drawtext(partial, sub_style,
                                       start_secs=w_start, end_secs=w_end))
    return filters


def _probe_duration(path):
    """Return video duration in seconds via ffprobe, or None on failure."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            dur = float(r.stdout.strip())
            log.debug("probed video duration: %.2f s", dur)
            return dur
    except Exception as e:
        log.debug("ffprobe failed: %s", e)
    return None


def _run_ffmpeg(cmd, timeout):
    """Run ffmpeg, streaming its stderr to the log as it is produced.

    capture_output holds every line until the process returns, so a job killed
    alongside its container — an OOM, say — leaves no account of itself at the
    one moment it mattered. The tail is kept so the caller still gets a useful
    error message.
    """
    tail = deque(maxlen=40)
    deadline = time.monotonic() + timeout
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    for line in proc.stderr:
        line = line.rstrip()
        if line:
            tail.append(line)
            log.info("ffmpeg: %s", line)
        if time.monotonic() > deadline:
            proc.kill()
            raise RuntimeError(f"ffmpeg exceeded {timeout}s")
    proc.wait()
    return proc.returncode, "\n".join(tail)


def add_text_overlay(in_path, out_path, params):
    log.debug("params keys: %s", list(params.keys()))
    raw_text = params.get("prompt", "")
    log.debug("raw prompt (%d chars): %r", len(raw_text), raw_text[:200])
    if not raw_text:
        raise ValueError("'prompt' parameter is required")

    font_file = _resolve_font(params.get("font", "modern"))
    margin = params.get("margin", "40")
    x, y = _resolve_position(params.get("position", "bottom-center"), margin)

    style = {
        "font_file": font_file,
        "fontsize":    params.get("fontsize", "48"),
        "fontcolor":   _validate_color(params.get("fontcolor", "white"), "fontcolor"),
        "x": x, "y": y,
        "borderw":     params.get("borderw", "2"),
        "bordercolor": _validate_color(params.get("bordercolor", "black"), "bordercolor"),
        "shadowx":     params.get("shadowx", "0"),
        "shadowy":     params.get("shadowy", "0"),
        "shadowcolor": _validate_color(params.get("shadowcolor", "black@0.6"), "shadowcolor"),
        "box":         params.get("box", "0"),
        "boxcolor":    _validate_color(params.get("boxcolor", "black@0.5"), "boxcolor"),
        "boxborderw":  params.get("boxborderw", "10"),
        "fade_in":     params.get("fade_in", "0"),
        "fade_out":    params.get("fade_out", "0"),
        "animation":   params.get("animation", "none"),
        "scroll_speed": params.get("scroll_speed", "50"),
        "typewriter_speed": params.get("typewriter_speed", "0.3"),
        "line_spacing": params.get("line_spacing", "0"),
    }

    max_width = int(params.get("max_width", "0"))
    animation = style["animation"]
    crf = params.get("crf", "23")
    preset = params.get("preset", "medium")

    entries = _parse_timed_text(raw_text)

    duration = _probe_duration(in_path)

    if entries and duration is not None:
        # Clamp timestamps that exceed video duration
        clamped = []
        for start, text in entries:
            if start >= duration:
                log.warning(
                    "timestamp %.1fs >= video duration %.1fs, "
                    "clamping to 0s: %r", start, duration, text,
                )
                start = 0.0
            clamped.append((start, text))
        clamped.sort(key=lambda e: e[0])
        entries = clamped

    if entries:
        log.debug("using TIMED mode with %d entries", len(entries))
        filters = []
        for i, (start, text) in enumerate(entries):
            end = entries[i + 1][0] if i + 1 < len(entries) else None
            wrapped = _wrap_text(text, max_width)
            log.debug("  entry %d: start=%.1f end=%s text=%r", i, start, end, wrapped)
            if animation == 'typewriter':
                filters.extend(_build_typewriter_filters(
                    wrapped, style, start_secs=start, end_secs=end))
            else:
                filters.append(_build_drawtext(wrapped, style,
                                               start_secs=start, end_secs=end))
        vf = ",".join(filters)
    else:
        log.debug("using PLAIN mode")
        wrapped = _wrap_text(raw_text.strip(), max_width)
        if animation == 'typewriter':
            tw = _build_typewriter_filters(wrapped, style)
            vf = ",".join(tw) if tw else _build_drawtext(wrapped, style)
        else:
            vf = _build_drawtext(wrapped, style)

    log.debug("full -vf filter: %s", vf)

    cmd = [
        "ffmpeg", "-y",
        "-nostats",              # progress churn would drown the log
        "-i", in_path,
        "-vf", vf,
        # ffmpeg sizes its thread pool from the HOST's cpu count, not the
        # container's quota, and x264 holds frame buffers plus a lookahead
        # queue per thread. Unbounded, a ~2 MP encode allocates past
        # ffmpeg-svc's 512 MB within seconds and the kernel kills it — which
        # reaches the caller as a closed connection with no status at all.
        "-threads", "2",
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-x264-params", "rc-lookahead=10:sync-lookahead=0",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        # The runner's output file has no .mp4 suffix, so the muxer cannot be
        # inferred from the name.
        "-f", "mp4",
        out_path,
    ]

    log.info("running ffmpeg: %s", " ".join(cmd))

    returncode, stderr_tail = _run_ffmpeg(cmd, timeout=600)
    if returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr_tail[-500:]}")

    log.info("output: %.1f MB", os.path.getsize(out_path) / (1024 * 1024))


def main():
    # Path API rather than read_input(): the runner hands us the video as a
    # file and expects the result as a file. Loading both in between costs two
    # full copies of the media in a process that only shells out to ffmpeg.
    content_type, params = read_params()

    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = input_path(tmpdir)    # the runner's file; nothing is copied
        out_path = output_path(tmpdir)  # ffmpeg writes the result in place

        if not os.path.exists(in_path) or os.path.getsize(in_path) == 0:
            write_error("no input video provided")
            return

        in_size = os.path.getsize(in_path)
        log.info("input: %.1f MB, content_type: %s", in_size / (1024 * 1024), content_type)

        try:
            add_text_overlay(in_path, out_path, params)
        except Exception as e:
            write_error(str(e))
            return

        finish(
            out_path, "video/mp4",
            input_size=in_size,
            output_size=os.path.getsize(out_path),
        )


if __name__ == "__main__":
    main()
