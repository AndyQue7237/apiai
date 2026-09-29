#!/usr/bin/env python3
"""
Fabric / material mockup without AI.

Given:
  image_item    (request body)      - product photo (chair, pillow, sofa, ...)
  image_mask    (param, is_image)   - white = region to replace, black = keep
  image_inpaint (param, is_image)   - fabric / material swatch (will be tiled)

Pipeline (Tier 1 realism):
  1. Brick-offset tile fabric across the masked region.
  2. Frequency-separation lighting transfer: low-pass of item luma drives a
     per-region multiplier; fabric's high-freq detail is preserved natively
     (no need for unsharp recovery).
  3. Crease / AO pickup: high-freq negatives darken fabric in shadow valleys.
  4. LAB chroma match (a/b channels only) — keeps fabric's L untouched.
  5. Ambient pickup in LAB from a ring outside the mask.
  6. Contact shadow at mask edges.
  7. Grain matching: noise std sampled outside the mask is added inside it.
  8. Poisson seamlessClone composite (or feather fallback) for invisible edges.

Fast, deterministic, ~300-700 ms on a 2000 px image. No AI, no GPU.

Params:
  tile_scale        Tile-size multiplier. 1.0 = ~8 repeats per region.   (default 1.0)
  feather_px        Mask-edge Gaussian blur (used by feather blend).     (default 3)
  shading_strength  Lighting-transfer strength. 0.0 = flat.              (default 0.8)
  color_match       LAB a/b shift toward masked region chroma. 0..1.    (default 0.0)
  detail_boost      Legacy unsharp on shaded fabric. 0..1. Usually 0.   (default 0.0)
  ambient_pickup    Pickup ambient room chroma from outside the mask.   (default 0.25)
  contact_shadow    Edge-darkening to look tucked in. 0..1.              (default 0.3)
  crease_strength   Darken fabric in shadow valleys (high-freq AO).      (default 0.4)
  grain_match       Match photographic grain inside the mask. 0..1.      (default 0.5)
  blend_mode        "poisson" (seamlessClone) or "feather".              (default poisson)

If scipy is installed, disconnected mask regions (e.g. chair seat + backrest)
are tiled and shaded independently so each region gets the right pattern + lighting.
"""

import io
import json
import sys
import logging

import cv2
import numpy as np
from PIL import Image, ImageFilter

from script_io import read_input, write_output, write_error

try:
    from script_io import decode_param_image
except ImportError:
    import base64 as _b64
    def decode_param_image(s): return _b64.b64decode(s)

log = logging.getLogger("fabric_mockup")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")

# ── Parameter definitions (picked up by admin "Scan Script") ──
PARAM_DEFS = json.loads(r"""
[
  {
    "name": "image_mask",
    "description": "Region mask: white = apply fabric, black = keep original. Any image format; alpha channel is honored if present.",
    "default_value": "",
    "required": true,
    "is_image": true
  },
  {
    "name": "image_inpaint",
    "description": "Fabric / material swatch to tile across the masked region. Square swatches work best.",
    "default_value": "",
    "required": true,
    "is_image": true
  },
  {
    "name": "tile_scale",
    "description": "Multiplier for fabric tile size. 1.0 = ~8 repeats across each masked region. Larger = bigger pattern.",
    "default_value": "1.0"
  },
  {
    "name": "feather_px",
    "description": "Gaussian blur radius (px) applied to mask edges for a soft blend.",
    "default_value": "3"
  },
  {
    "name": "shading_strength",
    "description": "How strongly the product's lighting is transferred onto the fabric (0.0 = flat, 1.0 = full).",
    "default_value": "0.8"
  },
  {
    "name": "color_match",
    "description": "How strongly to pull the fabric's chroma toward the masked region (0.0 = keep fabric color exactly).",
    "default_value": "0.0"
  },
  {
    "name": "detail_boost",
    "description": "Legacy unsharp boost on shaded fabric. With frequency-separation lighting this is rarely needed. 0.0 = off, 1.0 = strong.",
    "default_value": "0.0"
  },
  {
    "name": "ambient_pickup",
    "description": "Tint the fabric (in LAB chroma) toward the mean color of pixels just outside the mask. 0.0 = off, 1.0 = strong.",
    "default_value": "0.25"
  },
  {
    "name": "contact_shadow",
    "description": "Darken the fabric near mask edges to simulate a contact shadow where fabric meets the frame. 0.0 = off, 1.0 = strong.",
    "default_value": "0.3"
  },
  {
    "name": "crease_strength",
    "description": "Pick up shadow valleys (creases, folds) from the original photo and darken the fabric there. 0.0 = off, 1.0 = strong.",
    "default_value": "0.4"
  },
  {
    "name": "grain_match",
    "description": "Match photographic grain. Samples noise std from outside the mask and adds matching noise inside it. 0.0 = clean, 1.0 = full match.",
    "default_value": "0.5"
  },
  {
    "name": "blend_mode",
    "description": "Edge composite mode. 'poisson' uses OpenCV seamlessClone for invisible boundaries; 'feather' uses Gaussian-blurred alpha (legacy).",
    "default_value": "poisson"
  }
]
""")


