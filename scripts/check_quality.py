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
   to medium jumps. Measures anti-aliasing quality on transparent edges.
   High gradient = smooth AA edges OR clean hard-cut edges (good quality)
   Low gradient = medium jumps indicating compression artifacts (poor quality)

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
import io
import sys
import logging

import numpy as np
from PIL import Image

log = logging.getLogger("check_quality")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")

# Gradient magnitude thresholds for edge analysis
# Pixels with gradient magnitude below this are "smooth" (good AA or flat areas)
GRADIENT_SMALL_STEP_MAX = 50
# Pixels with gradient magnitude above this are "hard edges" (intentional, not artifacts)
GRADIENT_HARD_EDGE_MIN = 200

# Maximum dimension for quality analysis (downsample larger images for speed)
MAX_ANALYSIS_DIM = 500

# Reserved output field names that cannot be used as the 'field' param
RESERVED_FIELDS = {"image", "content_type", "error"}

PARAM_DEFS = [
    {"name": "field", "type": "string", "description": "Metadata field name for the result boolean", "default_value": "needs_enhancement"},
    {"name": "mp_high_threshold", "type": "float", "description": "MP above this is always high quality (skip enhancement)", "default_value": "1.0"},
    {"name": "mp_low_threshold", "type": "float", "description": "MP below this always needs enhancement", "default_value": "0.09"},
    {"name": "flatness_threshold", "type": "float", "description": "Flatness % below this triggers enhancement (for borderline MP)", "default_value": "80"},
    {"name": "gradient_threshold", "type": "float", "description": "Gradient % below this triggers enhancement for transparent images", "default_value": "50"},
]


def _downsample_for_analysis(img, max_dim=MAX_ANALYSIS_DIM):
    """Downsample image if larger than max_dim for faster analysis."""
    w, h = img.size
    if max(w, h) <= max_dim:
        return img
    scale = max_dim / max(w, h)
    new_size = (int(w * scale), int(h * scale))
    return img.resize(new_size, Image.LANCZOS)


def calculate_flatness_percent(img, num_colors=16, tolerance=12):
    """
    Calculate percentage of pixels that use one of the N most common colors.

    High flatness = clean vector-like graphics with solid color areas
    Low flatness = many unique colors (compression artifacts, gradients, noise)

    Uses vectorized numpy operations for performance.
    Transparent pixels (alpha < 128) are excluded from the calculation.

    Args:
        img: PIL Image (RGB or RGBA)
        num_colors: Number of top colors to consider (default: 16)
        tolerance: Color grouping tolerance (default: 12)

    Returns:
        float: Percentage of pixels using the top N colors (0-100)
    """
    # Downsample for speed (flatness is statistical, doesn't need full res)
    img = _downsample_for_analysis(img)

    # Get pixels as numpy array
    if img.mode == 'RGBA':
        pixels_array = np.array(img)
        # Mask out transparent pixels (alpha < 128)
        opaque_mask = pixels_array[:, :, 3] >= 128
        rgb_pixels = pixels_array[:, :, :3][opaque_mask]
    else:
        rgb_pixels = np.array(img.convert('RGB')).reshape(-1, 3)

    total_pixels = len(rgb_pixels)
    if total_pixels == 0:
        return 100.0

    # Quantize colors (vectorized)
    quant_pixels = (rgb_pixels // tolerance * tolerance)

    # Pack RGB into single int for efficient counting
    packed = (quant_pixels[:, 0].astype(np.int32) << 16) | \
             (quant_pixels[:, 1].astype(np.int32) << 8) | \
             quant_pixels[:, 2].astype(np.int32)

    # Count unique colors
    unique, counts = np.unique(packed, return_counts=True)

    # Get top N colors
    top_indices = np.argsort(-counts)[:num_colors]
    top_color_pixels = counts[top_indices].sum()

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
    return bool(alpha.min() < 255)


def calculate_gradient_smooth(img):
    """
    Calculate gradient smoothness on alpha channel for transparent images.

    Measures the ratio of smooth/hard edges to medium jumps. Medium jumps
    (between GRADIENT_SMALL_STEP_MAX and GRADIENT_HARD_EDGE_MIN) indicate
    compression artifacts or poor anti-aliasing.

    Both smooth AA edges AND clean hard-cut edges score well — only medium
    jumps (the hallmark of compression artifacts) lower the score.

    Args:
        img: PIL Image (must be RGBA with transparency)

    Returns:
        float: Gradient quality percentage (0-100), or None if not applicable
    """
    if img.mode != 'RGBA':
        return None

    # Downsample for speed
    img = _downsample_for_analysis(img)

    alpha = np.array(img.split()[3], dtype=np.float32)

    # Check if there's any transparency
    if alpha.min() == 255:
        return None  # Fully opaque, no transparency to analyze

    # Calculate gradient magnitude
    gy, gx = np.gradient(alpha)
    grad_mag = np.sqrt(gx**2 + gy**2)

    # Count edge pixels by gradient magnitude:
    # - Small steps (< GRADIENT_SMALL_STEP_MAX): smooth anti-aliasing (good)
    # - Medium jumps: compression artifacts, poor AA (bad)
    # - Large jumps (>= GRADIENT_HARD_EDGE_MIN): intentional hard edges (good)
    small_steps = np.sum((grad_mag > 0) & (grad_mag < GRADIENT_SMALL_STEP_MAX))
    medium_jumps = np.sum((grad_mag >= GRADIENT_SMALL_STEP_MAX) & (grad_mag < GRADIENT_HARD_EDGE_MIN))
    large_jumps = np.sum(grad_mag >= GRADIENT_HARD_EDGE_MIN)

    total_edges = small_steps + medium_jumps + large_jumps
    if total_edges == 0:
        return None  # No edges at all

    # Quality ratio: percentage of edges that are NOT medium jumps
    # Both smooth AA (small_steps) and clean hard cuts (large_jumps) are good
    good_edges = small_steps + large_jumps
    quality_ratio = (good_edges / total_edges) * 100
    return round(quality_ratio, 1)


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
        # Transparent image with poor edge quality (medium jumps = artifacts)
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
        "quality_reason": reason,
        "needs_enhancement": needs_enhancement,
    }

    return needs_enhancement, metadata


