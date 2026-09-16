#!/usr/bin/env python3
"""
Remove Background - Deterministic background removal using flood fill.

Algorithm:
1. Detect background color from image corners (or use specified color)
2. Flood fill from edges inward, removing pixels matching background color
3. Remove small "islands" (< threshold%) of background color inside the image
4. Apply optional feathering for soft edges

Best for:
- Logos on solid white/black/colored backgrounds
- Images where corners have consistent color

Not suitable for:
- Gradient backgrounds (use AI-based removal)
- Multi-color backgrounds
- Complex scenes

Params:
  bg_color - Background color: "auto" or hex "#FFFFFF" (default: "auto")
  tolerance - Color distance for flood fill (default: "20")
  feather - Edge softness in pixels 0-3 (default: "1")
  remove_holes_threshold - Remove inner "islands" smaller than X% of image (default: "0")
"""
import io
import json
import sys
import base64
import numpy as np
from PIL import Image
from scipy import ndimage

try:
    from script_io import read_input, write_output, write_error
    HAS_SCRIPT_IO = True
except ImportError:
    HAS_SCRIPT_IO = False

PARAM_DEFS = [
    {"name": "bg_color", "description": "Background color: 'auto' or hex like '#FFFFFF'", "default_value": "auto"},
    {"name": "tolerance", "description": "Color distance for flood fill (0-255)", "default_value": "20"},
    {"name": "feather", "description": "Edge softness in pixels (0-3)", "default_value": "1"},
    {"name": "remove_holes_threshold", "description": "Remove inner islands smaller than X% of image (0 = disabled)", "default_value": "0"},
]


def sample_corners(img, sample_size=5):
    """Sample colors from all 4 corners of the image."""
    pixels = np.array(img)
    h, w = pixels.shape[:2]

    corners = []
    positions = [
        (0, 0),
        (0, w - sample_size),
        (h - sample_size, 0),
        (h - sample_size, w - sample_size)
    ]

    for y, x in positions:
        region = pixels[y:y+sample_size, x:x+sample_size, :3]
        avg_color = tuple(int(c) for c in region.mean(axis=(0, 1)))
        corners.append(avg_color)

    return corners


def colors_match(colors, tolerance=30):
    """Check if all corner colors are similar enough."""
    if not colors:
        return False, (255, 255, 255)

    avg = tuple(int(sum(c[i] for c in colors) / len(colors)) for i in range(3))

    for color in colors:
        distance = sum(abs(color[i] - avg[i]) for i in range(3))
        if distance > tolerance * 3:
            return False, avg

    return True, avg


def parse_hex_color(hex_str):
    """Parse hex color string to (r, g, b) tuple."""
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 6:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    raise ValueError(f"Invalid hex color: {hex_str}")


def flood_fill_mask(img, bg_color, tolerance):
    """Create a mask of background pixels using flood fill from edges."""
    pixels = np.array(img)
    h, w = pixels.shape[:2]

    if pixels.shape[2] == 4:
        rgb = pixels[:, :, :3]
    else:
        rgb = pixels

    diff = np.abs(rgb.astype(float) - np.array(bg_color))
    dist = diff.sum(axis=2)
    within_tolerance = dist <= (tolerance * 3)

    edge_mask = np.zeros((h, w), dtype=bool)
    edge_mask[0, :] = True
    edge_mask[-1, :] = True
    edge_mask[:, 0] = True
    edge_mask[:, -1] = True

    seed = edge_mask & within_tolerance

    # Iterative flood fill using binary dilation
    background = ndimage.binary_dilation(
        seed,
        iterations=-1,  # -1 = repeat until no change
        mask=within_tolerance
    )

    return background


def remove_inner_holes(mask, img, bg_color, tolerance, threshold_pct):
    """Find and remove inner islands of background color."""
    if threshold_pct <= 0:
        return mask, 0

    pixels = np.array(img)
    h, w = pixels.shape[:2]
    total_pixels = h * w

    if pixels.shape[2] == 4:
        rgb = pixels[:, :, :3]
    else:
        rgb = pixels

    diff = np.abs(rgb.astype(float) - np.array(bg_color))
    dist = diff.sum(axis=2)
    matches_bg = dist <= (tolerance * 3)

    # Inner candidates = matches background but NOT already in mask
    inner_candidates = matches_bg & ~mask

    if not inner_candidates.any():
        return mask, 0

    # Label connected regions
    labeled, num_features = ndimage.label(inner_candidates)

    holes_removed = 0
    updated_mask = mask.copy()

    for i in range(1, num_features + 1):
        region = (labeled == i)
        region_size = region.sum()
        region_pct = 100 * region_size / total_pixels

        # Remove if smaller than threshold
        if region_pct < threshold_pct:
            updated_mask[region] = True
            holes_removed += 1

    return updated_mask, holes_removed


def apply_feather(img, mask, feather_px):
    """Apply feathered (soft) edges to the alpha channel."""
    pixels = np.array(img)

    if feather_px <= 0:
        pixels[mask, 3] = 0
        return Image.fromarray(pixels)

    distance = ndimage.distance_transform_edt(mask)

    alpha_factor = np.clip(1 - (distance / feather_px), 0, 1)

    new_alpha = pixels[:, :, 3].astype(float)
    new_alpha[mask] = new_alpha[mask] * alpha_factor[mask]
    pixels[:, :, 3] = new_alpha.astype(np.uint8)

    return Image.fromarray(pixels)