# ───────────────────────────── helpers ─────────────────────────────

def _clip01(a):
    return np.clip(a, 0.0, 1.0)


def _decode_image_param(b64, name, mode="RGB"):
    if not b64:
        raise ValueError(f"{name} parameter is required")
    data = decode_param_image(b64)
    return Image.open(io.BytesIO(data)).convert(mode)


def _tile_fabric_region(fabric_rgb, canvas, region_mask, tile_scale, target_repeats=8):
    """Tile `fabric_rgb` into `canvas` over the area where `region_mask` > 0.05.

    Tile size is derived from sqrt(region_area) / target_repeats so each
    connected region gets an appropriately-sized pattern — smaller regions
    get smaller tiles, larger regions get larger tiles, but in both cases
    the fabric repeats ~target_repeats times across the region.
    """
    ys, xs = np.where(region_mask > 0.05)
    if len(xs) == 0:
        return
    x0, y0 = int(xs.min()), int(ys.min())
    x1, y1 = int(xs.max()) + 1, int(ys.max()) + 1
    rw, rh = x1 - x0, y1 - y0

    area = float(region_mask.sum())
    base_tile = max(32, int(round(np.sqrt(area) / target_repeats)))
    tile_px   = max(16, int(round(base_tile * tile_scale)))

    # Resize fabric keeping aspect: longer side -> tile_px
    fw, fh = fabric_rgb.size
    if fw >= fh:
        new_w = tile_px
        new_h = max(1, int(round(fh * (tile_px / fw))))
    else:
        new_h = tile_px
        new_w = max(1, int(round(fw * (tile_px / fh))))
    fabric_small = fabric_rgb.resize((new_w, new_h), Image.LANCZOS)

    # Brick (half-drop) offset: alternate rows shift by half a tile width to
    # break the grid pattern and hide vertical seams.
    for row_idx, y in enumerate(range(y0, y1, new_h)):
        x_offset = (new_w // 2) if (row_idx & 1) else 0
        for x in range(x0 - x_offset, x1, new_w):
            canvas.paste(fabric_small, (x, y))


def _tile_fabric(fabric_rgb, target_size, tile_scale, mask_np):
    """Tile `fabric_rgb` across `target_size`, per connected mask region.

    If scipy is available, each connected component gets its own tiling
    pass (so a seat and a backrest are tiled independently). Otherwise
    falls back to a single tiling pass based on the full mask area.
    """
    tw, th = target_size
    canvas = Image.new("RGB", (tw, th))

    try:
        from scipy import ndimage
        binary = (mask_np > 0.05).astype(np.uint8)
        labeled, n = ndimage.label(binary)
        if n >= 1:
            for i in range(1, n + 1):
                region = mask_np * (labeled == i)
                _tile_fabric_region(fabric_rgb, canvas, region, tile_scale)
            return canvas
    except ImportError:
        log.info("scipy not available, using single-region tiling")

    # Fallback: treat the whole mask as one region
    _tile_fabric_region(fabric_rgb, canvas, mask_np, tile_scale)
    return canvas


def _luminance(rgb_u8):
    """Rec.709 luma in 0..255 as float32."""
    rgb = rgb_u8.astype(np.float32)
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def _lab_chroma_shift(rgb_u8, target_a, target_b, weight, strength):
    """Shift only L*a*b* a/b channels toward target means (weighted by `weight`).

    Keeps the L channel — and therefore the fabric's perceived brightness and
    micro-detail — untouched. Avoids the colour cast that a naive RGB-mean
    shift produces.
    """
    if strength <= 0.0:
        return rgb_u8
    total_w = float(weight.sum())
    if total_w <= 0.0:
        return rgb_u8
    lab = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2LAB).astype(np.float32)
    cur_a = float((lab[..., 1] * weight).sum() / total_w)
    cur_b = float((lab[..., 2] * weight).sum() / total_w)
    lab[..., 1] += (target_a - cur_a) * strength
    lab[..., 2] += (target_b - cur_b) * strength
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)


