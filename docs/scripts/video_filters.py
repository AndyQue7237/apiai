#!/usr/bin/env python3
"""
Apply an Instagram-style filter preset to a video.

Receives an input video via SCRIPT_INPUT_FILE (file-mode I/O — no base64
overhead), applies an ffmpeg filter chain, and writes the result to
SCRIPT_OUTPUT_FILE as MP4.

Params:
  preset    - Filter look. One of:
                bw          (clean black & white)
                noir        (high-contrast B&W, deep blacks)
                sepia       (classic warm brown tone)
                vintage     (warm, faded, vignetted, optional grain)
                california  (golden-hour warm, slight saturation boost)
                cinematic   (teal shadows + orange highlights)
                fade        (matte film, lifted blacks)
                cool        (cold blue cast)
                punchy      (high contrast + saturation)
              Default: "vintage"
  crf       - Output H.264 CRF (default "23"; lower = higher quality)
  speed     - x264 encoding preset (default "medium")
  grain     - "true"/"false" — overlay subtle film grain (default "false")
"""
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from collections import deque

from script_io import read_params, input_path, output_path, finish, write_error

log = logging.getLogger("video_filter_preset")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")


# Picked up by the admin "Scan Script" feature to seed the params form.
PARAM_DEFS = json.loads(r"""[
  {
    "name": "preset",
    "description": "Choose the overall color/look for your video.",
    "default_value": "vintage",
    "allowed_values": ["bw", "noir", "sepia", "vintage", "california", "cinematic", "fade", "cool", "punchy"],
    "required": false,
    "is_image": false
  },
  {
    "name": "grain",
    "description": "Add subtle film grain for an analog feel.",
    "default_value": "false",
    "allowed_values": ["true", "false"],
    "required": false,
    "is_image": false
  },
  {
    "name": "crf",
    "description": "Output quality. Lower numbers = higher quality and larger file size. Typical range 18-28.",
    "default_value": "23",
    "allowed_values": [],
    "required": false,
    "is_image": false
  },
  {
    "name": "speed",
    "description": "Encoding speed/quality tradeoff. Faster presets use less CPU but produce slightly larger files.",
    "default_value": "medium",
    "allowed_values": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
    "required": false,
    "is_image": false
  }
]""")


# Preset → ffmpeg -vf filter chain. Order matters within a chain.
PRESETS = {
    "bw": "hue=s=0,eq=contrast=1.05",
    "noir": "hue=s=0,eq=contrast=1.4:brightness=-0.04,"
            "curves=all='0/0 0.2/0.05 0.8/0.95 1/1'",
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "vintage": "colorbalance=rs=0.10:gs=0.00:bs=-0.10:rm=0.05:bm=-0.05,"
               "curves=all='0/0.05 0.5/0.5 1/0.95',"
               "eq=saturation=0.85:contrast=0.92,"
               "vignette=PI/5",
    "california": "colorbalance=rh=0.12:gh=0.05:bh=-0.12,"
                  "eq=saturation=1.15:gamma=1.05",
    "cinematic": "colorbalance=rs=-0.15:gs=0:bs=0.15:rh=0.15:gh=0.05:bh=-0.15,"
                 "eq=contrast=1.10:saturation=1.05",
    "fade": "curves=all='0/0.10 1/0.95',eq=saturation=0.85:contrast=0.92",
    "cool": "colorbalance=rs=-0.10:bs=0.10,eq=saturation=0.95",
    "punchy": "eq=contrast=1.20:saturation=1.30",
}


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


def apply_filter(in_path, out_path, preset_name, crf="23", speed="medium", grain=False):
    if preset_name not in PRESETS:
        raise ValueError(
            f"unknown preset '{preset_name}'. valid: {', '.join(sorted(PRESETS))}"
        )

    filter_chain = PRESETS[preset_name]
    if grain:
        # Subtle film grain — temporal noise so it shimmers instead of being static.
        filter_chain += ",noise=alls=8:allf=t"

    cmd = [
        "ffmpeg", "-y",
        "-nostats",              # progress churn would drown the log
        "-i", in_path,
        "-vf", filter_chain,
        # ffmpeg sizes its thread pool from the HOST's cpu count, not the
        # container's quota, and x264 holds frame buffers plus a lookahead
        # queue per thread. Unbounded, a ~2 MP encode allocates past
        # ffmpeg-svc's 512 MB within seconds and the kernel kills it — which
        # reaches the caller as a closed connection with no status at all.
        "-threads", "2",
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", speed,
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
    return filter_chain


def main():
    # The docstring above has always promised file-mode I/O; read_input() quietly
    # made a liar of it by loading the whole video, then writing it back out to a
    # second file for ffmpeg, then reading the result back to hand over. The path
    # API keeps the promise.
    _content_type, params = read_params()

    preset = (params.get("preset") or "vintage").strip().lower()
    crf = params.get("crf", "23")
    speed = params.get("speed", "medium")
    grain = str(params.get("grain", "")).strip().lower() in {"1", "true", "yes"}

    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = input_path(tmpdir)    # the runner's file; nothing is copied
        out_path = output_path(tmpdir)  # ffmpeg writes the result in place

        if not os.path.exists(in_path) or os.path.getsize(in_path) == 0:
            write_error("no input video provided")
            return

        in_size = os.path.getsize(in_path)
        log.info("input: %.1f MB, preset=%s grain=%s", in_size / (1024 * 1024), preset, grain)

        try:
            filter_chain = apply_filter(
                in_path, out_path, preset, crf=crf, speed=speed, grain=grain
            )
        except Exception as e:
            write_error(str(e))
            return

        finish(
            out_path, "video/mp4",
            preset=preset,
            filter_chain=filter_chain,
            grain=grain,
            input_size=in_size,
            output_size=os.path.getsize(out_path),
        )


if __name__ == "__main__":
    main()
