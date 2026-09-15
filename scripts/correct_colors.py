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
5. Use smart tolerance (ΔE/2, max 15) to avoid replacing similar-but-different colors

Black and white are excluded from correction — they rarely drift and
false-matching them would damage intentional use of these colors.
"""

import base64
import io
import sys
import logging
import os

import numpy as np
from PIL import Image
from scipy.cluster.vq import kmeans2
from skimage.color import rgb2lab

# Optional: replicate for auto-crop (Florence-2)
try:
    import replicate
    HAS_REPLICATE = True
except ImportError:
    HAS_REPLICATE = False

log = logging.getLogger("correct_colors")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")

# Black/white detection thresholds
BW_BRIGHTNESS_THRESHOLD = 25      # Pixels darker than this are "black"
BW_GRAYSCALE_TOLERANCE = 30       # Max R/G/B spread to be considered grayscale (restored from original)

# Near-white/highlight exclusion (colors too light to be brand colors)
NEAR_WHITE_THRESHOLD = 220        # Average RGB above this is likely a highlight, exclude

# Smart replacement tolerance
MIN_REPLACEMENT_TOLERANCE = 5     # Minimum ΔE tolerance for color replacement
MAX_REPLACEMENT_TOLERANCE = 15    # Maximum ΔE tolerance (cap for safety)

# Downsampling for clustering (color distribution preserved at small sizes)
MAX_CLUSTER_DIM = 400  # Increased from 200 for better color detection

# K-means stability (simulate sklearn's n_init)
KMEANS_N_INIT = 10  # Run clustering multiple times, pick best (matches sklearn default)

# Maximum ΔE for a valid color match (beyond this, it's not drift, it's wrong match)
MAX_MATCH_DELTA_E = 40


# Florence-2 model for auto-crop
FLORENCE_MODEL = "lucataco/florence-2-large:da53547e17d45b9cfb48174b2f18af8b83ca020fa76db62136bf9c6616762595"
CROP_MIN_PADDING = 5  # Hardcoded, works well for logos


# ── Parameter definitions (picked up by admin "Scan Script") ──
PARAM_DEFS = [
    {
        "name": "image_reference",
        "type": "string",
        "description": "Base64-encoded reference image with correct/original colors. Colors from this image are used to correct drift in the input image.",
        "default_value": "",
        "required": True,
    },
    {
        "name": "min_coverage",
        "type": "float",
        "description": "Minimum percentage of image a color must cover to be considered for correction. Range 1-50. Default 5.",
        "default_value": "5",
    },
    {
        "name": "min_delta_e",
        "type": "float",
        "description": "Minimum color difference (ΔE) to trigger correction. Range 5-50. ΔE 5-10 is noticeable, 10-15 is clear drift, 15+ is severe. Default 10.",
        "default_value": "10",
    },
    {
        "name": "n_clusters",
        "type": "int",
        "description": "Number of color clusters for analysis. Higher values detect more color variations but increase processing time. Range 8-20. Default 12.",
        "default_value": "12",
    },
    {
        "name": "auto_crop_reference",
        "type": "boolean",
        "description": "Auto-crop reference image before color extraction using Florence-2 object detection. Recommended when reference has large background areas. Default true.",
        "default_value": "true",
    },
    {
        "name": "crop_query",
        "type": "string",
        "description": "Detection query for auto-crop (e.g. 'logo', 'product', 'subject'). Only used if auto_crop_reference is true.",
        "default_value": "complete logo with text, full team logo with text, entire emblem, club logo",
    },
]


# ───────────────────────────── helpers ─────────────────────────────

def auto_crop_image(img, query):
    """
    Auto-crop image using Florence-2 object detection via Replicate.

    Returns cropped image if detection succeeds, otherwise returns original.
    """
    if not HAS_REPLICATE:
        log.warning("replicate not installed, skipping auto-crop")
        return img

    # Convert to bytes for API
    buf = io.BytesIO()
    img_format = "PNG" if img.mode == "RGBA" else "JPEG"
    img.save(buf, format=img_format)
    img_bytes = buf.getvalue()

    mime = "image/png" if img_format == "PNG" else "image/jpeg"
    data_uri = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"

    try:
        output = replicate.run(
            FLORENCE_MODEL,
            input={
                "image": data_uri,
                "task_input": "Caption to Phrase Grounding",
                "text_input": query,
            },
        )
    except Exception as e:
        log.warning("Florence-2 API error: %s, using original image", e)
        return img

    # Parse output
    text_output = output.get("text", "")
    try:
        import ast
        parsed = ast.literal_eval(text_output) if isinstance(text_output, str) else text_output
    except Exception:
        log.warning("Could not parse Florence-2 output, using original image")
        return img

    grounding = parsed.get("<CAPTION_TO_PHRASE_GROUNDING>", {})
    bboxes = grounding.get("bboxes", [])

    if not bboxes:
        log.warning("No detection found, using original image")
        return img

    # Crop with padding
    bbox = bboxes[0]
    x1, y1, x2, y2 = bbox
    logo_width = x2 - x1
    logo_height = y2 - y1
    img_width, img_height = img.size

    # Calculate padding (same logic as detect_and_crop.py)
    padding_percent = 5
    padding_x_pct = int(logo_width * (padding_percent / 100))
    padding_y_pct = int(logo_height * (padding_percent / 100))

    desired_padding_x = max(padding_x_pct, CROP_MIN_PADDING)
    desired_padding_y = max(padding_y_pct, CROP_MIN_PADDING)

    max_pad_left = x1
    max_pad_right = img_width - x2
    max_pad_top = y1
    max_pad_bottom = img_height - y2

    padding_x = min(desired_padding_x, max_pad_left, max_pad_right)
    padding_y = min(desired_padding_y, max_pad_top, max_pad_bottom)

    # Centered crop
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2

    crop_w = logo_width + 2 * padding_x
    crop_h = logo_height + 2 * padding_y

    cx1 = int(max(0, center_x - crop_w / 2))
    cy1 = int(max(0, center_y - crop_h / 2))
    cx2 = int(min(img_width, center_x + crop_w / 2))
    cy2 = int(min(img_height, center_y + crop_h / 2))

    cropped = img.crop((cx1, cy1, cx2, cy2))
    log.info("Auto-cropped reference: %dx%d -> %dx%d", img_width, img_height, cropped.width, cropped.height)

    return cropped


def _downsample_for_clustering(img, max_dim=MAX_CLUSTER_DIM):
    """Downsample image for faster clustering (color distribution preserved)."""
    w, h = img.size
    if max(w, h) <= max_dim:
        return img
    scale = max_dim / max(w, h)
    new_size = (int(w * scale), int(h * scale))
    return img.resize(new_size, Image.LANCZOS)


def rgb_to_hex(rgb):
    """Convert RGB tuple to hex string."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def is_black_or_white_or_highlight(rgb):
    """
    Check if color is black, white, or a near-white highlight.
    Returns 'black', 'white', 'highlight', or None.

    These are excluded because:
    - Black/white rarely drift in AI generation
    - Near-white highlights are shading artifacts, not brand colors
    - Matching them can cause false positives
    """
    r, g, b = rgb[:3]
    avg = (r + g + b) / 3

    # Check for near-white highlights (even with some color variation)
    # These are shading/highlight colors that shouldn't be corrected
    if avg > NEAR_WHITE_THRESHOLD:
        return "highlight"

    # Check if grayscale (R ≈ G ≈ B)
    if max(r, g, b) - min(r, g, b) > BW_GRAYSCALE_TOLERANCE:
        return None  # Has color, not grayscale

    if avg < BW_BRIGHTNESS_THRESHOLD:
        return "black"
    if avg > 255 - BW_BRIGHTNESS_THRESHOLD:
        return "white"
    return None


