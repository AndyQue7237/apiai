#!/usr/bin/env python3
"""Convert an image to a different format (PNG, JPEG, WebP, BMP, HEIC).

iPhone HEIC files (10-bit HDR / Display P3) are decoded via pillow_heif's
open_heif() so tone-mapping to 8-bit sRGB is applied — otherwise the
output gets crushed to near-black. Other formats use PIL as usual.

Params:
    format   – target format: png, jpeg, webp, bmp, heic (default: webp)
    quality  – compression quality 1-100 for lossy formats (default: 85)
    max_size – cap long edge at N pixels (default: 2048; 0 = no resize)
"""

import io
from PIL import Image
import pillow_heif
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "format", "description": "Target format", "default_value": "webp",
     "allowed_values": ["png", "jpeg", "webp", "bmp", "heic"]},
    {"name": "quality", "description": "Compression quality 1-100 for lossy formats",
     "default_value": "85"},
    {"name": "max_size", "description": "Max long edge in pixels (0 = no resize)",
     "default_value": "2048"},
]

HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis",
               b"hevm", b"hevs", b"mif1", b"msf1")

def _is_heif(data: bytes) -> bool:
    return len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in HEIF_BRANDS

def _resize(img: Image.Image, max_edge: int) -> Image.Image:
    if max_edge <= 0:
        return img
    w, h = img.size
    if max(w, h) <= max_edge:
        return img
    if w >= h:
        new_w, new_h = max_edge, max(1, h * max_edge // w)
    else:
        new_w, new_h = max(1, w * max_edge // h), max_edge
    return img.resize((new_w, new_h), Image.LANCZOS)

def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    fmt = params.get("format", "webp").lower().strip()
    try:
        quality = max(1, min(100, int(params.get("quality", "85"))))
    except ValueError:
        write_error("quality must be a number between 1 and 100")
        return
    try:
        max_size = int(params.get("max_size", "2048"))
        max_size = max(0, max_size)
    except ValueError:
        max_size = 2048

    fmt_map = {
        "png":  ("PNG",  "image/png"),
        "jpeg": ("JPEG", "image/jpeg"),
        "webp": ("WEBP", "image/webp"),
        "bmp":  ("BMP",  "image/bmp"),
        "heic": ("HEIF", "image/heic"),  # HEIF supports alpha → skips flatten
    }

    if fmt not in fmt_map:
        write_error(f"Unsupported format '{fmt}'. Use: png, jpeg, webp, bmp, heic")
        return

    pil_fmt, mime = fmt_map[fmt]

    try:
        # HEIC: decode via pillow_heif.open_heif so HDR→8bit tone mapping
        # is applied. The PIL-plugin path skips that and produces crushed
        # blacks for iPhone HDR shots.
        if _is_heif(input_bytes):
            heif = pillow_heif.open_heif(io.BytesIO(input_bytes), convert_hdr_to_8bit=True)
            img = heif.to_pillow()
        else:
            img = Image.open(io.BytesIO(input_bytes))

        img = _resize(img, max_size)

        # JPEG/BMP don't support alpha — flatten onto white
        if pil_fmt in ("JPEG", "BMP") and img.mode in ("RGBA", "LA", "PA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                bg.paste(img, mask=img.split()[-1])
            else:
                bg.paste(img, mask=img.convert("RGBA").split()[-1])
            img = bg
        elif pil_fmt in ("JPEG", "BMP") and img.mode != "RGB":
            img = img.convert("RGB")

        buf = io.BytesIO()
        save_kwargs = {}
        if pil_fmt in ("JPEG", "WEBP", "HEIF"):
            save_kwargs["quality"] = quality
        if pil_fmt == "PNG":
            save_kwargs["optimize"] = True

        img.save(buf, format=pil_fmt, **save_kwargs)
        write_output(buf.getvalue(), mime)

    except Exception as e:
        write_error(f"Failed to convert image: {str(e)}")

if __name__ == "__main__":
    main()
