#!/usr/bin/env python3
"""Adds padding/margin around an image with configurable color and size.

Params:
  padding - padding size in pixels (default: "20")
  padding_percent - padding as percentage of image size, overrides padding if set (default: "")
  color - padding color as hex (#RRGGBB) or name (default: "#FFFFFF")
  mode - padding mode: uniform, horizontal, vertical (default: "uniform")
"""
import io
from PIL import Image, ImageColor
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "padding", "description": "Padding size in pixels", "default_value": "20"},
    {"name": "padding_percent", "description": "Padding as percentage of image size (overrides padding)", "default_value": ""},
    {"name": "color", "description": "Padding color as hex (#RRGGBB) or name", "default_value": "#FFFFFF"},
    {"name": "mode", "description": "Padding mode", "default_value": "uniform", "allowed_values": ["uniform", "horizontal", "vertical"]},
]


def process(img, params):
    """Add padding around the image."""
    # Parse parameters
    padding_str = params.get("padding", "20")
    padding_percent_str = params.get("padding_percent", "")
    color_str = params.get("color", "#FFFFFF")
    mode = params.get("mode", "uniform")
    
    # Calculate padding size
    if padding_percent_str:
        # Use percentage of image dimensions
        padding_percent = float(padding_percent_str)
        if mode == "horizontal":
            padding = int(img.width * padding_percent / 100)
        elif mode == "vertical":
            padding = int(img.height * padding_percent / 100)
        else:  # uniform
            padding = int(min(img.width, img.height) * padding_percent / 100)
    else:
        # Use fixed pixel value
        padding = int(padding_str)
    
    # Parse color
    try:
        color = ImageColor.getcolor(color_str, "RGBA")
    except ValueError:
        # Fallback to white if color parsing fails
        color = (255, 255, 255, 255)
    
    # Calculate padding for each side based on mode
    if mode == "horizontal":
        left = right = padding
        top = bottom = 0
    elif mode == "vertical":
        left = right = 0
        top = bottom = padding
    else:  # uniform
        left = right = top = bottom = padding
    
    # Create new image with padding
    new_width = img.width + left + right
    new_height = img.height + top + bottom
    
    # Create background with the specified color
    if img.mode == "RGBA":
        new_img = Image.new("RGBA", (new_width, new_height), color)
    else:
        # For non-RGBA images, use RGB background
        rgb_color = color[:3] if len(color) >= 3 else (255, 255, 255)
        new_img = Image.new("RGB", (new_width, new_height), rgb_color)
    
    # Paste the original image onto the new background
    new_img.paste(img, (left, top))
    
    return new_img


def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    img = Image.open(io.BytesIO(input_bytes))

    try:
        result = process(img, params)
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png")
    except Exception as e:
        write_error(str(e))


if __name__ == "__main__":
    main()
