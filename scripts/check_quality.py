#!/usr/bin/env python3
"""
Check image quality based on megapixels, color flatness, and gradient smoothness.

Used for routing in pipelines: images below quality thresholds need AI
enhancement (e.g., GPT-2 reconstruction), while high-quality images can
go directly to upscaling.

Quality metrics:
1. Megapixels (MP) - raw resolution indicator
2. Flatness % - percentage of pixels that share one of the 16 most common colors
   High flatness = clean vector-like graphics with solid color areas
   Low flatness = many unique colors, indicates compression artifacts or noise
3. Gradient smoothness (transparent images only) - ratio of smooth alpha transitions
   to hard jumps. Measures anti-aliasing quality on transparent edges.
   High gradient = smooth AA edges (good quality)
   Low gradient = jagged/hard edges (poor quality, e.g. GIF-converted)

Routing logic:
- MP >= 1.0 → high quality (skip enhancement)
- MP < 0.09 → low quality, needs AI enhancement
- MP 0.09-1.0 + flatness < 80% → artifacts detected, needs enhancement
- MP 0.09-1.0 + transparent + gradient < 50 → poor edge quality, needs enhancement
- MP 0.09-1.0 + flatness >= 80% → acceptable quality

Outputs the image unchanged plus a metadata field for pipeline conditions.

Params:
  field              - metadata field name to write (default: "needs_enhancement")
  mp_high_threshold  - MP above this is always high quality (default: "1.0")
  mp_low_threshold   - MP below this always needs enhancement (default: "0.09")
  flatness_threshold - flatness % below this triggers enhancement (default: "80")
  gradient_threshold - gradient % below this triggers enhancement for transparent images (default: "50")
"""
import sys
import json
import base64
import io
import numpy as np
from PIL import Image

try:
    from script_io import read_input, write_output, write_error
except ImportError:
    # Local testing fallback
    pass

PARAM_DEFS = [
    {"name": "field", "description": "Metadata field name for the result boolean", "default_value": "needs_enhancement"},
    {"name": "mp_high_threshold", "description": "MP above this is always high quality (skip enhancement)", "default_value": "1.0"},
    {"name": "mp_low_threshold", "description": "MP below this always needs enhancement", "default_value": "0.09"},
    {"name": "flatness_threshold", "description": "Flatness % below this triggers enhancement (for borderline MP)", "default_value": "80"},
    {"name": "gradient_threshold", "description": "Gradient % below this triggers enhancement for transparent images", "default_value": "50"},
]


