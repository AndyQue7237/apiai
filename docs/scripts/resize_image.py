#!/usr/bin/env python3
"""
Resize image to specific dimensions with fit modes.

Supports three fit modes:
- contain: Fit within dimensions, preserve aspect ratio (may have empty space)
- cover: Fill dimensions, preserve aspect ratio (may crop)
- stretch: Exact dimensions, ignore aspect ratio (may distort)

If only width or height is provided, the other is calculated to preserve aspect ratio.

Params:
  width  - Target width in pixels, 0 = calculate from height (default: 0)
  height - Target height in pixels, 0 = calculate from width (default: 0)
  fit    - Fit mode: contain, cover, or stretch (default: contain)
"""
import sys
import json
import base64
import io
from PIL import Image, ImageOps

try:
    from script_io import read_input, write_output, write_error
    HAS_SCRIPT_IO = True
except ImportError:
    HAS_SCRIPT_IO = False

PARAM_DEFS = [
    {
        "name": "width",
        "type": "int",
        "description": "Target width in pixels. 0 = calculate from height to preserve aspect ratio.",
        "default_value": "0",
    },
    {
        "name": "height",
        "type": "int",
        "description": "Target height in pixels. 0 = calculate from width to preserve aspect ratio.",
        "default_value": "0",
    },
    {
        "name": "fit",
        "type": "string",
        "description": "Fit mode: 'contain' (fit within), 'cover' (fill, may crop), 'stretch' (exact size, may distort).",
        "default_value": "contain",
        "allowed_values": "contain, cover, stretch",
    },
]


def resize_image(img, width=None, height=None, fit="contain"):
    """
    Resize image to target dimensions.

    Args:
        img: PIL Image object
        width: Target width (None = calculate from height)
        height: Target height (None = calculate from width)
        fit: 'contain', 'cover', or 'stretch'

    Returns:
        tuple: (result_img, metadata)
    """
    orig_w, orig_h = img.size

    metadata = {
        "original_width": orig_w,
        "original_height": orig_h,
        "fit_mode": fit,
    }

    # Handle case where neither dimension is provided
    if not width and not height:
        metadata["resized"] = False
        return img, metadata

    # Calculate missing dimension to preserve aspect ratio
    if width and not height:
        height = max(1, int((width / orig_w) * orig_h))
    elif height and not width:
        width = max(1, int((height / orig_h) * orig_w))

    # Ensure dimensions are at least 1
    width = max(1, width)
    height = max(1, height)

    metadata["target_width"] = width
    metadata["target_height"] = height

    # Apply fit mode
    if fit == "stretch":
        # Exact size, may distort
        result = img.resize((width, height), Image.LANCZOS)

    elif fit == "cover":
        # Fill target, preserve aspect ratio, crop excess
        scale_w = width / orig_w
        scale_h = height / orig_h
        scale = max(scale_w, scale_h)

        new_w = max(1, int(orig_w * scale))
        new_h = max(1, int(orig_h * scale))

        # Resize to cover
        result = img.resize((new_w, new_h), Image.LANCZOS)

        # Crop to exact target size (center crop)
        left = (new_w - width) // 2
        top = (new_h - height) // 2
        result = result.crop((left, top, left + width, top + height))

    else:  # contain (default)
        # Fit within target, preserve aspect ratio
        result = img.copy()
        result.thumbnail((width, height), Image.LANCZOS)

    out_w, out_h = result.size
    metadata["resized"] = True
    metadata["new_width"] = out_w
    metadata["new_height"] = out_h

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

            # Handle EXIF rotation (important for JPEG)
            img = ImageOps.exif_transpose(img)

            # Store original format for output
            original_format = img.format  # e.g., "JPEG", "PNG"

            if img.mode not in ("RGBA", "RGB"):
                img = img.convert("RGBA")

            # Parse parameters
            width = int(params.get("width", "0")) or None
            height = int(params.get("height", "0")) or None
            fit = params.get("fit", "contain").lower()

            # Validate fit mode
            if fit not in ("contain", "cover", "stretch"):
                fit = "contain"

            result_img, metadata = resize_image(img, width, height, fit)

            # Determine output format
            # Priority: 1) RGBA requires PNG, 2) original format, 3) content_type, 4) PNG fallback
            if result_img.mode == "RGBA":
                out_format = "PNG"
            elif original_format in ("JPEG", "JPG"):
                out_format = "JPEG"
            elif content_type and "jpeg" in content_type.lower():
                out_format = "JPEG"
            else:
                out_format = "PNG"

            buf = io.BytesIO()
            if out_format == "JPEG":
                # Convert to RGB for JPEG (no alpha)
                if result_img.mode == "RGBA":
                    result_img = result_img.convert("RGB")
                result_img.save(buf, format="JPEG", quality=85)
                out_content_type = "image/jpeg"
            else:
                result_img.save(buf, format="PNG")
                out_content_type = "image/png"

            write_output(buf.getvalue(), out_content_type, **metadata)

        except Exception as e:
            write_error(f"Error: {str(e)}")
    else:
        # Local CLI mode
        import argparse
        parser = argparse.ArgumentParser(description="Resize image to specific dimensions")
        parser.add_argument("input", help="Input image path")
        parser.add_argument("-o", "--output", help="Output image path")
        parser.add_argument("--width", type=int, default=0, help="Target width (0 = auto)")
        parser.add_argument("--height", type=int, default=0, help="Target height (0 = auto)")
        parser.add_argument("--fit", choices=["contain", "cover", "stretch"], default="contain",
                            help="Fit mode (default: contain)")
        args = parser.parse_args()

        img = Image.open(args.input)
        img = ImageOps.exif_transpose(img)

        width = args.width or None
        height = args.height or None

        result, metadata = resize_image(img, width, height, args.fit)

        print(f"Original: {metadata['original_width']}×{metadata['original_height']}")
        if metadata.get("resized"):
            print(f"Resized:  {metadata['new_width']}×{metadata['new_height']} (fit={metadata['fit_mode']})")
        else:
            print("No resize (no dimensions specified)")

        if args.output:
            result.save(args.output)
            print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
