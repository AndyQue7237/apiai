#!/usr/bin/env python3
"""
Check that a mask follows the shape of the object in the image.

Measures how far the mask's edge drifts from real edges in the source
photo. Low drift = mask hugs the shape; high drift = mask wanders.

Outputs (one body, three modes):
  * overlay — the mask drawn on top of the image, for human review
  * mask    — the input mask, passed through to the next pipeline step
  * zip     — both, plus a JSON report

The pass/fail verdict and the drift measurement always travel in extra,
so the apiai.me UI shows the result regardless of which body is emitted.
"""

import base64
import io
import json
import sys
import logging

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation, binary_erosion, distance_transform_edt

try:
    from script_io import read_input, write_output, write_error
    SCRIPT_IO_AVAILABLE = True
except ImportError:
    SCRIPT_IO_AVAILABLE = False


def decode_param_image(s):
    return base64.b64decode(s)


log = logging.getLogger("check_mask")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")

# ── Defaults ──
DEFAULT_MAX_DRIFT_PX = 5.0
DEFAULT_CANNY_LOW    = 50
DEFAULT_CANNY_HIGH   = 150

# ── Parameter definitions ──
PARAM_DEFS = [
    {
        "name": "image_mask",
        "description": "The mask to check (white = inside the object).",
        "default_value": "",
        "required": True,
    },
    {
        "name": "max_drift_px",
        "description": "How far the mask edge is allowed to wander from the real shape, in pixels. Lower = stricter. 5 px works for most product photos.",
        "default_value": "5",
    },
    {
        "name": "output_mode",
        "description": "What to send back: 'overlay' (mask on photo, for review), 'mask' (input mask passed through, for the next step), 'report' (overlay + a banner showing PASS/FAIL and drift, for quick testing), or 'zip' (everything plus a JSON report).",
        "default_value": "overlay",
    },
    {
        "name": "color",
        "description": "Overlay color as hex. Magenta works on most photos.",
        "default_value": "#ff00ff",
    },
    {
        "name": "opacity",
        "description": "How transparent the overlay is, 0–1. 0.5 lets you see both the mask area and the photo underneath.",
        "default_value": "0.5",
    },
]


# ───────────────────────────── helpers ─────────────────────────────

def _parse_hex_color(s):
    s = (s or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"Invalid hex color: {s!r}")
    return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))


def compute_drift(image_arr, mask_bin, canny_low, canny_high):
    """Median distance in pixels from the mask boundary to the nearest
    detected edge in the source image. Low value = mask follows real
    features. High value = mask drifts somewhere that has no edge.

    Returns None when the metric can't be computed:
      - source image has no detected edges (very low contrast), or
      - mask has no boundary inside the image (empty or covers everything)
    """
    gray = cv2.cvtColor(image_arr.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, canny_low, canny_high)
    if not edges.any():
        return None
    edge_dist = distance_transform_edt(~edges.astype(bool))
    boundary = mask_bin & ~binary_erosion(mask_bin)
    if not boundary.any():
        return None
    return float(np.median(edge_dist[boundary]))


def compute_metrics(image_arr, mask_arr,
                    canny_low=DEFAULT_CANNY_LOW, canny_high=DEFAULT_CANNY_HIGH):
    """Two-metric quality summary: area % (informational) + drift px (the verdict driver)."""
    h, w = mask_arr.shape
    total = float(h * w)
    mask_bin = mask_arr > 127
    area_px = int(mask_bin.sum())
    drift = compute_drift(image_arr, mask_bin, canny_low, canny_high)
    return {
        "mask_area_pct": round(100.0 * area_px / total, 2) if total else 0.0,
        "mask_drift_px": None if drift is None else round(drift, 1),
    }


def derive_warnings(metrics, max_drift_px):
    """One quality warning + a catch-all for degenerate masks."""
    warnings = []
    drift = metrics["mask_drift_px"]
    if drift is None:
        warnings.append(
            f"Mask appears degenerate (area={metrics['mask_area_pct']:.1f} %) — "
            f"no usable boundary, likely empty or covering the whole image."
        )
    elif drift > max_drift_px:
        warnings.append(
            f"Mask edge sits {drift:.1f} px from the real shape (allowed {max_drift_px:.1f}). "
            f"Mask doesn't follow the object — likely too small or too large somewhere."
        )
    return warnings