# ─────────────────────────── apiai.me entry ───────────────────────────

def main():
    """Entry point when running in apiai.me environment."""
    from script_io import read_input, write_output, write_error

    body_bytes, content_type, params = read_input()
    if not body_bytes:
        write_error("No image provided")
        return

    try:
        img = Image.open(io.BytesIO(body_bytes))
    except Exception as e:
        write_error(f"Could not decode image: {e}")
        return

    # Parse params
    field = params.get("field", "needs_enhancement")

    # Guard against reserved field names
    if field in RESERVED_FIELDS:
        write_error(f"Invalid field name '{field}' - reserved by platform")
        return

    try:
        mp_high = float(params.get("mp_high_threshold", "1.0") or "1.0")
        mp_low = float(params.get("mp_low_threshold", "0.09") or "0.09")
        flatness_threshold = float(params.get("flatness_threshold", "80") or "80")
        gradient_threshold = float(params.get("gradient_threshold", "50") or "50")
    except ValueError as e:
        write_error(f"Invalid numeric parameter: {e}")
        return

    # Validate mp_high > mp_low
    if mp_low >= mp_high:
        write_error(f"mp_low_threshold ({mp_low}) must be less than mp_high_threshold ({mp_high})")
        return

    result, metadata = check_quality(img, mp_high, mp_low, flatness_threshold, gradient_threshold)

    log.info("Quality check: MP=%.3f, flatness=%.1f%%, gradient=%s, result=%s (%s)",
             metadata["megapixels"], metadata["flatness_pct"],
             metadata["gradient_pct"], result, metadata["quality_reason"])

    # Pass image through as RGBA PNG
    out = img.convert("RGBA")
    buf = io.BytesIO()
    out.save(buf, format="PNG")

    # Output with metadata as kwargs
    write_output(
        buf.getvalue(),
        "image/png",
        **{
            field: result,
            "megapixels": metadata["megapixels"],
            "flatness_pct": metadata["flatness_pct"],
            "transparent": metadata["transparent"],
            "gradient_pct": metadata["gradient_pct"],
            "quality_reason": metadata["quality_reason"],
        }
    )


# ─────────────────────── local CLI entry point ───────────────────────

def run_local_cli():
    """File-based CLI for local testing without apiai.me runtime."""
    import argparse

    p = argparse.ArgumentParser(description="Check image quality for pipeline routing")
    p.add_argument("input", help="Input image path")
    p.add_argument("--mp-high", type=float, default=1.0, help="MP threshold for high quality")
    p.add_argument("--mp-low", type=float, default=0.09, help="MP threshold for low quality")
    p.add_argument("--flatness", type=float, default=80, help="Flatness threshold")
    p.add_argument("--gradient", type=float, default=50, help="Gradient threshold")
    args = p.parse_args()

    if args.mp_low >= args.mp_high:
        print(f"Error: mp_low ({args.mp_low}) must be less than mp_high ({args.mp_high})")
        sys.exit(1)

    img = Image.open(args.input)
    result, metadata = check_quality(img, args.mp_high, args.mp_low, args.flatness, args.gradient)

    print(f"Image: {args.input}")
    print(f"  Size: {metadata['width']}x{metadata['height']} ({metadata['megapixels']} MP)")
    print(f"  Flatness: {metadata['flatness_pct']:.1f}%")
    print(f"  Transparent: {metadata['transparent']}")
    if metadata['gradient_pct'] is not None:
        print(f"  Gradient: {metadata['gradient_pct']:.1f}%")
    print(f"  Needs enhancement: {result} ({metadata['quality_reason']})")


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        main()
    else:
        run_local_cli()
