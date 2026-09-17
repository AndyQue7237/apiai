#!/usr/bin/env python3
"""
Prepare image for upscaling by resizing down if too large for GPU.

Real-ESRGAN on Replicate has a ~2.1MP pixel limit. This script resizes
images larger than max_pixels down to fit, preserving aspect ratio.

Use before any upscaler node to prevent GPU OOM errors.

Params:
  max_pixels - Maximum total pixels before resize (default: 2000000)
"""
import sys
import json
import base64
import io
from PIL import Image

try:
    from script_io import read_input, write_output, write_error
    HAS_SCRIPT_IO = True
except ImportError:
    HAS_SCRIPT_IO = False

PARAM_DEFS = [
    {
        "name": "max_pixels",
        "type": "int",
        "description": "Maximum total pixels (width x height) before resize. Default 2000000 for Real-ESRGAN GPU limit.",
        "default_value": "2000000",
    },
]


def prep_for_upscale(img, max_pixels=2000000):
    """
    Resize image down if it exceeds max_pixels.

    Args:
        img: PIL Image object
        max_pixels: Maximum total pixels allowed

    Returns:
        tuple: (result_img, metadata)
    """
    width, height = img.size
    total_pixels = width * height

    metadata = {
        "original_width": width,
        "original_height": height,
        "original_pixels": total_pixels,
        "max_pixels": max_pixels,
    }

    if total_pixels <= max_pixels:
        # Image is small enough, pass through unchanged
        metadata["resized"] = False
        return img, metadata

    # Calculate scale factor to fit within max_pixels
    scale = (max_pixels / total_pixels) ** 0.5
    new_width = int(width * scale)
    new_height = int(height * scale)

    # Ensure we don't exceed max_pixels due to rounding
    while new_width * new_height > max_pixels:
        new_width -= 1
        new_height = int(new_width * height / width)

    # Resize
    result = img.resize((new_width, new_height), Image.LANCZOS)

    metadata["resized"] = True
    metadata["new_width"] = new_width
    metadata["new_height"] = new_height
    metadata["new_pixels"] = new_width * new_height
    metadata["scale_factor"] = round(scale, 3)

    return result, metadata


def main():
    """Main entry point for apiai.me runtime."""
    if HAS_SCRIPT_IO:
        input_bytes, content_type, params = read_input()
        if not input_bytes:
            write_error("no input image provided")
            return

        try:
            img = Image.open(io.BytesIO(input_bytes))
            if img.mode not in ("RGBA", "RGB"):
                img = img.convert("RGBA")

            max_pixels = int(params.get("max_pixels", "2000000"))

            result_img, metadata = prep_for_upscale(img, max_pixels)

            # Preserve format
            out_format = "PNG" if img.mode == "RGBA" else "JPEG"
            buf = io.BytesIO()
            result_img.save(buf, format=out_format)

            content_type = "image/png" if out_format == "PNG" else "image/jpeg"
            write_output(buf.getvalue(), content_type, **metadata)

        except Exception as e:
            write_error(f"Error: {str(e)}")
    else:
        # Local CLI mode
        import argparse
        parser = argparse.ArgumentParser(description="Prepare image for upscaling")
        parser.add_argument("input", help="Input image path")
        parser.add_argument("-o", "--output", help="Output image path")
        parser.add_argument("--max-pixels", type=int, default=2000000, help="Max pixels")
        args = parser.parse_args()

        img = Image.open(args.input)
        result, metadata = prep_for_upscale(img, args.max_pixels)

        print(f"Original: {metadata['original_width']}x{metadata['original_height']} ({metadata['original_pixels']:,} px)")

        if metadata["resized"]:
            print(f"Resized:  {metadata['new_width']}x{metadata['new_height']} ({metadata['new_pixels']:,} px)")
            print(f"Scale:    {metadata['scale_factor']}")
        else:
            print("No resize needed")

        if args.output:
            result.save(args.output)
            print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
