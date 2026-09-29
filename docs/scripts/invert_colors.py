#!/usr/bin/env python3
"""Invert image colors (negative effect).

Params:
    channels - which channels to invert: all, rgb, red, green, blue (default: all)
"""

import io
from PIL import Image, ImageOps
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "channels", "description": "Which channels to invert", "default_value": "all", "allowed_values": ["all", "rgb", "red", "green", "blue"]},
]

def invert_image(img, channels):
    """Invert specified channels of the image."""
    # Preserve alpha channel if it exists
    had_alpha = img.mode in ("RGBA", "LA", "PA")
    alpha = None
    if had_alpha:
        alpha = img.split()[-1]
    
    # Convert to RGB for processing
    rgb_img = img.convert("RGB")
    
    if channels in ("all", "rgb"):
        # Invert all RGB channels
        result = ImageOps.invert(rgb_img)
    elif channels in ("red", "green", "blue"):
        # Invert single channel
        r, g, b = rgb_img.split()
        ch_map = {"red": r, "green": g, "blue": b}
        channels_list = [r, g, b]
        
        # Invert the specified channel
        if channels == "red":
            channels_list[0] = ImageOps.invert(r)
        elif channels == "green":
            channels_list[1] = ImageOps.invert(g)
        elif channels == "blue":
            channels_list[2] = ImageOps.invert(b)
        
        result = Image.merge("RGB", channels_list)
    else:
        # Invalid channel, return original
        result = rgb_img
    
    # Restore alpha if it existed
    if had_alpha:
        result = result.convert("RGBA")
        result.putalpha(alpha)
    
    return result

def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return
    
    channels = params.get("channels", "all").lower().strip()
    
    # Validate channels parameter
    valid_channels = ["all", "rgb", "red", "green", "blue"]
    if channels not in valid_channels:
        write_error(f"invalid channels parameter: {channels}. Must be one of {valid_channels}")
        return
    
    try:
        img = Image.open(io.BytesIO(input_bytes))
        result = invert_image(img, channels)
        
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png")
        
    except Exception as e:
        write_error(f"failed to process image: {str(e)}")

if __name__ == "__main__":
    main()
