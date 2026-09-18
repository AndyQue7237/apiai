#!/usr/bin/env python3
"""
Resize image to fit within size constraints.

Supports two types of limits:
- max_pixels: Total pixels (width × height) - for GPU/processing limits
- max_bytes: File size in bytes - for web upload limits

Resizes down proportionally to fit constraints, preserving aspect ratio.
If both are set, resizes to satisfy BOTH constraints.

Use cases:
- Prepare images for upscaler (GPU memory limit ~2MP)
- Optimize images for web upload (max file size)
- Ensure images fit processing pipelines

Params:
  max_pixels - Maximum total pixels, 0 = no limit (default: 0)
  max_bytes  - Maximum file size in bytes, 0 = no limit (default: 0)
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
        "name": "max_pixels",
        "type": "int",
        "description": "Maximum total pixels (width × height). Leave empty for no limit. Use 2000000 for Real-ESRGAN GPU limit.",
        "default_value": "",
    },
    {
        "name": "max_bytes",
        "type": "int",
        "description": "Maximum file size in bytes. Leave empty for no limit. Use 1048576 for 1MB, 5242880 for 5MB.",
        "default_value": "",
    },
]

JPEG_QUALITY = 85  # Industry standard "high quality" - visually identical to 100, ~50% smaller


def get_file_size(img):
    """Get approximate file size of image as PNG or JPEG."""
    buf = io.BytesIO()
    if img.mode == "RGBA":
        img.save(buf, format="PNG")
    else:
        img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.tell()


def resize_for_pixels(img, max_pixels):
    """Resize image to fit within max_pixels."""
    width, height = img.size
    total_pixels = width * height

    if total_pixels <= max_pixels:
        return img, False

    scale = (max_pixels / total_pixels) ** 0.5
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))

    # Ensure we don't exceed due to rounding
    while new_width * new_height > max_pixels and new_width > 1 and new_height > 1:
        new_width -= 1
        new_height = max(1, int(new_width * height / width))

    return img.resize((new_width, new_height), Image.LANCZOS), True


def resize_for_bytes(img, max_bytes):
    """Resize image to fit within max_bytes file size."""
    current_size = get_file_size(img)

    if current_size <= max_bytes:
        return img, False

    # Binary search for the right scale
    width, height = img.size
    low, high = 0.1, 1.0
    best_img = img
    resized = False

    for _ in range(10):  # Max 10 iterations
        scale = (low + high) / 2
        new_width = int(width * scale)
        new_height = int(height * scale)

        if new_width < 10 or new_height < 10:
            break

        test_img = img.resize((new_width, new_height), Image.LANCZOS)
        test_size = get_file_size(test_img)

        if test_size <= max_bytes:
            best_img = test_img
            resized = True
            low = scale  # Try larger
        else:
            high = scale  # Try smaller

    return best_img, resized


def resize_image(img, max_pixels=0, max_bytes=0):
    """
    Resize image to fit within constraints.

    Args:
        img: PIL Image object
        max_pixels: Maximum total pixels (0 = no limit)
        max_bytes: Maximum file size in bytes (0 = no limit)

    Returns:
        tuple: (result_img, metadata)
    """
    original_width, original_height = img.size
    original_pixels = original_width * original_height
    original_bytes = get_file_size(img)

    metadata = {
        "original_width": original_width,
        "original_height": original_height,
        "original_pixels": original_pixels,
        "original_bytes": original_bytes,
        "max_pixels": max_pixels,
        "max_bytes": max_bytes,
    }

    result = img
    resized_for_pixels = False
    resized_for_bytes = False

    # First, resize for pixels if needed
    if max_pixels > 0:
        result, resized_for_pixels = resize_for_pixels(result, max_pixels)

    # Then, resize for bytes if needed
    if max_bytes > 0:
        result, resized_for_bytes = resize_for_bytes(result, max_bytes)

    resized = resized_for_pixels or resized_for_bytes

    if resized:
        new_width, new_height = result.size
        metadata["resized"] = True
        reasons = []
        if resized_for_pixels:
            reasons.append("pixels")
        if resized_for_bytes:
            reasons.append("bytes")
        metadata["resized_for"] = ", ".join(reasons)
        metadata["new_width"] = new_width
        metadata["new_height"] = new_height
        metadata["new_pixels"] = new_width * new_height
        metadata["new_bytes"] = get_file_size(result)
    else:
        metadata["resized"] = False

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

            # Store original format BEFORE exif_transpose (clears .format)
            original_format = img.format

            # Handle EXIF rotation (important for JPEG)
            img = ImageOps.exif_transpose(img)

            if img.mode not in ("RGBA", "RGB"):
                img = img.convert("RGBA")

            max_pixels = int(params.get("max_pixels") or 0)
            max_bytes = int(params.get("max_bytes") or 0)

            result_img, metadata = resize_image(img, max_pixels, max_bytes)

            # Preserve format: RGBA requires PNG, else prefer original format
            if result_img.mode == "RGBA":
                out_format = "PNG"
            elif original_format in ("JPEG", "JPG"):
                out_format = "JPEG"
            elif content_type and "jpeg" in content_type.lower():
                out_format = "JPEG"
            else:
                out_format = "PNG"
            buf = io.BytesIO()
            if out_format == "PNG":
                result_img.save(buf, format="PNG")
            else:
                result_img.save(buf, format="JPEG", quality=JPEG_QUALITY)

            out_content_type = "image/png" if out_format == "PNG" else "image/jpeg"
            write_output(buf.getvalue(), out_content_type, **metadata)

        except Exception as e:
            write_error(f"Error: {str(e)}")
    else:
        # Local CLI mode
        import argparse
        parser = argparse.ArgumentParser(description="Resize image to fit constraints")
        parser.add_argument("input", help="Input image path")
        parser.add_argument("-o", "--output", help="Output image path")
        parser.add_argument("--max-pixels", type=int, default=0, help="Max pixels (0 = no limit)")
        parser.add_argument("--max-bytes", type=int, default=0, help="Max bytes (0 = no limit)")
        parser.add_argument("--max-mb", type=float, default=0, help="Max megabytes (convenience for --max-bytes)")
        args = parser.parse_args()

        max_bytes = args.max_bytes
        if args.max_mb > 0:
            max_bytes = int(args.max_mb * 1024 * 1024)

        img = Image.open(args.input)
        img = ImageOps.exif_transpose(img)
        result, metadata = resize_image(img, args.max_pixels, max_bytes)

        print(f"Original: {metadata['original_width']}×{metadata['original_height']} "
              f"({metadata['original_pixels']:,} px, {metadata['original_bytes']:,} bytes)")

        if metadata["resized"]:
            print(f"Resized:  {metadata['new_width']}×{metadata['new_height']} "
                  f"({metadata['new_pixels']:,} px, {metadata['new_bytes']:,} bytes)")
            print(f"Reason:   {metadata['resized_for']}")
        else:
            print("No resize needed")

        if args.output:
            if result.mode == "RGBA":
                result.save(args.output, format="PNG")
            else:
                result.save(args.output, format="JPEG", quality=JPEG_QUALITY)
            print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
