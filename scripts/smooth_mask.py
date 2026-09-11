#!/usr/bin/env python3
"""
Smooth a jagged binary mask (typically from a SAM-style segmenter).

Cleans up pixel-staircase aliasing and rounds corners without eroding
thin features. Outputs a grayscale mask with a semi-transparent edge ready to be used
as an alpha for compositing, inpainting, or further pipeline steps.

Two modes (pick via the `mode` parameter):

  simple (default)
      Signed-distance-function (SDF) smoothing with a single sigma.
      Best for masks that are mostly large blobs (e.g. upholstery,
      cushions, panels). Heavier smoothing produces very rounded edges.

  adaptive
      Spatially-varying SDF blur. Thin features get low sigma so they
      are preserved; thick blobs get high sigma for maximum smoothing.
      A maximum-filter on the inside-distance map propagates local
      thickness outward so each boundary pixel knows whether it belongs
      to a thin region or a thick one. Best for masks with mixed
      thin/thick features (frames, structural lines, complex shapes).

Algorithm (both modes share cleanup):
  1. Binarize input at 0.5.
  2. (Optional) Fill enclosed black holes.
  3. (Optional) Remove white "speckle" components below min_region_size.
  4. (Optional) Grow/shrink by expand_px: positive pre-dilates to preserve
     corner coverage after the SDF blur rounds them inward; negative erodes
     for a slightly tighter mask.
  5. Compute signed distance function (positive inside, negative outside).
  6. Mode-specific blur:
       simple   -> single Gaussian on SDF
       adaptive -> blend(low-sigma blur, high-sigma blur) by local thickness
  7. Threshold at SDF=0 with a semi-transparent ramp of width transparent_edge_px.

Entry points:
  - main()          — apiai.me runtime (reads via script_io, writes back)
  - run_local_cli() — file-based CLI for local testing; activated when
                      script_io is unavailable or argv has positional args
"""

import io
import sys
import logging

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

try:
    from script_io import read_input, write_output, write_error
    SCRIPT_IO_AVAILABLE = True
except ImportError:
    SCRIPT_IO_AVAILABLE = False

log = logging.getLogger("smooth_mask")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")

# ── Parameter definitions (picked up by admin "Scan Script") ──
PARAM_DEFS = [
    {
        "name": "mode",
        "description": "'simple' = single-sigma SDF blur for blob masks (fabric/cushions). 'adaptive' = spatially-varying blur that preserves thin features (frame/leg masks).",
        "default_value": "simple",
    },
    {
        "name": "smooth_strength",
        "description": "Smoothing intensity 0..1 (default 1.0 = max). Simple mode: sigma up to 7.5 px. Adaptive mode: high_sigma up to 5 px (thin features stay at 1.5 px).",
        "default_value": "1.0",
    },
    {
        "name": "min_region_size",
        "description": "Remove white speckle smaller than N pixels (px^2). 0 disables.",
        "default_value": "50",
    },
    {
        "name": "fill_holes",
        "description": "Fill enclosed black holes inside the mask. 'true' or 'false'. Disable for masks with legitimate gaps (e.g. between chair legs).",
        "default_value": "true",
    },
    {
        "name": "transparent_edge_px",
        "description": "Width in pixels of the semi-transparent band along the mask edge. Higher = softer/wider transition. 0 = hard binary (gives pixel-stair-step artefacts on curved edges).",
        "default_value": "1.5",
    },
    {
        "name": "expand_px",
        "description": "Grow (+) or shrink (-) the mask by N pixels before smoothing, -20..20. Positive pre-dilates so sharp corners aren't eaten by the SDF blur (prevents halos when compositing); negative erodes for a slightly tighter mask. Use 3-4 for blob masks, 0 for frame masks, negative to inset.",
        "default_value": "4",
    },
    {
        "name": "target_format",
        "description": "Output aspect ratio. 'original' keeps input dims. Otherwise pads (no crop) to the given aspect — options: 1:1, 3:4, 4:3, 9:16, 16:9. The padded area is filled with 0 (outside the mask).",
        "default_value": "original",
    },
]


# ───────────────────────────── helpers ─────────────────────────────

def _filter_small_components(binary, min_size):
    """Remove connected white regions smaller than `min_size` pixels."""
    labeled, n = ndimage.label(binary.astype(np.uint8))
    if n == 0:
        return binary
    sizes = ndimage.sum(binary, labeled, range(1, n + 1))
    keep = np.zeros(n + 1, dtype=bool)
    keep[1:] = sizes >= min_size
    return keep[labeled]


