#!/usr/bin/env python3
"""Apply sepia or custom duotone tint to an image.

Params:
    color - hex color for the tint (default: #704214 = classic sepia)
    intensity - tint strength 0-100 (default: 80)
"""

import io
from PIL import Image, ImageOps
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "color", "description": "Hex color for the tint", "default_value": "#704214"},
    {"name": "intensity", "description": "Tint strength 0-100", "default_value": "80"},
]

def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    try:
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        raise ValueError(f"Invalid hex color: #{h}")

def apply_tint(img, color, intensity):
    """Apply tint effect to image."""
    # Store alpha channel if present
    has_alpha = img.mode in ("RGBA", "LA", "PA")
    alpha = img.split()[-1] if has_alpha else None
    
    # Convert to greyscale
    grey = ImageOps.grayscale(img).convert("RGB")
    
    # Parse tint color
    r, g, b = hex_to_rgb(color)
    
    # Create tint overlay
    tint = Image.new("RGB", img.size, (r, g, b))
    
    # Blend greyscale with tint
    blend_factor = intensity / 200.0  # Scale to 0-0.5 range for subtle effect
    result = Image.blend(grey, tint, blend_factor)
    
    # Restore alpha if present
    if alpha:
        result.putalpha(alpha)
    
    return result

def main():
    input_bytes, content_type, params = read_input()
    
    if not input_bytes:
        write_error("No input image provided")
        return
    
    # Parse parameters
    color = params.get("color", "#704214").strip()
    try:
        intensity = int(params.get("intensity", "80"))
        intensity = max(0, min(100, intensity))
    except ValueError:
        write_error("Invalid intensity value - must be a number 0-100")
        return
    
    try:
        # Load and process image
        img = Image.open(io.BytesIO(input_bytes))
        result = apply_tint(img, color, intensity)
        
        # Output as PNG
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png")
        
    except ValueError as e:
        write_error(str(e))
    except Exception as e:
        write_error(f"Failed to process image: {str(e)}")

if __name__ == "__main__":
    main()