def _poisson_composite(item_rgb, src_rgb, mask_np, feather_px):
    """Per-region NORMAL_CLONE Poisson blend with a feather fallback.

    seamlessClone fails when the mask touches the image border or when a
    region is too small to compute a stable Poisson solve. In those cases we
    fall back to a Gaussian-feather alpha composite for that region only.
    """
    item_bgr = cv2.cvtColor(item_rgb, cv2.COLOR_RGB2BGR)
    src_bgr  = cv2.cvtColor(src_rgb, cv2.COLOR_RGB2BGR)
    H, W = item_bgr.shape[:2]
    out_bgr = item_bgr.copy()

    binary_in = (mask_np > 0.05)

    try:
        from scipy import ndimage
        labeled, n_regions = ndimage.label(binary_in.astype(np.uint8))
    except ImportError:
        labeled = binary_in.astype(np.int32)
        n_regions = 1 if binary_in.any() else 0

    def _feather_into(out_bgr, src_bgr, sel):
        mask_local = sel.astype(np.float32)
        if feather_px > 0.01:
            mask_blur = cv2.GaussianBlur(mask_local, (0, 0), sigmaX=max(1.0, feather_px))
        else:
            mask_blur = mask_local
        m3 = mask_blur[..., None]
        return np.clip(src_bgr.astype(np.float32) * m3 +
                       out_bgr.astype(np.float32) * (1.0 - m3),
                       0, 255).astype(np.uint8)

    pad = 4
    kernel3 = np.ones((3, 3), np.uint8)

    for i in range(1, int(n_regions) + 1):
        sel = (labeled == i)
        if not sel.any():
            continue
        ys, xs = np.where(sel)
        x0, y0 = int(xs.min()), int(ys.min())
        x1, y1 = int(xs.max()) + 1, int(ys.max()) + 1

        # seamlessClone needs breathing room around the mask
        if x0 < pad or y0 < pad or x1 > W - pad or y1 > H - pad:
            out_bgr = _feather_into(out_bgr, src_bgr, sel)
            continue

        mask_u8 = (sel.astype(np.uint8)) * 255
        mask_eroded = cv2.erode(mask_u8, kernel3, iterations=1)
        if mask_eroded.max() == 0:
            out_bgr = _feather_into(out_bgr, src_bgr, sel)
            continue

        cx = int((x0 + x1) // 2)
        cy = int((y0 + y1) // 2)
        try:
            out_bgr = cv2.seamlessClone(
                src_bgr, out_bgr, mask_eroded, (cx, cy), cv2.NORMAL_CLONE)
        except cv2.error as e:
            log.info("seamlessClone failed for region %d (%s); falling back to feather", i, e)
            out_bgr = _feather_into(out_bgr, src_bgr, sel)

    return cv2.cvtColor(out_bgr, cv2.COLOR_BGR2RGB)


# ───────────────────────────── main pipeline ─────────────────────────────

def main():
    input_bytes, content_type, params = read_input()

    if not input_bytes:
        write_error("No image_item provided (request body)")
        return

    try:
        mask_b64    = params.get("image_mask", "").strip()
        fabric_b64  = params.get("image_inpaint", "").strip()
        tile_scale  = float(params.get("tile_scale", "1.0") or "1.0")
        feather_px  = float(params.get("feather_px", "3") or "3")
        shading     = float(params.get("shading_strength", "0.8") or "0.8")
        color_match = float(params.get("color_match", "0.0") or "0.0")
        detail_boost = float(params.get("detail_boost", "0.0") or "0.0")
        ambient_pickup = float(params.get("ambient_pickup", "0.25") or "0.25")
        contact_shadow = float(params.get("contact_shadow", "0.3") or "0.3")
        crease_strength = float(params.get("crease_strength", "0.4") or "0.4")
        grain_match = float(params.get("grain_match", "0.5") or "0.5")
        blend_mode  = (params.get("blend_mode", "poisson") or "poisson").strip().lower()
    except ValueError as e:
        write_error(f"Invalid numeric parameter: {e}")
        return

    tile_scale  = max(0.1, min(10.0, tile_scale))
    feather_px  = max(0.0, min(50.0, feather_px))
    shading     = max(0.0, min(1.5, shading))
    color_match = max(0.0, min(1.0, color_match))
    detail_boost = max(0.0, min(1.5, detail_boost))
    ambient_pickup = max(0.0, min(1.0, ambient_pickup))
    contact_shadow = max(0.0, min(1.0, contact_shadow))
    crease_strength = max(0.0, min(1.0, crease_strength))
    grain_match = max(0.0, min(1.0, grain_match))
    if blend_mode not in ("poisson", "feather"):
        blend_mode = "poisson"

    # Decode item
    try:
        item = Image.open(io.BytesIO(input_bytes)).convert("RGB")
    except Exception as e:
        write_error(f"Could not open image_item: {e}")
        return

    W, H = item.size

    # Decode mask (support alpha-encoded masks too)
    try:
        if not mask_b64:
            raise ValueError("image_mask is required")
        mask_raw = Image.open(io.BytesIO(decode_param_image(mask_b64)))
        # If the mask has alpha, use alpha as mask; otherwise use luminance.
        if mask_raw.mode in ("RGBA", "LA"):
            mask_l = mask_raw.split()[-1]
        else:
            mask_l = mask_raw.convert("L")
        mask_l = mask_l.resize((W, H), Image.BILINEAR)
    except Exception as e:
        write_error(f"Could not decode image_mask: {e}")
        return

    # Decode fabric
    try:
        fabric = _decode_image_param(fabric_b64, "image_inpaint", mode="RGB")
    except Exception as e:
        write_error(f"Could not decode image_inpaint: {e}")
        return

    mask_np = np.asarray(mask_l, dtype=np.float32) / 255.0  # 0..1
    if mask_np.max() < 1e-3:
        write_error("image_mask is entirely black (no region selected)")
        return

    # Bounding box of the mask (where mask > 0.05)
    ys, xs = np.where(mask_np > 0.05)
    if len(xs) == 0:
        write_error("image_mask has no usable region")
        return
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)

    # Tile fabric to full canvas (per connected region when possible)
    fabric_tiled = _tile_fabric(fabric, (W, H), tile_scale, mask_np)
    fabric_rgb   = np.asarray(fabric_tiled, dtype=np.uint8)
    item_rgb     = np.asarray(item, dtype=np.uint8)

    # ── Frequency-separation lighting transfer ──
    # The item's LOW-pass luma represents the "lighting layer" (soft shadows,
    # highlights, falloff). We multiply the fabric by (low_item / region_mean)^shading.
    # Because we use the low-pass and not the raw luma, the fabric's high-freq
    # detail (weave, grain) is preserved natively — no unsharp recovery needed.
    item_Y   = _luminance(item_rgb).astype(np.float32)
    lighting_sigma = max(8.0, min(W, H) / 40.0)
    low_item = cv2.GaussianBlur(item_Y, ksize=(0, 0), sigmaX=lighting_sigma)

    w = mask_np
    total_w = float(w.sum())
    item_Y_mean = float((item_Y * w).sum() / total_w) if total_w > 0 else 128.0
    item_Y_mean = max(1.0, item_Y_mean)

    binary_in = (mask_np > 0.05)
    try:
        from scipy import ndimage
        labeled, n = ndimage.label(binary_in.astype(np.uint8))
    except ImportError:
        labeled, n = None, 0

    ratio = np.ones_like(item_Y, dtype=np.float32)
    if n and n >= 1:
        for i in range(1, int(n) + 1):
            sel = (labeled == i)
            if not sel.any():
                continue
            region_w = mask_np * sel
            rw_sum = float(region_w.sum())
            if rw_sum <= 0:
                continue
            region_low_mean = max(1.0, float((low_item * region_w).sum() / rw_sum))
            ratio[sel] = low_item[sel] / region_low_mean
    elif total_w > 0:
        region_low_mean = max(1.0, float((low_item * mask_np).sum() / total_w))
        ratio = low_item / region_low_mean

    ratio = np.clip(ratio, 0.25, 2.5)
    if shading > 0.0:
        ratio = np.power(ratio, shading)
    else:
        ratio = np.ones_like(ratio)

    shaded = fabric_rgb.astype(np.float32) * ratio[..., None]

    # ── Crease / AO pickup ──
    # high_item = item_Y - low_item is negative in shadow valleys (creases,
    # folds, seams). We use only the negative part to darken the fabric there
    # — never to brighten — so the fabric inherits the original photo's micro
    # shadowing without picking up speculars or hot edges.
    if crease_strength > 0.01:
        high_item = item_Y - low_item
        ao = np.clip(1.0 + np.minimum(high_item, 0.0) / 60.0 * crease_strength,
                     0.55, 1.0)
        shaded = shaded * ao[..., None]

    shaded_rgb = np.clip(shaded, 0, 255).astype(np.uint8)

    # ── LAB chroma match (a/b only — preserves fabric's L) ──
    if color_match > 0.0 and total_w > 0:
        item_lab_full = cv2.cvtColor(item_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        target_a = float((item_lab_full[..., 1] * mask_np).sum() / total_w)
        target_b = float((item_lab_full[..., 2] * mask_np).sum() / total_w)
        shaded_rgb = _lab_chroma_shift(shaded_rgb, target_a, target_b, mask_np, color_match)

    # Gentle local-contrast boost on the shaded fabric to restore micro-detail
    # that the multiplication softens. Only affects the fabric, not the item.
    if detail_boost > 0.01:
        percent  = int(round(30 * detail_boost))          # 0..45 typical
        threshold = 2
        shaded_img = Image.fromarray(shaded_rgb, mode="RGB")
        shaded_img = shaded_img.filter(ImageFilter.UnsharpMask(
            radius=2, percent=percent, threshold=threshold))
        shaded_rgb = np.asarray(shaded_img, dtype=np.uint8)

    # Ambient pickup in LAB: sample a ring just OUTSIDE the mask and tint the
    # fabric's a/b channels toward that mean. Bounce light is mostly chroma —
    # shifting only a/b avoids brightening or darkening the fabric.
    if ambient_pickup > 0.01:
        try:
            from scipy import ndimage
            ring_outer = ndimage.binary_dilation(binary_in, iterations=12)
            ring_inner = ndimage.binary_dilation(binary_in, iterations=2)
            ring       = ring_outer & ~ring_inner            # 2..12 px outside
            if ring.any():
                item_lab_full = cv2.cvtColor(item_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
                ring_a = float(item_lab_full[..., 1][ring].mean())
                ring_b = float(item_lab_full[..., 2][ring].mean())
                shaded_rgb = _lab_chroma_shift(
                    shaded_rgb, ring_a, ring_b,
                    binary_in.astype(np.float32),
                    0.35 * ambient_pickup)
        except ImportError:
            log.info("scipy not available, skipping ambient_pickup")

    # Contact shadow: darken the fabric within ~8 px of the mask edge so it
    # looks tucked into the frame rather than pasted on top.
    if contact_shadow > 0.01:
        try:
            from scipy import ndimage
            dist = ndimage.distance_transform_edt(binary_in).astype(np.float32)
            falloff_px = 8.0
            edge_t = np.clip(dist / falloff_px, 0.0, 1.0)
            edge_t = 1.0 - (edge_t * edge_t * (3.0 - 2.0 * edge_t))  # smoothstep inverted
            darken = 1.0 - (edge_t * 0.25 * contact_shadow)         # up to -25% at edge
            darken_full = np.ones_like(mask_np, dtype=np.float32)
            darken_full[binary_in] = darken[binary_in]
            shaded_rgb = np.clip(shaded_rgb.astype(np.float32) * darken_full[..., None],
                                 0, 255).astype(np.uint8)
        except ImportError:
            log.info("scipy not available, skipping contact_shadow")

    # ── Grain matching ──
    # A clean fabric tile composited into a noisy photo is visibly fake.
    # Estimate the photo's high-frequency noise std outside the mask, then
    # add Gaussian noise of matching scale inside the mask.
    if grain_match > 0.01:
        outside = ~binary_in
        if outside.any():
            item_Y_blur = cv2.GaussianBlur(item_Y, (0, 0), sigmaX=1.0)
            hp = item_Y - item_Y_blur
            sigma = float(np.std(hp[outside]))
            sigma = max(0.0, min(sigma * grain_match, 8.0))
            if sigma > 0.05:
                rng = np.random.default_rng(0)  # deterministic per-call
                noise = rng.normal(0.0, sigma, size=shaded_rgb.shape).astype(np.float32)
                noise *= binary_in.astype(np.float32)[..., None]
                shaded_rgb = np.clip(
                    shaded_rgb.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    # ── Composite ──
    if blend_mode == "poisson":
        out = _poisson_composite(item_rgb, shaded_rgb, mask_np, feather_px)
    else:
        if feather_px > 0.01:
            mask_img = Image.fromarray((mask_np * 255).astype(np.uint8), mode="L")
            mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=feather_px))
            mask_blur = np.asarray(mask_img, dtype=np.float32) / 255.0
        else:
            mask_blur = mask_np
        m3 = mask_blur[..., None]
        out = shaded_rgb.astype(np.float32) * m3 + item_rgb.astype(np.float32) * (1.0 - m3)
        out = np.clip(out, 0, 255).astype(np.uint8)

    result = Image.fromarray(out, mode="RGB")

    # Preserve JPEG → JPEG, else PNG
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

    log.info("fabric_mockup done: %dx%d, tile_scale=%.2f, shading=%.2f, feather=%.1f",
             W, H, tile_scale, shading, feather_px)

    write_output(buf.getvalue(), out_ct,
                 mask_bbox=list(bbox),
                 item_y_mean=round(item_Y_mean, 2))


if __name__ == "__main__":
    main()