def calculate_flatness_percent(img, num_colors=16, tolerance=12):
    """
    Calculate percentage of pixels that use one of the N most common colors.

    High flatness = clean vector-like graphics with solid color areas
    Low flatness = many unique colors (compression artifacts, gradients, noise)

    A clean logo from vector source will have very few distinct colors (high flatness).
    A logo that's been through lossy compression or bad upscaling will have
    many color variations (low flatness).

    Colors are grouped by tolerance (e.g., tolerance=12 means colors within
    12 RGB units are considered the same). This prevents anti-aliasing and
    subtle gradients from artificially lowering the flatness score.

    Args:
        img: PIL Image (RGB or RGBA)
        num_colors: Number of top colors to consider (default: 16)
        tolerance: Color grouping tolerance (default: 12)

    Returns:
        float: Percentage of pixels using the top N colors (0-100)
    """
    from collections import Counter

    # Convert to RGB
    rgb = img.convert('RGB')
    pixels = list(rgb.getdata())

    total_pixels = len(pixels)
    if total_pixels == 0:
        return 100.0

    # Group similar colors by quantizing to tolerance
    quant_pixels = [
        (r // tolerance * tolerance, g // tolerance * tolerance, b // tolerance * tolerance)
        for r, g, b in pixels
    ]

    # Count quantized colors
    color_counts = Counter(quant_pixels)

    # Get the top N colors
    top_colors = color_counts.most_common(num_colors)

    # Sum pixels using top colors
    top_color_pixels = sum(count for _, count in top_colors)

    return (top_color_pixels / total_pixels) * 100


def is_transparent(img):
    """
    Check if image has actual transparency (not just RGBA mode with full opacity).

    Args:
        img: PIL Image

    Returns:
        bool: True if image has transparent pixels
    """
    if img.mode != 'RGBA':
        return False
    alpha = np.array(img.split()[3])
    return bool(alpha.min() < 255)  # Convert numpy.bool_ to Python bool for JSON


def calculate_gradient_smooth(img):
    """
    Calculate gradient smoothness on alpha channel for transparent images.

    Measures the ratio of smooth alpha transitions (good anti-aliasing) to
    hard/medium jumps (jagged edges). High values indicate smooth, well-antialiased
    edges. Low values indicate poor quality edges (e.g., GIF-converted images,
    compression artifacts).

    Args:
        img: PIL Image (must be RGBA with transparency)

    Returns:
        float: Gradient smoothness percentage (0-100), or None if not applicable
    """
    if img.mode != 'RGBA':
        return None

    alpha = np.array(img.split()[3], dtype=np.float32)

    # Check if there's any transparency
    if alpha.min() == 255:
        return None  # Fully opaque, no transparency to analyze

    # Calculate gradient magnitude
    gy, gx = np.gradient(alpha)
    grad_mag = np.sqrt(gx**2 + gy**2)

    # Count edge pixels by gradient magnitude:
    # - Small steps (< 50): smooth anti-aliasing (good)
    # - Medium jumps (50-200): compression artifacts, poor AA (bad)
    # - Large jumps (>= 200): hard edges (bad but expected for some logos)
    small_steps = np.sum((grad_mag > 0) & (grad_mag < 50))
    medium_jumps = np.sum((grad_mag >= 50) & (grad_mag < 200))
    large_jumps = np.sum(grad_mag >= 200)

    total_edges = small_steps + medium_jumps + large_jumps
    if total_edges == 0:
        return None  # No edges at all

    # Smooth ratio: percentage of edges that are smooth
    # High = good quality, Low = bad quality (jagged/artifacts)
    smooth_ratio = (small_steps / total_edges) * 100
    return round(smooth_ratio, 1)


def check_quality(img, mp_high=1.0, mp_low=0.09, flatness_threshold=80, gradient_threshold=50):
    """
    Check image quality and determine if enhancement is needed.

    Routing logic:
    1. MP >= mp_high → skip (high resolution)
    2. MP < mp_low → enhance (too small)
    3. flatness < flatness_threshold → enhance (artifacts/noise)
    4. transparent + gradient < gradient_threshold → enhance (poor edge quality)
    5. Otherwise → skip (acceptable quality)

    Args:
        img: PIL Image
        mp_high: MP above this is always good quality
        mp_low: MP below this always needs enhancement
        flatness_threshold: Flatness % below this triggers enhancement
        gradient_threshold: Gradient % below this triggers enhancement (transparent only)

    Returns:
        tuple: (needs_enhancement: bool, metadata: dict)
    """
    width, height = img.size
    mp = (width * height) / 1_000_000

    # Calculate quality metrics
    flatness_pct = calculate_flatness_percent(img)
    transparent = is_transparent(img)
    gradient_pct = calculate_gradient_smooth(img) if transparent else None

    # Routing logic
    if mp >= mp_high:
        # High resolution - assume good quality
        needs_enhancement = False
        reason = "high_mp"
    elif mp < mp_low:
        # Too small - needs AI reconstruction
        needs_enhancement = True
        reason = "low_mp"
    elif flatness_pct < flatness_threshold:
        # Borderline MP with low flatness = artifacts/noise
        needs_enhancement = True
        reason = "low_flatness"
    elif transparent and gradient_pct is not None and gradient_pct < gradient_threshold:
        # Transparent image with poor edge quality (jagged, no AA)
        needs_enhancement = True
        reason = "low_gradient"
    else:
        # Acceptable quality
        needs_enhancement = False
        reason = "acceptable"

    metadata = {
        "width": width,
        "height": height,
        "megapixels": round(mp, 3),
        "flatness_pct": round(flatness_pct, 1),
        "transparent": transparent,
        "gradient_pct": round(gradient_pct, 1) if gradient_pct is not None else None,
        "reason": reason,
        "needs_enhancement": needs_enhancement,
    }

    return needs_enhancement, metadata


def main():
    data = json.load(sys.stdin)
    img_bytes = base64.b64decode(data["image"])
    img = Image.open(io.BytesIO(img_bytes))
    params = data.get("params", {})

    field = params.get("field", "needs_enhancement")
    mp_high = float(params.get("mp_high_threshold", "1.0"))
    mp_low = float(params.get("mp_low_threshold", "0.09"))
    flatness_threshold = float(params.get("flatness_threshold", "80"))
    gradient_threshold = float(params.get("gradient_threshold", "50"))

    result, metadata = check_quality(img, mp_high, mp_low, flatness_threshold, gradient_threshold)

    # Pass image through as RGBA PNG
    out = img.convert("RGBA")
    buf = io.BytesIO()
    out.save(buf, format="PNG")

    output = {
        "image": base64.b64encode(buf.getvalue()).decode(),
        "content_type": "image/png",
        field: result,
        "megapixels": metadata["megapixels"],
        "flatness_pct": metadata["flatness_pct"],
        "transparent": metadata["transparent"],
        "gradient_pct": metadata["gradient_pct"],
        "quality_reason": metadata["reason"],
    }

    json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
