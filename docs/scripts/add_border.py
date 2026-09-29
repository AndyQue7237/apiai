#!/usr/bin/env python3
"""
Add padding/border around an image with specified color.

Params:
  top - Top padding in pixels (default: "20")
  bottom - Bottom padding in pixels (default: "20")
  left - Left padding in pixels (default: "20")
  right - Right padding in pixels (default: "20")
  color - Border color as hex (#FFFFFF) or name (default: "#FFFFFF")
"""
import io
from PIL import Image, ImageColor
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "top", "description": "Top padding in pixels", "default_value": "20"},
    {"name": "bottom", "description": "Bottom padding in pixels", "default_value": "20"},
    {"name": "left", "description": "Left padding in pixels", "default_value": "20"},
    {"name": "right", "description": "Right padding in pixels", "default_value": "20"},
    {"name": "color", "description": "Border color as hex (#FFFFFF) or name", "default_value": "#FFFFFF"},
]

def main():
    input_bytes, content_type, params = read_input()
    
    if not input_bytes:
        write_error("no input image provided")
        return
    
    try:
        # Parse padding parameters
        try:
            top = int(params.get("top", "20"))
            bottom = int(params.get("bottom", "20"))
            left = int(params.get("left", "20"))
            right = int(params.get("right", "20"))
        except ValueError:
            write_error("padding values must be integers")
            return
        
        color = params.get("color", "#FFFFFF").strip()
        
        # Load image
        img = Image.open(io.BytesIO(input_bytes))
        
        # Determine if we need to preserve transparency
        has_transparency = (
            img.mode in ("RGBA", "LA") or 
            "transparency" in img.info or
            (img.mode == "P" and "transparency" in img.info)
        )
        
        # Set output mode
        if has_transparency:
            output_mode = "RGBA"
            if img.mode != "RGBA":
                img = img.convert("RGBA")
        else:
            output_mode = "RGB"
            if img.mode != "RGB":
                img = img.convert("RGB")
        
        # Parse color to match output mode
        try:
            fill = ImageColor.getcolor(color, output_mode)
        except ValueError:
            write_error(f"invalid color format: {color} (use hex like #FF0000 or color names like 'red')")
            return
        
        # Calculate new dimensions
        new_w = img.width + left + right
        new_h = img.height + top + bottom
        
        # Validate dimensions
        if new_w <= 0 or new_h <= 0:
            write_error("padding values would result in zero or negative image dimensions")
            return
        
        # Create padded image with the specified fill color
        out = Image.new(output_mode, (new_w, new_h), fill)
        
        # Paste the original image, using itself as alpha mask for RGBA images
        if output_mode == "RGBA":
            out.paste(img, (left, top), img)
        else:
            out.paste(img, (left, top))
        
        # Output result
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        write_output(buf.getvalue(), "image/png")
        
    except Exception as e:
        write_error(f"error processing image: {e}")

if __name__ == "__main__":
    main()
