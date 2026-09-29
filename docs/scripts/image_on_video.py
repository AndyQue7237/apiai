#!/usr/bin/env python3
"""
Overlay an image (logo, watermark, sticker) onto a video using ffmpeg.

Input: video file (binary)
The overlay image is provided as base64 in the 'overlay_image' parameter.

Params:
  overlay_image - Base64-encoded PNG/JPEG image to overlay (required)
  position      - Where to place the overlay (default: "bottom-right")
                  Options: bottom-center, bottom-left, bottom-right,
                           top-center, top-left, top-right,
                           center-left, center, center-right
  margin        - Distance from edge in pixels (default: "20")
  scale         - Overlay size: 0.01-1.0 = fraction of video width,
                  >1 = pixel width (default: "0.15")
  opacity       - Overlay transparency 0.0-1.0 (default: "1.0")
  start_time    - When to show, seconds or HH:MM:SS (default: "0")
  end_time      - When to hide, 0 = until end (default: "0")
  fade_in       - Fade-in duration in seconds (default: "0")
  fade_out      - Fade-out duration in seconds (default: "0")
  rotation      - Rotate overlay in degrees (default: "0")
  entrance      - Slide-in animation with ease-in-out (default: "none")
                  Options: none, slide-left-0.5, slide-left-1, slide-left-1.5,
                           slide-right-0.5, slide-right-1, slide-right-1.5,
                           slide-top-0.5, slide-top-1, slide-top-1.5,
                           slide-bottom-0.5, slide-bottom-1, slide-bottom-1.5
  exit          - Slide-out animation with ease-in-out (default: "none")
                  Same options as entrance
  crf           - Encoding quality, lower = better (default: "23")
  preset        - Encoding speed tradeoff (default: "medium")
"""
import sys
import json
import base64
import subprocess
import tempfile
import os
import re
import time
import logging
from collections import deque
from script_io import read_params, input_path, output_path, finish, write_error

log = logging.getLogger("video_image_overlay")
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG,
                    format="%(name)s %(levelname)s: %(message)s")


# ── Parameter definitions (picked up by admin "Scan Script") ──
PARAM_DEFS = json.loads(r"""
[
  {"name": "overlay_image", "description": "PNG or JPEG image to overlay onto the video (logo, watermark, sticker)", "default_value": "", "required": true, "is_image": true},
  {"name": "position", "description": "Where to place the overlay on screen", "default_value": "bottom-right", "allowed_values": ["bottom-center", "bottom-left", "bottom-right", "top-center", "top-left", "top-right", "center-left", "center", "center-right"]},
  {"name": "margin", "description": "Distance from the edge in pixels", "default_value": "20"},
  {"name": "scale", "description": "Overlay size: 0.01-1.0 = fraction of video width (e.g. 0.15 = 15%), values above 1 = pixel width (e.g. 200 = 200px wide)", "default_value": "0.15"},
  {"name": "opacity", "description": "Overlay transparency from 0.0 (invisible) to 1.0 (fully opaque)", "default_value": "1.0"},
  {"name": "start_time", "description": "When the overlay appears, in seconds or HH:MM:SS (0 = from start)", "default_value": "0"},
  {"name": "end_time", "description": "When the overlay disappears, in seconds or HH:MM:SS (0 = until end)", "default_value": "0"},
  {"name": "fade_in", "description": "Seconds to fade the overlay in (0 = instant appear)", "default_value": "0"},
  {"name": "fade_out", "description": "Seconds to fade the overlay out (0 = instant disappear)", "default_value": "0"},
  {"name": "rotation", "description": "Rotate the overlay image in degrees (0 = no rotation)", "default_value": "0"},
  {"name": "entrance", "description": "Slide-in animation with ease-in-out: direction and speed in seconds", "default_value": "none", "allowed_values": ["none", "slide-left-0.5", "slide-left-1", "slide-left-1.5", "slide-right-0.5", "slide-right-1", "slide-right-1.5", "slide-top-0.5", "slide-top-1", "slide-top-1.5", "slide-bottom-0.5", "slide-bottom-1", "slide-bottom-1.5"]},
  {"name": "exit", "description": "Slide-out animation with ease-in-out: direction and speed in seconds", "default_value": "none", "allowed_values": ["none", "slide-left-0.5", "slide-left-1", "slide-left-1.5", "slide-right-0.5", "slide-right-1", "slide-right-1.5", "slide-top-0.5", "slide-top-1", "slide-top-1.5", "slide-bottom-0.5", "slide-bottom-1", "slide-bottom-1.5"]},
  {"name": "crf", "description": "Video quality 0-51: lower = better quality but larger file", "default_value": "23"},
  {"name": "preset", "description": "Encoding speed: faster encodes quicker but larger file", "default_value": "medium", "allowed_values": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]}
]
""")


