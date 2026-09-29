#!/usr/bin/env python3
"""
Mask composite — clamp generative output to the masked region.

Given:
  image_item     (request body)      - the AI-generated/refined image (from prev node)
  image_mask     (param, is_image)   - white = use generated, black = use original
  image_original (param, is_image)   - the unmodified input image

Output: pixel-perfect composite where the mask is white the generated image
shows through; everywhere else the original is restored byte-exact.

Use this AFTER a generative node (Flux Kontext, SDXL, etc.) when the model
drifts outside the edit region — wood tints, background shifts, geometry
changes — and you need the non-edited areas to stay identical to the input.

Params:
  mask_dilate_px  Expand the mask outward by this many pixels before
                  compositing. Covers geometric drift introduced by the
                  generative node (chair slightly resized, back rest
                  shifted, etc.) so no thin sliver of "original" shows
                  through where the model drew new content. (default 4)
  feather_px      Gaussian blur radius (px) on mask edges (applied AFTER
                  dilation) to soften the seam. (default 3)
"""

import io
import json
import sys
import logging

import numpy as np
from PIL import Image, ImageFilter

from script_io import read_input, write_output, write_error

try:
    from script_io import decode_param_image
except ImportError:
    import base64 as _b64
    def decode_param_image(s): return _b64.b64decode(s)

log = logging.getLogger("mask_composite")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")

PARAM_DEFS = json.loads(r"""
[
  {
    "name": "image_mask",
    "description": "Region mask: white = use generated (from prev node), black = use original. Same mask used upstream.",
    "default_value": "",
    "required": true,
    "is_image": true
  },
  {
    "name": "image_original",
    "description": "The original input image. Pixels outside the mask are taken from here so wood, background, and geometry stay byte-exact.",
    "default_value": "",
    "required": true,
    "is_image": true
  },
  {
    "name": "mask_dilate_px",
    "description": "Expand the mask outward by this many pixels before compositing. Covers geometric drift from the generative node so no sliver of original shows where the model drew new content.",
    "default_value": "4"
  },
  {
    "name": "feather_px",
    "description": "Gaussian blur radius (px) for soft mask edges. Applied AFTER dilation. Hides small alignment errors at the seam.",
    "default_value": "3"
  }
]
""")


def _decode_image_param(b64, name, mode="RGB"):
    if not b64:
        raise ValueError(f"{name} parameter is required")
    return Image.open(io.BytesIO(decode_param_image(b64))).convert(mode)


def main():
    input_bytes, content_type, params = read_input()

    if not input_bytes:
        write_error("No image_item provided (request body)")
        return

    try:
        mask_b64       = params.get("image_mask", "").strip()
        original_b64   = params.get("image_original", "").strip()
        mask_dilate_px = float(params.get("mask_dilate_px", "4") or "4")
        feather_px     = float(params.get("feather_px", "3") or "3")
    except ValueError as e:
        write_error(f"Invalid numeric parameter: {e}")
        return

    mask_dilate_px = max(0.0, min(50.0, mask_dilate_px))
    feather_px     = max(0.0, min(50.0, feather_px))

    try:
        generated = Image.open(io.BytesIO(input_bytes)).convert("RGB")
    except Exception as e:
        write_error(f"Could not open image_item: {e}")
        return

    try:
        original = _decode_image_param(original_b64, "image_original", mode="RGB")
    except Exception as e:
        write_error(f"Could not decode image_original: {e}")
        return

    # The original drives the output size — that's the canvas we want to preserve.
    W, H = original.size

    # Generative models often output at a slightly different aspect / resolution.
    if generated.size != (W, H):
        log.info("resizing generated %s -> %s", generated.size, (W, H))
        generated = generated.resize((W, H), Image.LANCZOS)

    try:
        if not mask_b64:
            raise ValueError("image_mask is required")
        mask_raw = Image.open(io.BytesIO(decode_param_image(mask_b64)))
        if mask_raw.mode in ("RGBA", "LA"):
            mask_l = mask_raw.split()[-1]
        else:
            mask_l = mask_raw.convert("L")
        if mask_l.size != (W, H):
            mask_l = mask_l.resize((W, H), Image.BILINEAR)
    except Exception as e:
        write_error(f"Could not decode image_mask: {e}")
        return

    # Dilate first (expand the "use generated" region) — covers geometry drift.
    if mask_dilate_px >= 1.0:
        ksize = int(round(mask_dilate_px)) * 2 + 1
        if ksize % 2 == 0:
            ksize += 1
        mask_l = mask_l.filter(ImageFilter.MaxFilter(ksize))

    # Feather second (soften the now-wider edge).
    if feather_px > 0.01:
        mask_l = mask_l.filter(ImageFilter.GaussianBlur(radius=feather_px))

    mask_np = np.asarray(mask_l, dtype=np.float32) / 255.0
    if mask_np.max() < 1e-3:
        write_error("image_mask is entirely black (no region selected)")
        return

    gen_np  = np.asarray(generated, dtype=np.float32)
    orig_np = np.asarray(original, dtype=np.float32)

    m3 = mask_np[..., None]
    out = gen_np * m3 + orig_np * (1.0 - m3)
    out = np.clip(out, 0, 255).astype(np.uint8)

    result = Image.fromarray(out, mode="RGB")

    fmt = "PNG"
    out_ct = "image/png"
    if content_type and "jpeg" in content_type.lower():
        fmt = "JPEG"
        out_ct = "image/jpeg"

    buf = io.BytesIO()
    if fmt == "JPEG":
        result.save(buf, format="JPEG", quality=92)
    else:
        result.save(buf, format="PNG", optimize=True)

    log.info("mask_composite done: %dx%d, feather=%.1f", W, H, feather_px)
    write_output(buf.getvalue(), out_ct)


if __name__ == "__main__":
    main()