def extract_colors(img, n_colors=12, exclude_bw=True):
    """
    Extract dominant colors from image using k-means clustering.

    Returns list of (color_rgb, percentage) tuples, sorted by percentage.
    Transparent pixels are excluded. Black/white optionally excluded.
    Uses scipy.cluster.vq.kmeans2 (sklearn not available on platform).
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Downsample for speed (color distribution is preserved)
    img = _downsample_for_clustering(img)

    pixels = np.array(img).reshape(-1, 4)
    # Filter out transparent pixels
    opaque = pixels[pixels[:, 3] > 128][:, :3].astype(np.float32)

    if len(opaque) < n_colors:
        return []

    # Run kmeans2 multiple times and pick best result (simulate sklearn n_init)
    # This improves stability since scipy kmeans2 can be sensitive to initialization
    best_centroids, best_labels, best_distortion = None, None, float('inf')
    for i in range(KMEANS_N_INIT):
        try:
            centroids, labels = kmeans2(opaque, n_colors, minit='points', seed=42 + i)
            # Calculate distortion (sum of squared distances to centroids)
            distortion = np.sum((opaque - centroids[labels]) ** 2)
            if distortion < best_distortion:
                best_centroids, best_labels, best_distortion = centroids, labels, distortion
        except Exception:
            continue  # Skip failed iterations

    if best_centroids is None:
        return []

    colors = best_centroids.astype(int)
    counts = np.bincount(best_labels, minlength=n_colors)
    total = len(best_labels)

    results = []
    for idx in np.argsort(-counts):
        color = tuple(np.clip(colors[idx], 0, 255))
        pct = counts[idx] / total * 100
        if exclude_bw and is_black_or_white_or_highlight(color):
            continue
        results.append((color, pct))

    return results


def find_best_match(color, candidates):
    """
    Find the best matching color from candidates based on ΔE.

    Returns (best_match, delta_e) or (None, inf) if no valid match found.
    A match is invalid if delta_e > MAX_MATCH_DELTA_E (not drift, wrong match).
    """
    # Convert single color to Lab (skimage expects 0-1 range, shape (1,1,3))
    color_rgb = np.array([[color[:3]]], dtype=np.float32) / 255.0
    lab1 = rgb2lab(color_rgb)[0, 0]

    best_match, best_delta = None, float("inf")

    for cand, _ in candidates:
        cand_rgb = np.array([[cand[:3]]], dtype=np.float32) / 255.0
        lab2 = rgb2lab(cand_rgb)[0, 0]
        d = np.sqrt(np.sum((lab1 - lab2) ** 2))
        if d < best_delta:
            best_delta, best_match = d, cand

    # Safety check: if best match is too far, it's not drift, it's wrong match
    if best_delta > MAX_MATCH_DELTA_E:
        log.warning("No valid match for %s (best was ΔE %.1f > max %d)",
                    rgb_to_hex(color), best_delta, MAX_MATCH_DELTA_E)
        return None, float("inf")

    return best_match, best_delta


def replace_color_smart(img, old_color, new_color, max_delta):
    """
    Replace old_color with new_color in image, using smart tolerance.

    Vectorized implementation using skimage.color.rgb2lab for speed.
    Only replaces pixels where: ΔE(pixel, old_color) < tolerance
    Tolerance is min(MAX_REPLACEMENT_TOLERANCE, max(MIN_REPLACEMENT_TOLERANCE, max_delta/2))

    Returns: (corrected_image, number_of_pixels_replaced)
    """
    pixels = np.array(img, dtype=np.float32)
    h, w = pixels.shape[:2]

    # Tolerance: half the drift distance, clamped to safe range
    tolerance = min(MAX_REPLACEMENT_TOLERANCE, max(MIN_REPLACEMENT_TOLERANCE, max_delta / 2))

    # Create mask for opaque pixels
    opaque_mask = pixels[:, :, 3] >= 128

    # Convert RGB to Lab for all pixels (vectorized)
    # skimage expects (H, W, 3) in range 0-1
    rgb_normalized = pixels[:, :, :3] / 255.0
    all_lab = rgb2lab(rgb_normalized)

    # Convert old_color to Lab
    old_rgb = np.array([[old_color[:3]]], dtype=np.float32) / 255.0
    old_lab = rgb2lab(old_rgb)[0, 0]

    # Calculate ΔE for all pixels (vectorized)
    delta_e = np.sqrt(np.sum((all_lab - old_lab) ** 2, axis=2))

    # Create replacement mask: opaque AND within tolerance
    replace_mask = opaque_mask & (delta_e < tolerance)

    # Apply replacement
    new_rgb = np.array(new_color[:3], dtype=np.float32)
    pixels[replace_mask, :3] = new_rgb

    replaced = int(np.sum(replace_mask))
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
        # Skip if no valid match found (delta > MAX_MATCH_DELTA_E)
        if match is None:
            continue
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
    from script_io import read_input, write_output, write_error

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

    # Boolean params
    auto_crop_str = (params.get("auto_crop_reference", "true") or "true").lower()
    auto_crop_reference = auto_crop_str in ("true", "1", "yes")
    crop_query = params.get("crop_query", "complete logo with text, full team logo with text, entire emblem, club logo") or "complete logo with text, full team logo with text, entire emblem, club logo"

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

    # Auto-crop reference if enabled
    if auto_crop_reference:
        log.info("Auto-cropping reference with query: %s", crop_query)
        ref_img = auto_crop_image(ref_img, crop_query)

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
    write_output(
        buf.getvalue(),
        "image/png",
        colors_corrected=len(replacements),
    )


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
    p.add_argument("--auto-crop", action="store_true", default=True,
                   help="Auto-crop reference using Florence-2 (default: true)")
    p.add_argument("--no-auto-crop", dest="auto_crop", action="store_false",
                   help="Disable auto-crop of reference")
    p.add_argument("--crop-query", type=str,
                   default="complete logo with text, full team logo with text, entire emblem, club logo",
                   help="Detection query for auto-crop")
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

    # Auto-crop reference if enabled
    if args.auto_crop:
        log.info("Auto-cropping reference with query: %s", args.crop_query)
        ref_img = auto_crop_image(ref_img, args.crop_query)
        log.info("Reference after crop: %dx%d", *ref_img.size)

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
    if len(sys.argv) <= 1:
        main()
    else:
        run_local_cli()
