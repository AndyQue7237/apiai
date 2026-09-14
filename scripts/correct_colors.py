#!/usr/bin/env python3
"""
Color Correction — correct color drift between a generated image and reference.

Compares colors in the input image (e.g. AI-generated logo) against colors
in a reference image (original/source). Colors that have drifted beyond
a threshold are replaced with the closest matching color from the reference.

This is useful for correcting color drift in AI-generated images, where
generative models tend to shift colors (especially reds, golds, and oranges)
toward more saturated or different hues.

Pipeline position:
    original → ai_processing → correct_colors → final

The algorithm:
1. Extract dominant colors from both images (k-means clustering)
2. For each color in generated image that covers >min_coverage% of pixels
3. Find the closest color in the reference image (by ΔE in CIELAB)
4. If ΔE > min_delta_e, replace that color with the reference color
5. Use smart tolerance (ΔE/2) to avoid replacing similar-but-different colors

Black and white are excluded from correction — they rarely drift and
false-matching them would damage intentional use of these colors.
"""

import base64
import io
import os
import sys
import logging

import numpy as np
from PIL import Image
from sklearn.cluster import KMeans

try:
    from script_io import read_input, write_output, write_error
    SCRIPT_IO_AVAILABLE = True
except ImportError:
    SCRIPT_IO_AVAILABLE = False


log = logging.getLogger("correct_colors")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")


# ── Parameter definitions (picked up by admin "Scan Script") ──
PARAM_DEFS = [
    {
        "name": "image_reference",
        "description": "Reference image with the correct/original colors. Colors from this image are used to correct drift in the input image.",
        "default_value": "",
        "required": True,
    },
    {
        "name": "min_coverage",
        "description": "Minimum percentage of image a color must cover to be considered for correction. Range 1-50. Default 5.",
        "default_value": "5",
    },
    {
        "name": "min_delta_e",
        "description": "Minimum color difference (ΔE) to trigger correction. Range 5-50. ΔE 5-10 is noticeable, 10-15 is clear drift, 15+ is severe. Default 10.",
        "default_value": "10",
    },
    {
        "name": "n_clusters",
        "description": "Number of color clusters for analysis. Higher values detect more color variations but increase processing time. Range 8-20. Default 12.",
        "default_value": "12",
    },
]


# ───────────────────────────── helpers ─────────────────────────────

def rgb_to_lab(rgb):
    """Convert RGB (0-255) to CIELAB color space."""
    r, g, b = [x / 255.0 for x in rgb[:3]]

    def pivot(n):
        return n ** 2.4 if n > 0.04045 else n / 12.92

    r, g, b = pivot(r), pivot(g), pivot(b)

    # RGB to XYZ
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    # Normalize for D65 illuminant
    x, y, z = x / 0.95047, y / 1.0, z / 1.08883

    def f(t):
        return t ** (1/3) if t > 0.008856 else (7.787 * t) + (16 / 116)

    return (116 * f(y)) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def delta_e(lab1, lab2):
    """Calculate ΔE (Euclidean distance in CIELAB)."""
    return np.sqrt(sum((a - b) ** 2 for a, b in zip(lab1, lab2)))


def rgb_to_hex(rgb):
    """Convert RGB tuple to hex string."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def is_black_or_white(rgb, threshold=25):
    """
    Check if color is black or white (grayscale near extremes).
    Returns 'black', 'white', or None.

    Black and white are excluded because:
    - They rarely drift in AI generation
    - Matching them can cause false positives
    """
    r, g, b = rgb[:3]
    # Check if grayscale (R ≈ G ≈ B)
    if max(r, g, b) - min(r, g, b) > 30:
        return None  # Has color, not grayscale

    avg = (r + g + b) / 3
    if avg < threshold:
        return "black"
    if avg > 255 - threshold:
        return "white"
    return None


def extract_colors(img, n_colors=12, exclude_bw=True):
    """
    Extract dominant colors from image using k-means clustering.

    Returns list of (color_rgb, percentage) tuples, sorted by percentage.
    Transparent pixels are excluded. Black/white optionally excluded.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    pixels = np.array(img).reshape(-1, 4)
    # Filter out transparent pixels
    opaque = pixels[pixels[:, 3] > 128][:, :3]

    if len(opaque) < n_colors:
        return []

    kmeans = KMeans(n_clusters=n_colors, random_state=42, n_init=10)
    kmeans.fit(opaque)

    colors = kmeans.cluster_centers_.astype(int)
    labels = kmeans.labels_
    counts = np.bincount(labels)
    total = len(labels)

    results = []
    for idx in np.argsort(-counts):
        color = tuple(colors[idx])
        pct = counts[idx] / total * 100
        if exclude_bw and is_black_or_white(color):
            continue
        results.append((color, pct))

    return results


