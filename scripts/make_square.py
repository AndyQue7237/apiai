#!/usr/bin/env python3
"""
Make Square - Pad image to 1:1 aspect ratio

Converts any image to square format by adding padding.
Configurable background, extra padding, and positioning.

Params:
    background (optional) - "transparent" (default) or "white"
    padding (optional)    - Extra padding in pixels around image (default: 0)
    position (optional)   - "center" (default), "top", or "bottom"

Input:  Any aspect ratio image
Output: Square image (1:1) with padding

Examples:
    800x600 + padding=0   → 800x800 (centered)
    800x600 + padding=50  → 900x900 (centered with 50px extra)
    800x600 + position=top → 800x800 (logo at top)
"""
import sys
import json
import base64
import io
from PIL import Image


def process(img, params):
    """
    Make image square by adding padding.

    Args:
        img: PIL Image object
        params: Dict with optional parameters:
            - background: "transparent" or "white"
            - padding: extra pixels around image
            - position: "center", "top", or "bottom"

    Returns:
        tuple: (square_image, metadata_dict)
    """
    # Parse parameters
    bg_param = str(params.get("background", "transparent")).lower()
    padding = int(params.get("padding", "0"))
    position = str(params.get("position", "center")).lower()

    # Get original dimensions
    original_width, original_height = img.size

    # Calculate square size (larger dimension + extra padding)
    max_side = max(original_width, original_height) + (padding * 2)

    # Determine background color
    if bg_param == "white":
        background_color = (255, 255, 255, 255)
    else:
        background_color = (0, 0, 0, 0)  # Transparent

    # Ensure image has alpha channel for transparency
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # Create square canvas
    square = Image.new('RGBA', (max_side, max_side), background_color)

    # Calculate horizontal position (always centered)
    x_offset = (max_side - original_width) // 2

    # Calculate vertical position based on position parameter
    if position == "top":
        y_offset = padding
    elif position == "bottom":
        y_offset = max_side - original_height - padding
    else:  # center (default)
        y_offset = (max_side - original_height) // 2

    # Paste original image onto square canvas
    square.paste(img, (x_offset, y_offset), img)

    # Check if any changes were made
    no_changes = (
        original_width == original_height and
        padding == 0
    )

    if no_changes:
        return img, {
            "squared": False,
            "reason": "Already square with no padding requested",
            "size": f"{original_width}x{original_height}"
        }

    return square, {
        "squared": True,
        "original_size": f"{original_width}x{original_height}",
        "new_size": f"{max_side}x{max_side}",
        "background": bg_param,
        "padding": padding,
        "position": position,
        "offsets": {"x": x_offset, "y": y_offset}
    }


def main():
    """Entry point for apiai.me - reads from stdin, writes to stdout."""
    # Read input from stdin
    input_data = json.loads(sys.stdin.read())

    # Decode base64 image
    img_b64 = input_data["image"]
    img_bytes = base64.b64decode(img_b64)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

    # Get parameters
    params = input_data.get("params", {})

    # Process image
    result_img, metadata = process(img, params)

    # Encode result to base64
    buf = io.BytesIO()
    result_img.save(buf, format="PNG")

    # Write output to stdout
    print(json.dumps({
        "image": base64.b64encode(buf.getvalue()).decode(),
        "content_type": "image/png",
        "metadata": metadata
    }))


if __name__ == "__main__":
    main()
