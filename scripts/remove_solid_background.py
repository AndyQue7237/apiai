#!/usr/bin/env python3
"""
Remove solid background color using flood-fill from edges.

Simple, fast background removal for images with uniform background color.
Uses flood-fill starting from image edges to identify and remove background.

Best for:
- Logos on solid white/black/colored backgrounds
- Images where corners have consistent color

Not suitable for:
- Gradient backgrounds (use AI-based removal)
- Multi-color backgrounds
- Complex scenes

Params:
  bg_color   - Background color: "auto" (detect from corners) or hex "#FFFFFF" (default: "auto")
  tolerance  - Color distance for flood fill 0-100 (default: "20")
  feather    - Edge softness in pixels 0-5 (default: "1")
"""
import sys
import json
import base64
import io
import numpy as np
from PIL import Image
from scipy import ndimage

try:
    from script_io import read_input, write_output, write_error
except ImportError:
    # Local testing fallback
    pass

PARAM_DEFS = [
    {"name": "bg_color", "description": "Background color: 'auto' or hex like '#FFFFFF'", "default_value": "auto"},
    {"name": "tolerance", "description": "Color distance for flood fill (0-100)", "default_value": "20"},
    {"name": "feather", "description": "Edge softness in pixels (0-5)", "default_value": "1"},
]


def sample_corners(img, sample_size=10):
    """Sample colors from all 4 corners of the image."""
    pixels = np.array(img)
    h, w = pixels.shape[:2]

    s = min(sample_size, h // 4, w // 4)

    corners = []
    positions = [
        (0, 0),
        (0, w - s),
        (h - s, 0),
        (h - s, w - s)
    ]

    for y, x in positions:
        region = pixels[y:y+s, x:x+s, :3]
        avg_color = tuple(int(c) for c in region.mean(axis=(0, 1)))
        corners.append(avg_color)

    return corners


def detect_bg_color(img):
    """Detect background color from corners."""
    corners = sample_corners(img)

    # Average all corners
    avg = tuple(int(sum(c[i] for c in corners) / len(corners)) for i in range(3))
    return avg


def parse_hex_color(hex_str):
    """Parse hex color string to (r, g, b) tuple."""
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 6:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    raise ValueError(f"Invalid hex color: {hex_str}")


def flood_fill_from_edges(img, bg_color, tolerance):
    """Create mask of background pixels using flood fill from edges."""
    pixels = np.array(img)
    h, w = pixels.shape[:2]

    if pixels.shape[2] == 4:
        rgb = pixels[:, :, :3]
    else:
        rgb = pixels

    # Calculate color distance
    diff = np.abs(rgb.astype(float) - np.array(bg_color))
    dist = diff.sum(axis=2)
    within_tolerance = dist <= (tolerance * 3)

    # Create edge seed mask
    edge_mask = np.zeros((h, w), dtype=bool)
    edge_mask[0, :] = True
    edge_mask[-1, :] = True
    edge_mask[:, 0] = True
    edge_mask[:, -1] = True

    # Seed = edge pixels that match background color
    seed = edge_mask & within_tolerance

    # Flood fill from seed
    background = ndimage.binary_dilation(
        seed,
        iterations=-1,
        mask=within_tolerance
    )

    return background


def apply_feather(mask, feather_px):
    """Apply feathered (soft) edges to the mask."""
    if feather_px <= 0:
        return mask.astype(np.uint8) * 255

    # Distance transform for soft edges
    foreground = ~mask
    dist = ndimage.distance_transform_edt(foreground)

    # Create alpha gradient at edges
    alpha = np.clip(dist / feather_px, 0, 1)
    alpha = (alpha * 255).astype(np.uint8)

    return alpha


def remove_background(img, bg_color="auto", tolerance=20, feather=1):
    """
    Remove solid background from image.

    Args:
        img: PIL Image (RGB or RGBA)
        bg_color: "auto" or (r, g, b) tuple or "#RRGGBB" hex
        tolerance: Color tolerance for flood fill
        feather: Edge softness in pixels

    Returns:
        tuple: (RGBA image, metadata dict)
    """
    # Ensure RGB for processing
    if img.mode == 'RGBA':
        rgb = Image.new('RGB', img.size, (255, 255, 255))
        rgb.paste(img, mask=img.split()[3])
        img_rgb = rgb
    else:
        img_rgb = img.convert('RGB')

    # Detect or parse background color
    if bg_color == "auto":
        bg_color_rgb = detect_bg_color(img_rgb)
    elif isinstance(bg_color, str) and bg_color.startswith("#"):
        bg_color_rgb = parse_hex_color(bg_color)
    else:
        bg_color_rgb = bg_color

    # Flood fill to find background
    bg_mask = flood_fill_from_edges(img_rgb, bg_color_rgb, tolerance)

    # Create alpha channel
    alpha = apply_feather(bg_mask, feather)

    # Compose final RGBA image
    result = img_rgb.convert('RGBA')
    result.putalpha(Image.fromarray(alpha))

    # Calculate stats
    total_pixels = img.size[0] * img.size[1]
    removed_pixels = np.sum(bg_mask)
    removed_pct = (removed_pixels / total_pixels) * 100

    metadata = {
        "bg_color": "#{:02x}{:02x}{:02x}".format(*bg_color_rgb),
        "removed_pct": round(removed_pct, 1),
        "tolerance": tolerance,
        "feather": feather,
    }

    return result, metadata


def main():
    data = json.load(sys.stdin)
    img_bytes = base64.b64decode(data["image"])
    img = Image.open(io.BytesIO(img_bytes))
    params = data.get("params", {})

    bg_color = params.get("bg_color", "auto")
    tolerance = int(params.get("tolerance", "20"))
    feather = int(params.get("feather", "1"))

    result, metadata = remove_background(img, bg_color, tolerance, feather)

    # Output as PNG
    buf = io.BytesIO()
    result.save(buf, format="PNG")

    output = {
        "image": base64.b64encode(buf.getvalue()).decode(),
        "content_type": "image/png",
        "bg_color_detected": metadata["bg_color"],
        "bg_removed_pct": metadata["removed_pct"],
    }

    json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