def _parse_bool(s):
    return str(s).strip().lower() in ("1", "true", "yes", "on", "y")


def _default_expand_for_mode(mode):
    """4 px expansion for simple (compensates corner rounding on blobs);
    0 for adaptive (would fatten thin features we deliberately preserve)."""
    return 4 if mode == "simple" else 0


ASPECT_RATIO_EPSILON = 1e-6  # treat aspects within this distance as equal


def _pad_to_aspect(arr_u8, target_format):
    """Pad a uint8 mask (H,W) to the given aspect ratio with zeros.

    target_format examples: 'original' (no-op), '1:1', '16:9', '9:16'.
    Returns the (possibly padded) array. Padding is centered.

    Malformed target_format strings are logged as warnings and treated
    as 'original' (no-op).
    """
    if not target_format or target_format.strip().lower() in ("original", "auto", ""):
        return arr_u8

    s = target_format.strip()
    if ":" not in s:
        log.warning("Ignoring malformed target_format %r (expected 'W:H' or 'original')", target_format)
        return arr_u8
    try:
        rw, rh = (int(x) for x in s.split(":"))
    except ValueError:
        log.warning("Ignoring malformed target_format %r (expected integer 'W:H')", target_format)
        return arr_u8

    if rw <= 0 or rh <= 0:
        log.warning("Ignoring non-positive target_format %r", target_format)
        return arr_u8

    h, w = arr_u8.shape[:2]
    current_aspect = w / h
    target_aspect = rw / rh

    if abs(current_aspect - target_aspect) < ASPECT_RATIO_EPSILON:
        return arr_u8

    if current_aspect > target_aspect:
        # Too wide → add vertical padding
        target_h = int(round(w * rh / rw))
        target_w = w
    else:
        # Too tall → add horizontal padding
        target_w = int(round(h * rw / rh))
        target_h = h

    pad_top = (target_h - h) // 2
    pad_bottom = target_h - h - pad_top
    pad_left = (target_w - w) // 2
    pad_right = target_w - w - pad_left

    pad_width = [(pad_top, pad_bottom), (pad_left, pad_right)]
    if arr_u8.ndim == 3:
        pad_width.append((0, 0))
    return np.pad(arr_u8, pad_width, mode="constant", constant_values=0)


def _decode_mask(input_bytes):
    """Decode bytes into a 2D float32 0..1 mask. Honors alpha channel."""
    pil = Image.open(io.BytesIO(input_bytes))
    if pil.mode in ("RGBA", "LA"):
        pil = pil.split()[-1]
    else:
        pil = pil.convert("L")
    return np.asarray(pil, dtype=np.float32) / 255.0


# ─────────────────────────── core algorithm ───────────────────────────

# Tuning constants — empirically chosen on AZ Design chair masks (Tailerd
# brand, ~500x700 px). For other product types (different scale, very thin
# features < 6 px, or very large blobs > 100 px wide) these may need
# adjustment. To re-tune: run apiai-tools/eval/run_fabric_eval.py and
# compare results across a sweep of sigma/threshold values.
SIMPLE_SIGMA_MAX   = 7.5  # smooth_strength=1.0 -> sigma=7.5 (= explore sdf_s1.5, preferred for fabric)
ADAPTIVE_HIGH_SIGMA_MAX = 5.0  # smooth_strength=1.0 -> high_sigma=5 (= t4_12 winner for wood)

ADAPTIVE_LOW_SIGMA       = 1.5  # thin features blur sigma (kept low to preserve features)
ADAPTIVE_THIN_THRESHOLD  = 4    # thickness (px) below which a pixel is "thin"
ADAPTIVE_THICK_THRESHOLD = 12   # thickness (px) above which a pixel is "thick"
ADAPTIVE_PROPAGATE_RADIUS = 8   # max-filter radius for thickness propagation