def find_best_match(color, candidates):
    """Find the best matching color from candidates based on ΔE."""
    lab1 = rgb_to_lab(color)
    best_match, best_delta = None, float("inf")

    for cand, _ in candidates:
        d = delta_e(lab1, rgb_to_lab(cand))
        if d < best_delta:
            best_delta, best_match = d, cand

    return best_match, best_delta


def replace_color_smart(img, old_color, new_color, max_delta):
    """
    Replace old_color with new_color in image, using smart tolerance.

    Only replaces pixels where: ΔE(pixel, old_color) < max_delta / 2

    This prevents accidentally replacing similar-but-different colors
    (e.g., light blue vs dark blue when targeting a drifted dark blue).
    The tolerance is half the drift distance, minimum 5 ΔE.

    Returns: (corrected_image, number_of_pixels_replaced)
    """
    pixels = np.array(img, dtype=np.float32)
    new_rgb = np.array(new_color, dtype=np.float32)
    old_lab = rgb_to_lab(old_color)

    # Tolerance: half the drift distance, minimum 5
    tolerance = max(5, max_delta / 2)

    h, w = pixels.shape[:2]
    replaced = 0

    for y in range(h):
        for x in range(w):
            if pixels[y, x, 3] < 128:  # Skip transparent
                continue
            pixel_rgb = tuple(pixels[y, x, :3].astype(int))
            pixel_lab = rgb_to_lab(pixel_rgb)
            pixel_delta = delta_e(pixel_lab, old_lab)

            if pixel_delta < tolerance:
                pixels[y, x, :3] = new_rgb
                replaced += 1

    return Image.fromarray(pixels.astype(np.uint8)), replaced


def apply_color_correction(gen_img, ref_img, min_coverage, min_delta_e, n_clusters):
    """
    Apply color correction from reference image to generated image.

    Args:
        gen_img: PIL Image (generated/AI output to correct)
        ref_img: PIL Image (reference with correct colors)
        min_coverage: Minimum % of image for a color to be corrected
        min_delta_e: Minimum ΔE to trigger correction
        n_clusters: Number of k-means clusters for color extraction

    Returns:
        (corrected_image, list_of_replacements)

    Each replacement is: (old_color, new_color, delta_e, coverage_pct, pixel_count)
    """
    gen_colors = extract_colors(gen_img, n_colors=n_clusters)
    ref_colors = extract_colors(ref_img, n_colors=n_clusters)

    if not gen_colors or not ref_colors:
        log.warning("Could not extract colors from one or both images")
        return gen_img, []

    # Find colors that need correction
    corrections_needed = []
    for gen_color, gen_pct in gen_colors:
        if gen_pct < min_coverage:
            continue
        match, delta = find_best_match(gen_color, ref_colors)
        if delta > min_delta_e:
            corrections_needed.append((gen_color, match, delta, gen_pct))

    if not corrections_needed:
        log.info("No color corrections needed")
        return gen_img, []

    # Apply corrections
    img = gen_img.copy()
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    actual_replacements = []
    for old_color, new_color, delta, pct in corrections_needed:
        img, pixel_count = replace_color_smart(img, old_color, new_color, delta)
        if pixel_count > 0:
            actual_replacements.append((old_color, new_color, delta, pct, pixel_count))
            log.info("Replaced %s -> %s (ΔE %.1f, %.0f%%, %d px)",
                     rgb_to_hex(old_color), rgb_to_hex(new_color),
                     delta, pct, pixel_count)

    return img, actual_replacements


# ─────────────────────────── apiai.me entry ───────────────────────────

