#!/usr/bin/env python3
"""
Convert a MOV video to MP4 (H.264 + AAC).

Accepts video input (MOV or other formats) and converts it to MP4 using ffmpeg
with H.264 video codec and AAC audio codec.

Params:
  crf - Constant Rate Factor for quality (default: "23", lower = better quality)
  preset - Encoding speed/quality tradeoff (default: "medium")
"""
import subprocess
import tempfile
import os
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "crf", "description": "Constant Rate Factor for quality (lower = better)", "default_value": "23"},
    {"name": "preset", "description": "Encoding speed preset", "default_value": "medium", "allowed_values": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]},
]


def convert_mov_to_mp4(input_bytes, crf="23", preset="medium"):
    """Convert video bytes to MP4 bytes using ffmpeg."""
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "input.mov")
        out_path = os.path.join(tmpdir, "output.mp4")

        with open(in_path, "wb") as f:
            f.write(input_bytes)

        cmd = [
            "ffmpeg", "-y",
            "-i", in_path,
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            out_path,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")

        with open(out_path, "rb") as f:
            return f.read()


def main():
    input_bytes, content_type, params = read_input()
    
    if not input_bytes:
        write_error("no input video provided")
        return

    crf = params.get("crf", "23")
    preset = params.get("preset", "medium")

    try:
        output_bytes = convert_mov_to_mp4(input_bytes, crf=crf, preset=preset)
        
        write_output(
            output_bytes, 
            "video/mp4",
            converted=True,
            input_size=len(input_bytes),
            output_size=len(output_bytes)
        )

    except Exception as e:
        write_error(str(e))


if __name__ == "__main__":
    main()