def _load_font(size):
    """Best-effort font loader. PIL 10.x supports a size arg on
    load_default; older versions ignore it and give a fixed tiny font."""
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def render_report(image_pil, mask_pil, color, opacity, mask_ok,
                  metrics, max_drift_px):
    """Overlay + a banner at the top showing PASS/FAIL and the drift
    measurement. Useful when iterating on different masks — the result is
    visible at a glance without reading metadata."""
    overlay = overlay_mask(image_pil, mask_pil, color, opacity)
    w, h = overlay.size

    banner_h = 90
    canvas = Image.new("RGB", (w, h + banner_h), (24, 24, 24))
    canvas.paste(overlay, (0, banner_h))

    draw = ImageDraw.Draw(canvas)
    font_status = _load_font(46)
    font_value  = _load_font(22)

    status_text = "PASS" if mask_ok else "FAIL"
    status_color = (60, 220, 60) if mask_ok else (240, 80, 80)
    draw.text((24, 20), status_text, font=font_status, fill=status_color)

    drift = metrics.get("mask_drift_px")
    drift_str = f"{drift:.1f}" if drift is not None else "—"
    value_text = f"drift: {drift_str} px   (max {max_drift_px:.1f})"
    # Right-align approximately by measuring text width
    bbox = draw.textbbox((0, 0), value_text, font=font_value)
    text_w = bbox[2] - bbox[0]
    draw.text((w - text_w - 24, 38), value_text,
              font=font_value, fill=(220, 220, 220))
    return canvas


def overlay_mask(image_pil, mask_pil, color, opacity, outline_width=2):
    """Render the mask as a tinted overlay over the source image.

    Tint follows the mask's gray values (anti-aliased edges fade
    smoothly). The outline is computed from a binarised mask
    (threshold 127) so the boundary stays crisp regardless of the
    edge softness.
    """
    if mask_pil.size != image_pil.size:
        mask_pil = mask_pil.resize(image_pil.size, Image.LANCZOS)
    img = np.asarray(image_pil.convert("RGB"), dtype=np.float32)
    mask = np.asarray(mask_pil.convert("L"),   dtype=np.float32) / 255.0
    alpha = np.clip(mask * opacity, 0.0, 1.0)[..., None]
    tint = np.array(color, dtype=np.float32).reshape(1, 1, 3)
    out = img * (1.0 - alpha) + tint * alpha
    if outline_width > 0:
        mask_bin = mask > 0.5
        dilated = binary_dilation(mask_bin, iterations=outline_width)
        out[dilated & ~mask_bin] = color
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGB")


# ─────────────────────────── apiai.me entry ───────────────────────────