def main():
    """Entry point when running in apiai.me environment."""
    body_bytes, content_type, params = read_input()
    if not body_bytes:
        write_error("No image provided (request body)")
        return

    # Required: reference image
    ref_b64 = (params.get("image_reference") or "").strip()
    if not ref_b64:
        write_error("image_reference is required")
        return

    # Parse params with validation
    try:
        min_coverage = float(params.get("min_coverage", "5") or "5")
        min_delta_e = float(params.get("min_delta_e", "10") or "10")
        n_clusters = int(params.get("n_clusters", "12") or "12")
    except ValueError as e:
        write_error(f"Invalid numeric parameter: {e}")
        return

    # Clamp to valid ranges
    min_coverage = max(1.0, min(50.0, min_coverage))
    min_delta_e = max(5.0, min(50.0, min_delta_e))
    n_clusters = max(8, min(20, n_clusters))

    # Decode images
    try:
        gen_img = Image.open(io.BytesIO(body_bytes)).convert("RGBA")
    except Exception as e:
        write_error(f"Could not decode input image: {e}")
        return

    try:
        ref_bytes = base64.b64decode(ref_b64)
        ref_img = Image.open(io.BytesIO(ref_bytes)).convert("RGBA")
    except Exception as e:
        write_error(f"Could not decode image_reference: {e}")
        return

    log.info("Correcting colors: min_coverage=%.0f%%, min_delta_e=%.0f, clusters=%d",
             min_coverage, min_delta_e, n_clusters)

    # Apply correction
    corrected_img, replacements = apply_color_correction(
        gen_img, ref_img, min_coverage, min_delta_e, n_clusters
    )

    # Output
    buf = io.BytesIO()
    corrected_img.save(buf, format="PNG")

    log.info("Color correction done: %d replacements", len(replacements))
    write_output(buf.getvalue(), "image/png")


# ─────────────────────── local CLI entry point ───────────────────────

def run_local_cli():
    """File-based CLI for local testing without apiai.me runtime."""
    try:
        from dotenv import load_dotenv
        from pathlib import Path as _Path
        _dir = _Path(__file__).resolve().parent
        for _ in range(5):
            if (_dir / ".env").exists():
                load_dotenv(_dir / ".env")
                break
            _dir = _dir.parent
    except ImportError:
        pass

    import argparse
    p = argparse.ArgumentParser(
        description="Correct color drift between generated and reference images.")
    p.add_argument("input", help="Input image (generated/AI output)")
    p.add_argument("reference", help="Reference image (original/source)")
    p.add_argument("output", help="Output PNG path")
    p.add_argument("--min-coverage", type=float, default=5.0,
                   help="Min %% coverage to correct a color (default 5)")
    p.add_argument("--min-delta-e", type=float, default=10.0,
                   help="Min ΔE to trigger correction (default 10)")
    p.add_argument("--n-clusters", type=int, default=12,
                   help="Number of color clusters (default 12)")
    args = p.parse_args()

    # Load images
    gen_img = Image.open(args.input).convert("RGBA")
    ref_img = Image.open(args.reference).convert("RGBA")

    # Clamp params
    min_coverage = max(1.0, min(50.0, args.min_coverage))
    min_delta_e = max(5.0, min(50.0, args.min_delta_e))
    n_clusters = max(8, min(20, args.n_clusters))

    log.info("Input: %s (%dx%d)", args.input, *gen_img.size)
    log.info("Reference: %s (%dx%d)", args.reference, *ref_img.size)
    log.info("Params: min_coverage=%.0f%%, min_delta_e=%.0f, clusters=%d",
             min_coverage, min_delta_e, n_clusters)

    # Apply correction
    corrected_img, replacements = apply_color_correction(
        gen_img, ref_img, min_coverage, min_delta_e, n_clusters
    )

    # Save
    corrected_img.save(args.output)

    if replacements:
        print(f"\nApplied {len(replacements)} color correction(s):")
        for old, new, delta, pct, px in replacements:
            print(f"  {rgb_to_hex(old)} -> {rgb_to_hex(new)} "
                  f"(ΔE {delta:.1f}, {pct:.0f}%, {px:,} px)")
    else:
        print("\nNo color corrections needed.")

    log.info("Wrote %s", args.output)


if __name__ == "__main__":
    if SCRIPT_IO_AVAILABLE and len(sys.argv) <= 1:
        main()
    else:
        run_local_cli()
