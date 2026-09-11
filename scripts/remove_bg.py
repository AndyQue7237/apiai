#!/usr/bin/env python3
"""
Remove Background - Deterministic background removal using flood fill.

Algorithm:
1. Detect background color from image corners (or use specified color)
2. Flood fill from edges inward, removing pixels matching background color
3. If Grounding DINO detections provided, compute union bounding box as "protected zone"
4. Remove small white "islands" (< threshold%) that are OUTSIDE the protected zone
5. Apply optional feathering for soft edges

Use with Grounding DINO: Run DINO first with query "emblem or shield or badge",
then pass detections to this script to protect logo elements while removing
background holes in text areas.

Params:
  bg_color - Background color: "auto" or hex "#FFFFFF" (default: "auto")
  tolerance - Color distance for flood fill (default: "20")
  feather - Edge softness in pixels 0-3 (default: "1")
  remove_holes_threshold - Remove inner "islands" smaller than X% of image (default: "2")
  detections - JSON array from Grounding DINO with bounding boxes to protect (optional)
"""
import io
import json
from PIL import Image
import numpy as np
from scipy import ndimage
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "bg_color", "description": "Background color: 'auto' or hex like '#FFFFFF'", "default_value": "auto"},
    {"name": "tolerance", "description": "Color distance for flood fill (0-255)", "default_value": "20"},
    {"name": "feather", "description": "Edge softness in pixels (0-3)", "default_value": "1"},
    {"name": "remove_holes_threshold", "description": "Remove inner islands smaller than X% of image", "default_value": "2"},
    {"name": "detections", "description": "JSON array from Grounding DINO with bboxes to protect", "default_value": ""},
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


def compute_union_box(detections):
    """Compute the union bounding box from Grounding DINO detections."""
    if not detections:
        return None

    min_x1 = float('inf')
    min_y1 = float('inf')
    max_x2 = float('-inf')
    max_y2 = float('-inf')

    for det in detections:
        bbox = det.get("bbox", [])
        if len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            min_x1 = min(min_x1, x1)
            min_y1 = min(min_y1, y1)
            max_x2 = max(max_x2, x2)
            max_y2 = max(max_y2, y2)

    if min_x1 == float('inf'):
        return None

    return (int(min_x1), int(min_y1), int(max_x2), int(max_y2))


def is_outside_box(region_coords, protected_box):
    """Check if a region is completely outside the protected box."""
    if protected_box is None:
        return True

    x1, y1, x2, y2 = protected_box

    ys = region_coords[:, 0]
    xs = region_coords[:, 1]

    region_min_x = xs.min()
    region_max_x = xs.max()
    region_min_y = ys.min()
    region_max_y = ys.max()

    # No overlap = outside
    if region_max_x < x1 or region_min_x > x2:
        return True
    if region_max_y < y1 or region_min_y > y2:
        return True

    return False


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


def remove_inner_holes(mask, img, bg_color, tolerance, threshold_pct, protected_box=None):
    """Find and remove inner islands of background color outside protected box."""
    if threshold_pct <= 0 and protected_box is None:
        return mask, 0

    effective_threshold = threshold_pct if threshold_pct > 0 else 100

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

    inner_candidates = matches_bg & ~mask

    if not inner_candidates.any():
        return mask, 0

    labeled, num_features = ndimage.label(inner_candidates)

    holes_removed = 0
    updated_mask = mask.copy()

    for i in range(1, num_features + 1):
        region = (labeled == i)
        region_size = region.sum()
        region_pct = 100 * region_size / total_pixels

        region_coords = np.argwhere(region)
        outside = is_outside_box(region_coords, protected_box)

        if outside and region_pct < effective_threshold:
            updated_mask[region] = True
            holes_removed += 1

    return updated_mask, holes_removed


def apply_feather(img, mask, feather_px):
    """Apply feathered (soft) edges to the alpha channel."""
    pixels = np.array(img)

    if feather_px <= 0:
        pixels[mask, 3] = 0
        return Image.fromarray(pixels)

    foreground = ~mask
    distance = ndimage.distance_transform_edt(mask)

    alpha_factor = np.clip(1 - (distance / feather_px), 0, 1)

    new_alpha = pixels[:, :, 3].astype(float)
    new_alpha[mask] = new_alpha[mask] * alpha_factor[mask]
    pixels[:, :, 3] = new_alpha.astype(np.uint8)

    return Image.fromarray(pixels)


def remove_bg(img, bg_color="auto", tolerance=20, feather=1, remove_holes_threshold=2, detections=None):
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

    # Compute protected box from Grounding DINO detections
    protected_box = compute_union_box(detections) if detections else None

    # Remove inner holes outside protected box
    mask, holes_removed = remove_inner_holes(mask, img, bg_rgb, tolerance, remove_holes_threshold, protected_box)

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

    if protected_box:
        metadata["protected_box"] = list(protected_box)

    return result, metadata


def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    try:
        img = Image.open(io.BytesIO(input_bytes))

        bg_color = params.get("bg_color", "auto")
        tolerance = int(params.get("tolerance", "20"))
        feather = int(params.get("feather", "1"))
        remove_holes_threshold = float(params.get("remove_holes_threshold", "2"))

        # Parse detections JSON if provided
        detections_str = params.get("detections", "")
        detections = None
        detections_warning = None
        if detections_str and detections_str.strip():
            try:
                detections = json.loads(detections_str)
            except json.JSONDecodeError as e:
                detections_warning = f"Invalid detections JSON, ignoring: {str(e)}"

        # Clamp feather to valid range
        feather = max(0, min(3, feather))

        result_img, metadata = remove_bg(img, bg_color, tolerance, feather, remove_holes_threshold, detections)

        if detections_warning:
            metadata["warning"] = detections_warning

        buf = io.BytesIO()
        result_img.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png", **metadata)

    except Exception as e:
        write_error(str(e))


if __name__ == "__main__":
    main()