def main():
    img_bytes, content_type, params = read_input()
    if not img_bytes:
        write_error("No source image provided (request body)")
        return

    mask_b64 = (params.get("image_mask") or "").strip()
    if not mask_b64:
        write_error("image_mask is required")
        return

    try:
        max_drift_px = float(params.get("max_drift_px") or DEFAULT_MAX_DRIFT_PX)
        color = _parse_hex_color(params.get("color") or "#ff00ff")
        opacity = max(0.0, min(1.0, float(params.get("opacity") or "0.5")))
        output_mode = (params.get("output_mode") or "overlay").strip().lower()
        if output_mode not in ("overlay", "mask", "report", "zip"):
            write_error(f"output_mode must be 'overlay', 'mask', 'report' or 'zip', got {output_mode!r}")
            return
    except ValueError as e:
        write_error(f"Invalid parameter: {e}")
        return

    try:
        image_pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        mask_pil = Image.open(io.BytesIO(decode_param_image(mask_b64)))
        if mask_pil.mode in ("RGBA", "LA"):
            mask_pil = mask_pil.split()[-1]
        else:
            mask_pil = mask_pil.convert("L")
    except Exception as e:
        write_error(f"Could not decode input image: {e}")
        return

    if mask_pil.size != image_pil.size:
        mask_pil = mask_pil.resize(image_pil.size, Image.LANCZOS)

    image_arr = np.asarray(image_pil, dtype=np.float32)
    mask_arr = np.asarray(mask_pil, dtype=np.uint8)

    metrics = compute_metrics(image_arr, mask_arr)
    warnings = derive_warnings(metrics, max_drift_px)
    mask_ok = len(warnings) == 0

    buf = io.BytesIO()
    content_type = "image/png"
    if output_mode == "mask":
        mask_pil.save(buf, format="PNG", optimize=True)
    elif output_mode == "report":
        render_report(image_pil, mask_pil, color, opacity, mask_ok,
                      metrics, max_drift_px).save(buf, format="PNG", optimize=True)
    elif output_mode == "zip":
        import zipfile
        mask_buf = io.BytesIO()
        mask_pil.save(mask_buf, format="PNG", optimize=True)
        ov_buf = io.BytesIO()
        overlay_mask(image_pil, mask_pil, color, opacity).save(ov_buf, format="PNG", optimize=True)
        verdict_json = json.dumps(
            {"mask_ok": mask_ok, "mask_warnings": warnings, **metrics},
            indent=2,
        )
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("mask.png", mask_buf.getvalue())
            zf.writestr("overlay.png", ov_buf.getvalue())
            zf.writestr("result.json", verdict_json)
        content_type = "application/zip"
    else:
        overlay = overlay_mask(image_pil, mask_pil, color, opacity)
        overlay.save(buf, format="PNG", optimize=True)

    log.info("check_mask: ok=%s, mode=%s, area=%.1f%%, drift=%s",
             mask_ok, output_mode, metrics["mask_area_pct"], metrics["mask_drift_px"])

    write_output(
        buf.getvalue(),
        content_type,
        mask_ok=mask_ok,
        mask_warnings=warnings,
        output_mode=output_mode,
        **metrics,
    )


# ─────────────────────── local CLI entry point ───────────────────────

def run_local_cli():
    import argparse
    p = argparse.ArgumentParser(
        description="Check a mask against its source image and produce overlay + JSON verdict.")
    p.add_argument("image", help="Source image path")
    p.add_argument("mask", help="Mask image path")
    p.add_argument("overlay_out", help="Overlay PNG output path")
    p.add_argument("--json-out", default=None, help="Optional JSON output path")
    p.add_argument("--max-drift-px", type=float, default=DEFAULT_MAX_DRIFT_PX)
    p.add_argument("--mode", choices=("overlay", "report"), default="overlay",
                   help="Body output style for the saved PNG.")
    p.add_argument("--color", default="#ff00ff")
    p.add_argument("--opacity", type=float, default=0.5)
    args = p.parse_args()

    image_pil = Image.open(args.image).convert("RGB")
    mask_pil = Image.open(args.mask)
    if mask_pil.mode in ("RGBA", "LA"):
        mask_pil = mask_pil.split()[-1]
    else:
        mask_pil = mask_pil.convert("L")
    if mask_pil.size != image_pil.size:
        mask_pil = mask_pil.resize(image_pil.size, Image.LANCZOS)

    image_arr = np.asarray(image_pil, dtype=np.float32)
    mask_arr = np.asarray(mask_pil, dtype=np.uint8)

    metrics = compute_metrics(image_arr, mask_arr)
    warnings = derive_warnings(metrics, args.max_drift_px)
    mask_ok = len(warnings) == 0

    color = _parse_hex_color(args.color)
    opacity = max(0.0, min(1.0, args.opacity))
    if args.mode == "report":
        out_img = render_report(image_pil, mask_pil, color, opacity,
                                mask_ok, metrics, args.max_drift_px)
    else:
        out_img = overlay_mask(image_pil, mask_pil, color, opacity)
    out_img.save(args.overlay_out, optimize=True)

    verdict = {"mask_ok": mask_ok, "mask_warnings": warnings, **metrics}
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(verdict, f, indent=2)
    log.info("verdict: %s", json.dumps(verdict, indent=2))


if __name__ == "__main__":
    if SCRIPT_IO_AVAILABLE and len(sys.argv) <= 1:
        main()
    else:
        run_local_cli()
