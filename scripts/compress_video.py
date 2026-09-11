#!/usr/bin/env python3
"""
Compress Video - Reduce video file size using FFmpeg.

Optimized for AI-generated videos (Kling, Luma, etc.) which are often
too large for web use.

Params:
    quality (optional) - Preset: "archive", "web", "light" (default: "web")
    crf (optional) - Manual CRF value 0-51, lower = better (overrides quality)
    max_width (optional) - Scale down to max width, maintains aspect ratio
    max_size_mb (optional) - Target max size in MB (will re-encode if needed)
    keep_audio (optional) - Keep audio track, default: false

Quality presets:
    - "archive" - CRF 20, high quality for storage/editing
    - "web" - CRF 28, good balance for websites
    - "light" - CRF 34 + 720p, optimized for mobile/preview

Input:  Video file (MP4, WebM, MOV, etc.)
Output: Compressed MP4 (H.264)
"""
import sys
import json
import base64
import subprocess
import tempfile
import os


# Quality presets: (crf, max_width or None)
QUALITY_PRESETS = {
    "archive": (20, None),
    "web": (28, None),
    "light": (34, 720),
}

# Max re-encode attempts when targeting file size
MAX_SIZE_RETRIES = 3


def compress_video(
    input_path: str,
    output_path: str,
    crf: int = 28,
    max_width: int = None,
    max_size_mb: float = None,
    keep_audio: bool = False,
    _retry_count: int = 0
) -> dict:
    """
    Compress video using FFmpeg.

    Args:
        input_path: Path to input video
        output_path: Path to output video
        crf: Constant Rate Factor (0-51, lower = better quality)
        max_width: Maximum width (scales proportionally)
        max_size_mb: Target maximum file size in MB
        keep_audio: Whether to keep audio track (default: False)
        _retry_count: Internal counter for size-based re-encoding

    Returns:
        dict with compression metadata
    """
    # Get original file size
    original_size = os.path.getsize(input_path)

    # Build FFmpeg command
    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-i", input_path,
        "-c:v", "libx264",  # H.264 codec
        "-preset", "medium",  # Encoding speed/quality tradeoff
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",  # Compatibility
        "-movflags", "+faststart",  # Web optimization
    ]

    # Audio handling
    if keep_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])
    else:
        cmd.append("-an")

    # Add scaling if max_width specified
    if max_width:
        # Scale to max_width, maintain aspect ratio, ensure even dimensions
        cmd.extend([
            "-vf", f"scale='min({max_width},iw)':-2"
        ])

    cmd.append(output_path)

    # Run FFmpeg
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {result.stderr}")

    # Get compressed file size
    compressed_size = os.path.getsize(output_path)

    # If max_size_mb specified and file is too large, re-encode with higher CRF
    if max_size_mb and compressed_size > max_size_mb * 1024 * 1024:
        if _retry_count >= MAX_SIZE_RETRIES:
            # Give up after max retries, return what we have
            pass
        else:
            # Calculate new CRF (rough estimate)
            ratio = compressed_size / (max_size_mb * 1024 * 1024)
            new_crf = min(51, crf + int(ratio * 4))

            # Re-run with higher CRF
            return compress_video(
                input_path, output_path,
                crf=new_crf,
                max_width=max_width,
                max_size_mb=max_size_mb,
                keep_audio=keep_audio,
                _retry_count=_retry_count + 1
            )

    # Calculate compression ratio
    compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0

    metadata = {
        "original_size_bytes": original_size,
        "original_size_mb": round(original_size / (1024 * 1024), 2),
        "compressed_size_bytes": compressed_size,
        "compressed_size_mb": round(compressed_size / (1024 * 1024), 2),
        "compression_ratio": f"{compression_ratio:.0f}%",
        "crf_used": crf,
        "max_width": max_width,
        "keep_audio": keep_audio,
    }

    # Include ffmpeg warnings if any (for debugging)
    if result.stderr and "warning" in result.stderr.lower():
        metadata["ffmpeg_warnings"] = result.stderr[:500]

    return metadata


def main():
    data = json.load(sys.stdin)

    # Get video from input (base64 encoded)
    video_bytes = base64.b64decode(data["video"])
    params = data.get("params", {})

    # Parse parameters
    quality = params.get("quality", "web").lower()
    crf = params.get("crf")
    max_width = params.get("max_width")
    max_size_mb = params.get("max_size_mb")
    keep_audio = params.get("keep_audio", False)

    # Apply quality preset if no manual CRF
    if crf is None:
        preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["web"])
        crf = preset[0]
        if max_width is None:
            max_width = preset[1]
    else:
        crf = int(crf)

    if max_width:
        max_width = int(max_width)
    if max_size_mb:
        max_size_mb = float(max_size_mb)

    # Create temp files for processing
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.mp4")
        output_path = os.path.join(tmpdir, "output.mp4")

        # Write input video to temp file
        with open(input_path, "wb") as f:
            f.write(video_bytes)

        # Compress
        metadata = compress_video(
            input_path, output_path,
            crf=crf,
            max_width=max_width,
            max_size_mb=max_size_mb,
            keep_audio=keep_audio
        )

        # Read compressed video
        with open(output_path, "rb") as f:
            compressed_bytes = f.read()

    # Output
    output = {
        "video": base64.b64encode(compressed_bytes).decode(),
        "format": "mp4",
        **metadata
    }

    json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