# ── Position presets ──
# Uses ffmpeg overlay filter variables: W/H = main video, w/h = overlay
# {m} replaced with margin value at runtime.
POSITIONS = {
    "top-left":      ("{m}",          "{m}"),
    "top-center":    ("(W-w)/2",      "{m}"),
    "top-right":     ("W-w-{m}",      "{m}"),
    "center-left":   ("{m}",          "(H-h)/2"),
    "center":        ("(W-w)/2",      "(H-h)/2"),
    "center-right":  ("W-w-{m}",      "(H-h)/2"),
    "bottom-left":   ("{m}",          "H-h-{m}"),
    "bottom-center": ("(W-w)/2",      "H-h-{m}"),
    "bottom-right":  ("W-w-{m}",      "H-h-{m}"),
}

_SAFE_COLOR = re.compile(r"^[\w@#.]+$")


def _parse_timestamp(ts):
    """Parse HH:MM:SS, MM:SS, or bare seconds into float seconds."""
    ts = ts.strip()
    parts = [float(p) for p in ts.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def _probe_video(path):
    """Return (width, height, duration) via ffprobe."""
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
            log.debug("probed video: %dx%d, %.2fs", w, h, dur)
            return w, h, dur
    except Exception as e:
        log.debug("ffprobe failed: %s", e)
    return None, None, None


def _decode_overlay(b64_string, tmpdir):
    """Decode base64 image and write to temp file. Returns path."""
    # Strip optional data URI prefix
    if "," in b64_string[:100]:
        b64_string = b64_string.split(",", 1)[1]
    data = base64.b64decode(b64_string)
    # Detect format from magic bytes
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        ext = "png"
    elif data[:2] == b'\xff\xd8':
        ext = "jpg"
    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        ext = "webp"
    else:
        ext = "png"  # default
    path = os.path.join(tmpdir, f"overlay.{ext}")
    with open(path, "wb") as f:
        f.write(data)
    log.debug("overlay image: %d bytes, format=%s", len(data), ext)
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


# ── Slide animation helpers ──
_SLIDE_OFF = {
    "left":   ("x", "-w"),
    "right":  ("x", "W"),
    "top":    ("y", "-h"),
    "bottom": ("y", "H"),
}


def _parse_slide(val):
    """Parse 'slide-left-0.5' → ('left', 0.5) or (None, 0)."""
    if not val or val == "none":
        return None, 0.0
    parts = val.split("-")  # ["slide", "left", "0.5"]
    return parts[1], float(parts[2])


def _ease_expr(s, d):
    """Smoothstep (ease-in-out) ffmpeg expression: 0→1 over [s, s+d]."""
    e = round(s + d, 4)
    p = f"(t-{s})/{d}"
    return f"if(lt(t,{s}),0,if(gt(t,{e}),1,{p}*{p}*(3-2*{p})))"


def _slide_axis_expr(target, ent_off, ent_s, ent_d, ext_off, ext_s, ext_d):
    """Build expression for one axis with optional slide entrance/exit."""
    has_ent = ent_off is not None
    has_ext = ext_off is not None

    if not has_ent and not has_ext:
        return target

    if has_ent and not has_ext:
        e = _ease_expr(ent_s, ent_d)
        return f"({ent_off})+({target}-({ent_off}))*({e})"

    if not has_ent and has_ext:
        e = _ease_expr(ext_s, ext_d)
        return f"({target})+({ext_off}-({target}))*({e})"

    # Both entrance and exit on same axis
    ent_end = round(ent_s + ent_d, 4)
    ee = _ease_expr(ent_s, ent_d)
    xe = _ease_expr(ext_s, ext_d)
    ent_part = f"({ent_off})+({target}-({ent_off}))*({ee})"
    ext_part = f"({target})+({ext_off}-({target}))*({xe})"
    return f"if(lt(t,{ent_end}),{ent_part},if(gte(t,{ext_s}),{ext_part},{target}))"


def _run_ffmpeg(cmd, timeout):
    """Run ffmpeg, streaming its stderr to the log as it is produced.

    capture_output holds every line until the process returns, so a job killed
    alongside its container — an OOM, say — leaves no account of itself at the
    one moment it mattered. Streaming puts the lines in the container log as
    they happen; the tail is kept purely so the caller still gets a useful
    error message.

    The deadline is checked per line, which is enough because ffmpeg is
    talkative. An ffmpeg that hangs saying nothing is caught by the outer
    timeout ffmpeg-svc puts on this whole script.
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


def add_image_overlay(in_path, out_path, tmpdir, params):
    log.debug("params keys: %s", list(params.keys()))

    overlay_b64 = params.get("overlay_image", "")
    if not overlay_b64:
        raise ValueError("'overlay_image' parameter is required")

    position = params.get("position", "bottom-right")
    margin = int(params.get("margin", "20"))
    scale = float(params.get("scale", "0.15"))
    opacity = float(params.get("opacity", "1.0"))
    start_time = _parse_timestamp(params.get("start_time", "0"))
    end_time = _parse_timestamp(params.get("end_time", "0"))
    fade_in = float(params.get("fade_in", "0"))
    fade_out = float(params.get("fade_out", "0"))
    rotation = float(params.get("rotation", "0"))
    crf = params.get("crf", "23")
    preset = params.get("preset", "medium")
    entrance = params.get("entrance", "none")
    exit_anim = params.get("exit", "none")

    # Clamp values
    opacity = max(0.0, min(1.0, opacity))

    x_expr, y_expr = _resolve_position(position, margin)

    overlay_path = _decode_overlay(overlay_b64, tmpdir)

    vid_w, vid_h, duration = _probe_video(in_path)

    # Calculate pixel width for scaling
    if scale <= 1.0 and vid_w:
        scale_w = int(vid_w * scale)
    elif scale > 1.0:
        scale_w = int(scale)
    else:
        scale_w = 200  # fallback

    # Ensure even dimensions (required by many codecs)
    scale_w = max(2, scale_w - (scale_w % 2))

    log.debug("overlay scale: %.3f → %dpx wide", scale, scale_w)

    # Build filter_complex
    # Step 1: scale the overlay, keep aspect ratio
    ovr_filter = f"[1:v]scale={scale_w}:-1"

    # Step 2: ensure RGBA for transparency
    ovr_filter += ",format=rgba"

    # Step 3: rotation
    if rotation != 0:
        # rotate filter uses radians
        import math
        rad = rotation * math.pi / 180
        ovr_filter += f",rotate={rad}:c=none:ow=rotw({rad}):oh=roth({rad})"

    # Step 4: opacity via colorchannelmixer
    if opacity < 1.0:
        ovr_filter += f",colorchannelmixer=aa={opacity}"

    # Step 5: fade in/out on the overlay alpha channel
    if fade_in > 0:
        st = start_time
        ovr_filter += f",fade=t=in:st={st}:d={fade_in}:alpha=1"
    if fade_out > 0 and duration and end_time > 0:
        fade_start = end_time - fade_out
        ovr_filter += f",fade=t=out:st={fade_start}:d={fade_out}:alpha=1"
    elif fade_out > 0 and duration:
        fade_start = duration - fade_out
        ovr_filter += f",fade=t=out:st={fade_start}:d={fade_out}:alpha=1"

    ovr_filter += "[ovr]"

    # Step 6: overlay composite with position and slide/timing
    ent_dir, ent_dur = _parse_slide(entrance)
    ext_dir, ext_dur = _parse_slide(exit_anim)
    has_slides = ent_dir is not None or ext_dir is not None

    if has_slides:
        ext_start = 0.0
        if ext_dir:
            if end_time > 0:
                ext_start = end_time - ext_dur
            elif duration:
                ext_start = duration - ext_dur

        ent_axis = ent_off = None
        if ent_dir:
            ent_axis, ent_off = _SLIDE_OFF[ent_dir]
        ext_axis = ext_off = None
        if ext_dir:
            ext_axis, ext_off = _SLIDE_OFF[ext_dir]

        x_final = _slide_axis_expr(
            x_expr,
            ent_off if ent_axis == "x" else None, start_time, ent_dur,
            ext_off if ext_axis == "x" else None, ext_start, ext_dur,
        )
        y_final = _slide_axis_expr(
            y_expr,
            ent_off if ent_axis == "y" else None, start_time, ent_dur,
            ext_off if ext_axis == "y" else None, ext_start, ext_dur,
        )
        overlay_expr = f"[0:v][ovr]overlay=x='{x_final}':y='{y_final}'"
    else:
        overlay_expr = f"[0:v][ovr]overlay={x_expr}:{y_expr}"

    # Enable window (timing)
    if start_time > 0 or end_time > 0:
        if end_time > 0:
            overlay_expr += f":enable='between(t,{start_time},{end_time})'"
        else:
            overlay_expr += f":enable='gte(t,{start_time})'"

    filter_complex = f"{ovr_filter};{overlay_expr}"
    log.debug("filter_complex: %s", filter_complex)

    cmd = [
        "ffmpeg", "-y",
        "-nostats",              # progress churn would drown the log
        "-i", in_path,
        "-i", overlay_path,
        "-filter_complex", filter_complex,
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

    returncode, stderr_tail = _run_ffmpeg(cmd, timeout=300)
    if returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr_tail[-500:]}")

    log.info("output: %.1f MB", os.path.getsize(out_path) / (1024 * 1024))


def main():
    # Path API rather than read_input(): the runner hands us the video as a
    # file and expects the result as a file. Loading both in between costs two
    # full copies of the media in a process that only shells out to ffmpeg.
    content_type, params = read_params()

    log.debug("received params: %s", json.dumps(
        {k: (v[:50] + "..." if isinstance(v, str) and len(v) > 50 else v)
         for k, v in params.items()}, indent=None))

    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = input_path(tmpdir)    # the runner's file; nothing is copied
        out_path = output_path(tmpdir)  # ffmpeg writes the result in place

        if not os.path.exists(in_path) or os.path.getsize(in_path) == 0:
            write_error("no input video provided")
            return

        in_size = os.path.getsize(in_path)
        log.info("input: %.1f MB, content_type: %s", in_size / (1024 * 1024), content_type)

        try:
            add_image_overlay(in_path, out_path, tmpdir, params)
        except Exception as e:
            write_error(str(e))
            return

        # input_size previously reported the length of the OUTPUT — both keys
        # carried the same number, so the metadata could never show what the
        # step actually did to the file.
        finish(
            out_path, "video/mp4",
            input_size=in_size,
            output_size=os.path.getsize(out_path),
        )


if __name__ == "__main__":
    main()
