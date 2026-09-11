#!/usr/bin/env python3
"""
Smart Crop - Crop to content with configurable aspect ratio.

Finds the bounding box of non-transparent pixels, crops with margin,
then pads to specified format.

Params:
    margin (optional) - Pixels around content (default: 10)
    alpha_threshold (optional) - Min alpha to count as content (default: 10)
    format (optional) - Output aspect ratio (default: "square")
        Supported formats:
        - "square" or "1:1" - Square format
        - "original" - Keep cropped aspect ratio (no padding)
        - "16:9" - Widescreen landscape
        - "4:3" - Classic landscape
        - "3:2" - Photo landscape
        - "9:16" - Vertical (stories/reels)
        - "4:5" - Instagram portrait
        - "2:3" - Photo portrait

Input:  PNG with transparent background
Output: PNG cropped to content with margin, in specified format
"""
import sys
import json
import base64
import io
from PIL import Image


# Supported aspect ratios (width:height)
FORMATS = {
    "square": (1, 1),
    "1:1": (1, 1),
    "16:9": (16, 9),
    "4:3": (4, 3),
    "3:2": (3, 2),
    "9:16": (9, 16),
    "4:5": (4, 5),
    "2:3": (2, 3),
    "original": None,  # Special case: no aspect ratio change
}


def smart_crop(img, margin=10, alpha_threshold=10, format="square"):
    """
    Crop to content bounding box, add guaranteed margin, then pad to format.

    Args:
        img: PIL Image (RGBA)
        margin: Guaranteed pixels around content (default: 10)
        alpha_threshold: Minimum alpha value to count as content (default: 10)
        format: Output aspect ratio (default: "square")

    Returns:
        tuple: (cropped_image, metadata_dict)
    """
    # Ensure RGBA
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    original_size = img.size

    # Validate format
    format_lower = format.lower()
    if format_lower not in FORMATS:
        return img, {"cropped": False, "reason": f"Unknown format: {format}"}

    # Get bounding box using alpha threshold to ignore semi-transparent noise
    alpha = img.split()[3]  # Extract alpha channel

    # Create mask where alpha > threshold
    mask = alpha.point(lambda p: 255 if p > alpha_threshold else 0)
    bbox = mask.getbbox()

    if bbox is None:
        # No visible content found - return as-is
        return img, {"cropped": False, "reason": "No content found"}

    # Crop tight to content (no margin yet)
    x1, y1, x2, y2 = bbox
    content = img.crop((x1, y1, x2, y2))
    content_w, content_h = content.size

    # Handle "original" format - just add margin, no aspect ratio change
    if format_lower == "original":
        final_w = content_w + (margin * 2)
        final_h = content_h + (margin * 2)
        result = Image.new('RGBA', (final_w, final_h), (0, 0, 0, 0))
        result.paste(content, (margin, margin), content)

        return result, {
            "cropped": True,
            "original_size": f"{original_size[0]}x{original_size[1]}",
            "content_bbox": [x1, y1, x2, y2],
            "content_size": f"{content_w}x{content_h}",
            "final_size": f"{final_w}x{final_h}",
            "margin": margin,
            "alpha_threshold": alpha_threshold,
            "format": format_lower
        }

    # Get target aspect ratio
    ratio_w, ratio_h = FORMATS[format_lower]
    target_ratio = ratio_w / ratio_h

    # Content with margin
    content_with_margin_w = content_w + (margin * 2)
    content_with_margin_h = content_h + (margin * 2)
    content_ratio = content_with_margin_w / content_with_margin_h

    # Calculate final dimensions to fit content while matching target ratio
    if content_ratio > target_ratio:
        # Content is wider than target - width determines size
        final_w = content_with_margin_w
        final_h = int(final_w / target_ratio)
    else:
        # Content is taller than target - height determines size
        final_h = content_with_margin_h
        final_w = int(final_h * target_ratio)

    # Create canvas with transparent background
    result = Image.new('RGBA', (final_w, final_h), (0, 0, 0, 0))

    # Center content
    x_offset = (final_w - content_w) // 2
    y_offset = (final_h - content_h) // 2
    result.paste(content, (x_offset, y_offset), content)

    return result, {
        "cropped": True,
        "original_size": f"{original_size[0]}x{original_size[1]}",
        "content_bbox": [x1, y1, x2, y2],
        "content_size": f"{content_w}x{content_h}",
        "final_size": f"{final_w}x{final_h}",
        "margin": margin,
        "alpha_threshold": alpha_threshold,
        "format": format_lower
    }


def main():
    data = json.load(sys.stdin)
    img_bytes = base64.b64decode(data["image"])
    img = Image.open(io.BytesIO(img_bytes))
    params = data.get("params", {})

    margin = int(params.get("margin", "10"))
    alpha_threshold = int(params.get("alpha_threshold", "10"))
    format = params.get("format", "square")

    result_img, metadata = smart_crop(img, margin, alpha_threshold, format)

    buf = io.BytesIO()
    result_img.save(buf, format="PNG")

    output = {
        "image": base64.b64encode(buf.getvalue()).decode(),
        "content_type": "image/png",
    }
    output.update(metadata)  # Flat on root level, not nested
    json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
