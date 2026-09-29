#!/usr/bin/env python3
"""
Check whether an image has sufficient resolution (total pixels).

Outputs the image unchanged plus a metadata field set to "true" or "false".
The field name is configurable via the `field` param so it can feed directly
into a condition node.

Use case: Conditional upscaling in pipelines - only upscale low-res images.
Note: Replicate Upscaler has a limit of width * height > 2,000,000 pixels.

Params:
  field      - metadata field name to write (default: "is_high_resolution")
  max_pixels - total pixels (width x height) threshold (default: 2000000)

Examples:
  1920x1080 (2,073,600) with max_pixels=2000000 → is_high_resolution: true
  1000x1000 (1,000,000) with max_pixels=2000000 → is_high_resolution: false
"""
import io
from PIL import Image
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "field", "description": "Metadata field name to write", "default_value": "is_high_resolution"},
    {"name": "max_pixels", "description": "Total pixels (width x height) threshold", "default_value": "2000000"},
]


def check_resolution(img, max_pixels=2000000):
    width, height = img.size
    total_pixels = width * height
    is_high_res = total_pixels >= max_pixels
    return is_high_res


def main():
    img_bytes, content_type, params = read_input()
    
    if not img_bytes:
        write_error("no input image provided")
        return

    try:
        img = Image.open(io.BytesIO(img_bytes))
    except Exception as e:
        write_error(f"failed to open image: {e}")
        return

    field = params.get("field", "is_high_resolution")
    
    try:
        max_pixels = int(params.get("max_pixels", "2000000"))
    except ValueError:
        write_error("max_pixels must be a valid integer")
        return

    result = check_resolution(img, max_pixels)

    # Preserve original format if possible
    original_format = img.format or "PNG"
    if original_format.upper() in ["JPEG", "JPG"]:
        # Convert JPEG to RGB to avoid transparency issues
        out = img.convert("RGB")
        output_format = "JPEG"
        output_content_type = "image/jpeg"
    else:
        # Keep as-is or convert to RGBA for PNG
        out = img.convert("RGBA") if img.mode != "RGBA" else img
        output_format = "PNG"
        output_content_type = "image/png"

    buf = io.BytesIO()
    out.save(buf, format=output_format)

    write_output(buf.getvalue(), output_content_type, **{field: result})


if __name__ == "__main__":
    main()