def remove_bg(img, bg_color="auto", tolerance=20, feather=1, remove_holes_threshold=0):
    """Remove solid color background from image."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    original_size = img.size
    detected_color = None

    # Determine background color
    if bg_color == "auto":
        corners = sample_corners(img)
        matches, avg_color = colors_match(corners, tolerance=30)

        if not matches:
            raise ValueError("Corner colors don't match - cannot auto-detect background")

        detected_color = avg_color
        bg_rgb = avg_color
    else:
        bg_rgb = parse_hex_color(bg_color)

    # Create background mask using flood fill
    mask = flood_fill_mask(img, bg_rgb, tolerance)

    # Remove inner holes
    mask, holes_removed = remove_inner_holes(mask, img, bg_rgb, tolerance, remove_holes_threshold)

    # Count removed pixels
    removed_pixels = int(mask.sum())
    total_pixels = img.size[0] * img.size[1]

    # Apply feathering
    result = apply_feather(img, mask, feather)

    # Build metadata
    metadata = {
        "original_size": f"{original_size[0]}x{original_size[1]}",
        "bg_color_used": f"#{bg_rgb[0]:02x}{bg_rgb[1]:02x}{bg_rgb[2]:02x}",
        "bg_detection": "auto" if bg_color == "auto" else "manual",
        "tolerance": tolerance,
        "feather": feather,
        "remove_holes_threshold": remove_holes_threshold,
        "holes_removed": holes_removed,
        "pixels_removed_pct": round(100 * removed_pixels / total_pixels, 1)
    }

    if detected_color:
        metadata["detected_color"] = f"#{detected_color[0]:02x}{detected_color[1]:02x}{detected_color[2]:02x}"

    return result, metadata


def main():
    """Main entry point for apiai.me runtime."""
    if HAS_SCRIPT_IO:
        # apiai.me runtime
        input_bytes, content_type, params = read_input()
        if not input_bytes:
            write_error("no input image provided")
            return

        try:
            img = Image.open(io.BytesIO(input_bytes))

            bg_color = params.get("bg_color", "auto")
            tolerance = int(params.get("tolerance", "20"))
            feather = int(params.get("feather", "1"))
            remove_holes_threshold = float(params.get("remove_holes_threshold", "0"))

            # Clamp feather to valid range
            feather = max(0, min(3, feather))

            result_img, metadata = remove_bg(img, bg_color, tolerance, feather, remove_holes_threshold)

            buf = io.BytesIO()
            result_img.save(buf, format="PNG")
            write_output(buf.getvalue(), "image/png", **metadata)

        except Exception as e:
            write_error(str(e))
    else:
        # Local testing via stdin JSON
        data = json.load(sys.stdin)
        img_bytes = base64.b64decode(data["image"])
        img = Image.open(io.BytesIO(img_bytes))
        params = data.get("params", {})

        bg_color = params.get("bg_color", "auto")
        tolerance = int(params.get("tolerance", "20"))
        feather = int(params.get("feather", "1"))
        remove_holes_threshold = float(params.get("remove_holes_threshold", "0"))

        feather = max(0, min(3, feather))

        result, metadata = remove_bg(img, bg_color, tolerance, feather, remove_holes_threshold)

        buf = io.BytesIO()
        result.save(buf, format="PNG")

        output = {
            "image": base64.b64encode(buf.getvalue()).decode(),
            "content_type": "image/png",
            **metadata
        }

        json.dump(output, sys.stdout)


# ─────────────────────── local CLI entry point ───────────────────────

def run_local_cli():
    """File-based CLI for local testing without apiai.me runtime."""
    import argparse
    p = argparse.ArgumentParser(
        description="Remove solid background color from image using flood fill.")
    p.add_argument("input", help="Input image path")
    p.add_argument("output", help="Output PNG path")
    p.add_argument("--bg-color", type=str, default="auto",
                   help="Background color: 'auto' or hex '#FFFFFF' (default: auto)")
    p.add_argument("--tolerance", type=int, default=20,
                   help="Color tolerance for flood fill (default: 20)")
    p.add_argument("--feather", type=int, default=1,
                   help="Edge softness in pixels 0-3 (default: 1)")
    p.add_argument("--remove-holes", type=float, default=0,
                   help="Remove inner islands smaller than X%% of image (default: 0 = disabled)")
    args = p.parse_args()

    img = Image.open(args.input)
    feather = max(0, min(3, args.feather))

    result, metadata = remove_bg(
        img,
        bg_color=args.bg_color,
        tolerance=args.tolerance,
        feather=feather,
        remove_holes_threshold=args.remove_holes
    )

    result.save(args.output)

    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    print(f"Background color: {metadata['bg_color_used']}")
    print(f"Pixels removed: {metadata['pixels_removed_pct']}%")
    print(f"Holes removed: {metadata['holes_removed']}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # CLI arguments = local testing
        run_local_cli()
    else:
        # No arguments = apiai.me style (stdin JSON)
        main()
