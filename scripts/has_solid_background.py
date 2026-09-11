#!/usr/bin/env python3
"""
Check if an image has a solid (uniform) background color.

Samples the four corners of the image and compares their colors.
If all corners have similar colors, the background is considered solid
and suitable for simple flood-fill removal.

Different corner colors indicate:
- Gradient backgrounds
- Multi-color designs (e.g., esports templates)
- Complex backgrounds requiring AI removal

Outputs the image unchanged plus metadata fields for pipeline conditions.

Params:
  field           - metadata field name for the result boolean (default: "has_solid_bg")
  sample_size     - pixels to sample from each corner (default: "10")
  color_threshold - max RGB distance to consider "same color" (default: "50")
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
    {"name": "field", "description": "Metadata field name for the result boolean", "default_value": "has_solid_bg"},
    {"name": "sample_size", "description": "Pixels to sample from each corner (NxN)", "default_value": "10"},
    {"name": "color_threshold", "description": "Max RGB distance to consider same color (0-442)", "default_value": "50"},
]


def get_corner_colors(img, sample_size=10):
    """
    Get average color of each corner.

    Args:
        img: PIL Image (RGB or RGBA)
        sample_size: Size of square to sample from each corner

    Returns:
        dict: Corner names to RGB tuples
    """
    if img.mode == 'RGBA':
        # Convert to RGB, compositing on white
        rgb = Image.new('RGB', img.size, (255, 255, 255))
        rgb.paste(img, mask=img.split()[3])
        img = rgb
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    arr = np.array(img)
    h, w = arr.shape[:2]

    s = min(sample_size, h // 4, w // 4)  # Ensure sample fits

    corners = {
        "top_left": arr[:s, :s],
        "top_right": arr[:s, -s:],
        "bottom_left": arr[-s:, :s],
        "bottom_right": arr[-s:, -s:],
    }

    colors = {}
    for name, region in corners.items():
        avg_r = int(np.mean(region[:, :, 0]))
        avg_g = int(np.mean(region[:, :, 1]))
        avg_b = int(np.mean(region[:, :, 2]))
        colors[name] = (avg_r, avg_g, avg_b)

    return colors


def color_distance(c1, c2):
    """Calculate Euclidean RGB distance between two colors."""
    return np.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def check_solid_background(img, sample_size=10, threshold=50):
    """
    Check if image has a solid background color.

    Args:
        img: PIL Image
        sample_size: Pixels to sample from each corner
        threshold: Max color distance to consider "solid"

    Returns:
        tuple: (has_solid_bg: bool, metadata: dict)
    """
    colors = get_corner_colors(img, sample_size)

    # Calculate max distance between any two corners
    corner_list = list(colors.values())
    max_dist = 0

    for i, c1 in enumerate(corner_list):
        for c2 in corner_list[i + 1:]:
            dist = color_distance(c1, c2)
            max_dist = max(max_dist, dist)

    has_solid = max_dist < threshold

    # Calculate average background color (if solid)
    if has_solid:
        avg_r = int(np.mean([c[0] for c in corner_list]))
        avg_g = int(np.mean([c[1] for c in corner_list]))
        avg_b = int(np.mean([c[2] for c in corner_list]))
        bg_color = (avg_r, avg_g, avg_b)
        bg_color_hex = "#{:02x}{:02x}{:02x}".format(*bg_color)
    else:
        bg_color = None
        bg_color_hex = None

    metadata = {
        "has_solid_bg": has_solid,
        "corner_distance": round(max_dist, 1),
        "corners": colors,
        "bg_color": bg_color,
        "bg_color_hex": bg_color_hex,
    }

    return has_solid, metadata


def main():
    data = json.load(sys.stdin)
    img_bytes = base64.b64decode(data["image"])
    img = Image.open(io.BytesIO(img_bytes))
    params = data.get("params", {})

    field = params.get("field", "has_solid_bg")
    sample_size = int(params.get("sample_size", "10"))
    threshold = float(params.get("color_threshold", "50"))

    result, metadata = check_solid_background(img, sample_size, threshold)

    # Pass image through as RGBA PNG
    out = img.convert("RGBA")
    buf = io.BytesIO()
    out.save(buf, format="PNG")

    output = {
        "image": base64.b64encode(buf.getvalue()).decode(),
        "content_type": "image/png",
        field: bool(result),  # Convert numpy bool to Python bool
        "corner_distance": float(metadata["corner_distance"]),
    }

    # Add bg_color if solid
    if metadata["bg_color_hex"]:
        output["bg_color"] = metadata["bg_color_hex"]

    json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