def smooth_mask_core(mask_np_float, mode, smooth_strength, min_region_size,
                     fill_holes, transparent_edge_px, expand_px=None,
                     target_format="original"):
    """Smooth a single-channel mask.

    Args:
      mask_np_float:   2D float32/64 array in 0..1.
      mode:            'simple' or 'adaptive'.
      smooth_strength: 0..1. Maps to Gaussian sigma in pixels.
      min_region_size: px^2 threshold for component removal (0 = off).
      fill_holes:      bool.
      transparent_edge_px:      width in px of the semi-transparent edge band (0 = hard binary).
      expand_px:       Grow (+) / shrink (-) radius in px, -20..20. None =
                       mode-dependent default (4 for simple, 0 for adaptive).
                       Positive compensates for the corner inset that SDF blur
                       introduces; negative erodes for a tighter mask.
      target_format:   Output aspect ratio. 'original' keeps input dims;
                       otherwise pads (no crop) to e.g. '1:1', '16:9'.

    Returns:
      uint8 2D array, 0..255.

    Raises:
      ValueError: if `mode` isn't 'simple' or 'adaptive'.
    """
    if mode not in ("simple", "adaptive"):
        raise ValueError(f"Invalid mode {mode!r}; expected 'simple' or 'adaptive'")

    if expand_px is None:
        expand_px = _default_expand_for_mode(mode)
    expand_px = max(-20, min(20, int(expand_px)))

    binary = mask_np_float > 0.5

    if fill_holes:
        binary = ndimage.binary_fill_holes(binary)

    if min_region_size > 0:
        binary = _filter_small_components(binary, min_region_size)

    if not binary.any():
        return np.zeros_like(mask_np_float, dtype=np.uint8)

    # Grow (+) / shrink (-) the binary before SDF. Positive pre-dilates to
    # preserve corner coverage after SDF rounding; negative erodes to inset
    # the mask for a slightly tighter selection.
    if expand_px != 0:
        ksize = int(round(abs(expand_px) * 2 + 1))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        morph = cv2.dilate if expand_px > 0 else cv2.erode
        binary = morph(binary.astype(np.uint8), kernel).astype(bool)

    # SDF (positive inside, negative outside, in pixels)
    dist_in  = ndimage.distance_transform_edt(binary).astype(np.float32)
    dist_out = ndimage.distance_transform_edt(~binary).astype(np.float32)
    sdf = dist_in - dist_out

    if mode == "adaptive":
        # Spatially-varying blur: thin features get low sigma, thick get high.
        # high_sigma is more conservative than simple mode (5 px vs 7.5 px) so
        # thick areas don't drag thin features along during the weighted blend.
        high_sigma = max(0.5, smooth_strength * ADAPTIVE_HIGH_SIGMA_MAX)
        sdf_low  = cv2.GaussianBlur(sdf, (0, 0), sigmaX=ADAPTIVE_LOW_SIGMA)
        sdf_high = cv2.GaussianBlur(sdf, (0, 0), sigmaX=high_sigma)

        # Propagate inside-distance outward via max filter so boundary pixels
        # inherit the local "thickness" of their nearest interior point.
        # Cap radius at min(h,w)/8 so we don't overshoot on small masks.
        h, w = binary.shape
        effective_radius = min(ADAPTIVE_PROPAGATE_RADIUS, max(1, min(h, w) // 8))
        size = max(3, int(round(2 * effective_radius + 1)))
        thickness = ndimage.maximum_filter(dist_in, size=size)

        span = max(0.1, ADAPTIVE_THICK_THRESHOLD - ADAPTIVE_THIN_THRESHOLD)
        weight = np.clip(
            (thickness - ADAPTIVE_THIN_THRESHOLD) / span, 0.0, 1.0)
        sdf_final = sdf_low * (1.0 - weight) + sdf_high * weight
    else:
        # 'simple' — single-sigma SDF blur. Higher max sigma (7.5 px) since
        # there's no thin-feature constraint to worry about for blob masks.
        sigma = max(0.5, smooth_strength * SIMPLE_SIGMA_MAX)
        if sigma > 0.05:
            sdf_final = cv2.GaussianBlur(sdf, (0, 0), sigmaX=sigma)
        else:
            sdf_final = sdf

    # Threshold at 0 with optional semi-transparent ramp
    if transparent_edge_px <= 0.01:
        out = (sdf_final > 0).astype(np.float32)
    else:
        out = np.clip(0.5 + sdf_final / (2.0 * transparent_edge_px), 0.0, 1.0)

    out_u8 = (out * 255.0).astype(np.uint8)
    return _pad_to_aspect(out_u8, target_format)


# ─────────────────────── apiai.me entry point ───────────────────────

def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("No image_item provided (request body — the mask)")
        return

    try:
        mode            = (params.get("mode", "simple") or "simple").strip().lower()
        smooth_strength = float(params.get("smooth_strength", "1.0") or "1.0")
        min_region_size = int(float(params.get("min_region_size", "50") or "50"))
        fill_holes      = _parse_bool(params.get("fill_holes", "true"))
        transparent_edge_px      = float(params.get("transparent_edge_px", "1.5") or "1.5")
        target_format   = (params.get("target_format") or "original").strip()
    except ValueError as e:
        write_error(f"Invalid numeric parameter: {e}")
        return

    if mode not in ("simple", "adaptive"):
        log.info("Unknown mode %r; falling back to 'simple'", mode)
        mode = "simple"

    # expand_px default depends on mode, so resolve after mode is settled
    try:
        expand_raw = params.get("expand_px", "").strip()
        expand_px = int(float(expand_raw)) if expand_raw else _default_expand_for_mode(mode)
    except ValueError as e:
        write_error(f"Invalid expand_px: {e}")
        return

    smooth_strength = max(0.0, min(1.0, smooth_strength))
    min_region_size = max(0, min_region_size)
    transparent_edge_px      = max(0.0, min(10.0, transparent_edge_px))
    expand_px       = max(-20, min(20, expand_px))

    try:
        mask_np = _decode_mask(input_bytes)
    except Exception as e:
        write_error(f"Could not open mask image: {e}")
        return

    if mask_np.max() < 1e-3:
        write_error("Input mask is entirely black (no region selected)")
        return

    out_u8 = smooth_mask_core(mask_np, mode, smooth_strength,
                              min_region_size, fill_holes, transparent_edge_px,
                              expand_px=expand_px, target_format=target_format)
    result = Image.fromarray(out_u8, mode="L")

    # Always output PNG. Mask pixels need exact values (0/255 + AA edges);
    # JPEG's lossy compression would corrupt them.
    buf = io.BytesIO()
    result.save(buf, format="PNG", optimize=True)
    out_ct = "image/png"

    log.debug("smooth_mask done: shape=%s, mode=%s, smooth=%.2f, fill=%s, min_size=%d, aa=%.2f, expand=%d",
              out_u8.shape, mode, smooth_strength, fill_holes, min_region_size, transparent_edge_px, expand_px)
    write_output(buf.getvalue(), out_ct)


# ─────────────────────── local CLI entry point ───────────────────────

def run_local_cli():
    """File-based CLI for local testing without apiai.me runtime."""
    import argparse
    p = argparse.ArgumentParser(
        description="Smooth a SAM-style binary mask (local CLI mode).")
    p.add_argument("input", help="Input mask image path")
    p.add_argument("output", help="Output mask image path")
    p.add_argument("--mode", choices=["simple", "adaptive"], default="simple",
                   help="Smoothing mode (default 'simple'). Use 'adaptive' "
                        "for masks with mixed thin/thick features.")
    p.add_argument("--smooth-strength", type=float, default=1.0,
                   help="0..1 (default 1.0)")
    p.add_argument("--min-region-size", type=int, default=50,
                   help="px^2 speckle filter (default 50; 0 to disable)")
    p.add_argument("--fill-holes", default="true",
                   help="true/false (default true)")
    p.add_argument("--transparent-edge-px", type=float, default=1.5,
                   help="width in px of the semi-transparent edge band (default 1.5; 0 = hard binary)")
    p.add_argument("--expand-px", type=int, default=None,
                   help="grow (+) / shrink (-) radius, -20..20 (default 4 for simple, "
                        "0 for adaptive). Positive compensates corner-inset from SDF "
                        "blur; negative erodes for a tighter mask.")
    p.add_argument("--target-format", default="original",
                   help="output aspect ratio: 'original' (default), '1:1', "
                        "'16:9', etc. Pads (no crop).")
    args = p.parse_args()
    if args.expand_px is None:
        args.expand_px = _default_expand_for_mode(args.mode)

    with open(args.input, "rb") as f:
        mask_np = _decode_mask(f.read())

    out_u8 = smooth_mask_core(
        mask_np,
        args.mode,
        max(0.0, min(1.0, args.smooth_strength)),
        max(0, args.min_region_size),
        _parse_bool(args.fill_holes),
        max(0.0, min(10.0, args.transparent_edge_px)),
        expand_px=max(-20, min(20, args.expand_px)),
        target_format=args.target_format,
    )
    Image.fromarray(out_u8, mode="L").save(args.output, optimize=True)
    # CLI users typically want to see what was produced — keep at INFO.
    log.info("Wrote %s (shape=%s, mode=%s, smooth=%.2f, fill=%s, min_size=%d, aa=%.2f, expand=%d)",
             args.output, out_u8.shape, args.mode,
             args.smooth_strength, args.fill_holes,
             args.min_region_size, args.transparent_edge_px, args.expand_px)


if __name__ == "__main__":
    # Local CLI when (a) script_io isn't available, or (b) positional args given
    if SCRIPT_IO_AVAILABLE and len(sys.argv) <= 1:
        main()
    else:
        run_local_cli()
