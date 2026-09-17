#!/usr/bin/env python3
"""
Detect and Remove Background - Combines Grounding DINO detection with
deterministic background removal.

Algorithm:
1. Run Grounding DINO to detect emblem/shield/badge areas
2. Compute union bounding box of all detections as "protected zone"
3. Flood fill from edges to remove solid background
4. Remove small white "islands" OUTSIDE protected zone (e.g., holes in text)
5. Preserve white elements INSIDE protected zone (e.g., logo graphics)

This solves the problem of distinguishing between:
- White background that should be removed (including holes in letters)
- White design elements that should be preserved (inside emblems)

Params:
  query - DINO detection prompt (default: "emblem or shield or badge")
  box_threshold - DINO confidence threshold (default: "0.25")
  bg_color - Background color: "auto" or hex "#FFFFFF" (default: "auto")
  tolerance - Color distance for flood fill (default: "20")
  feather - Edge softness in pixels 0-3 (default: "1")
  remove_holes_threshold - Remove islands smaller than X% outside protected zone (default: "2")
"""
import io
import os
import tempfile
import replicate
from PIL import Image
import numpy as np
from scipy import ndimage
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "query", "type": "string", "description": "DINO detection prompt", "default_value": "emblem or shield or badge"},
    {"name": "box_threshold", "type": "float", "description": "DINO confidence threshold", "default_value": "0.25"},
    {"name": "bg_color", "type": "string", "description": "Background color: 'auto' or hex like '#FFFFFF'", "default_value": "auto"},
    {"name": "tolerance", "type": "int", "description": "Color distance for flood fill (0-255)", "default_value": "20"},
    {"name": "feather", "type": "int", "description": "Edge softness in pixels (0-3)", "default_value": "1"},
    {"name": "remove_holes_threshold", "type": "float", "description": "Remove islands smaller than X% outside protected zone", "default_value": "2"},
    {"name": "passthrough_on_mismatch", "type": "boolean", "description": "If true, pass through image unchanged when corner colors don't match (instead of error)", "default_value": "false"},
]


# ============== GROUNDING DINO ==============

def detect_elements(image_bytes, content_type, params):
    """Call Grounding DINO on Replicate and return all detections."""
    query = params.get("query", "emblem or shield or badge")
    box_threshold = float(params.get("box_threshold", "0.25"))

    # Write image to temp file (Replicate needs a file handle)
    ext = ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        ext = ".jpg"
    elif "webp" in content_type:
        ext = ".webp"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            output = replicate.run(
                "adirik/grounding-dino:efd10a8ddc57ea28773327e881ce95e20cc1d734c589f7dd01d2036921ed78aa",
                input={
                    "image": f,
                    "query": query,
                    "box_threshold": box_threshold,
                    "text_threshold": box_threshold,
                    "show_visualisation": False,
                },
            )
    finally:
        os.unlink(tmp_path)

    if not output or "detections" not in output:
        return []

    return output["detections"]


def compute_union_box(detections):
    """Compute the union bounding box from all detections."""
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

    return (round(min_x1), round(min_y1), round(max_x2), round(max_y2))


# ============== BACKGROUND REMOVAL ==============

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

    background = ndimage.binary_dilation(
        seed,
        iterations=-1,
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

    distance = ndimage.distance_transform_edt(mask)
    alpha_factor = np.clip(1 - (distance / feather_px), 0, 1)

    new_alpha = pixels[:, :, 3].astype(float)
    new_alpha[mask] = new_alpha[mask] * alpha_factor[mask]
    pixels[:, :, 3] = new_alpha.astype(np.uint8)

    return Image.fromarray(pixels)


def remove_bg(img, bg_color, tolerance, feather, remove_holes_threshold, protected_box, passthrough_on_mismatch=False):
    """Remove solid color background from image with protected zone."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    original_size = img.size
    detected_color = None

    # Determine background color
    if bg_color == "auto":
        corners = sample_corners(img)
        matches, avg_color = colors_match(corners, tolerance=30)

        if not matches:
            if passthrough_on_mismatch:
                # Return original image unchanged
                return img, {"passthrough": True, "reason": "corner_colors_mismatch"}
            raise ValueError("Corner colors don't match - cannot auto-detect background")

        detected_color = avg_color
        bg_rgb = avg_color
    else:
        bg_rgb = parse_hex_color(bg_color)

    # Create background mask using flood fill
    mask = flood_fill_mask(img, bg_rgb, tolerance)

    # Remove inner holes outside protected box
    mask, holes_removed = remove_inner_holes(mask, img, bg_rgb, tolerance, remove_holes_threshold, protected_box)

    # Count removed pixels
    removed_pixels = int(mask.sum())
    total_pixels = img.size[0] * img.size[1]

    # Apply feathering
    result = apply_feather(img, mask, feather)

    metadata = {
        "bg_color_used": f"#{bg_rgb[0]:02x}{bg_rgb[1]:02x}{bg_rgb[2]:02x}",
        "holes_removed": holes_removed,
        "pixels_removed_pct": round(100 * removed_pixels / total_pixels, 1)
    }

    if detected_color:
        metadata["detected_color"] = f"#{detected_color[0]:02x}{detected_color[1]:02x}{detected_color[2]:02x}"

    return result, metadata


# ============== MAIN ==============

def main():
    img_bytes, content_type, params = read_input()
    if not content_type:
        content_type = "image/png"
    if not img_bytes:
        write_error("no input image provided")
        return

    step = "initialization"
    try:
        # Step 1: Detect elements with Grounding DINO
        step = "DINO detection"
        detections = detect_elements(img_bytes, content_type, params)

        # Step 2: Compute protected zone (union of all detections)
        step = "computing protected zone"
        protected_box = compute_union_box(detections)

        # Step 3: Load and prepare image
        step = "loading image"
        img = Image.open(io.BytesIO(img_bytes))
        if img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGBA")

        # Step 4: Remove background with protection
        step = "removing background"
        bg_color = params.get("bg_color", "auto")
        tolerance = int(params.get("tolerance", "20"))
        feather = int(params.get("feather", "1"))
        feather = max(0, min(3, feather))
        remove_holes_threshold = float(params.get("remove_holes_threshold", "2"))
        passthrough_on_mismatch = str(params.get("passthrough_on_mismatch", "false")).lower() == "true"

        result_img, bg_metadata = remove_bg(
            img, bg_color, tolerance, feather, remove_holes_threshold, protected_box, passthrough_on_mismatch
        )

        # Step 5: Encode result
        step = "encoding output"
        buf = io.BytesIO()
        result_img.save(buf, format="PNG")

        # Build output metadata
        output_meta = {
            "original_size": f"{img.width}x{img.height}",
            "detections_count": len(detections),
            **bg_metadata
        }

        if protected_box:
            output_meta["protected_box"] = list(protected_box)

        write_output(buf.getvalue(), "image/png", **output_meta)

    except Exception as e:
        write_error(f"Error during {step}: {str(e)}")


if __name__ == "__main__":
    main()
