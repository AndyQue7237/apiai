#!/usr/bin/env python3
"""
NB Pro Inpainting — bundled AI-driven image inpainting with mask precision.

Calls Google's Gemini Image model (gemini-3-pro-image-preview, internally
branded "NB Pro" on apiai.me) with a subject image and a reference image,
then composites the AI output through a smoothed mask so the unmasked
region of the subject is preserved pixel-exact.

Pipeline position:
    chair → SAM-3 → smooth_mask → nb_pro_inpaint → final

Inputs:
  request body: subject image (e.g. chair photo)
  image_mask:   grayscale mask (typically from smooth_mask, white = AI region)
  image_reference: reference image (fabric swatch, color sample, etc.)

The mask defines the canvas dimensions — the subject is padded to match
the mask's aspect ratio before being sent to Gemini. After generation,
the composite is: final = ai * (mask * blend) + subject * (1 - mask * blend).

All Gemini parameters that NB Pro on apiai.me exposes are available as
script parameters and proxied through to the Gemini API.
"""

import base64
import io
import os
import sys
import json
import logging

import ssl
import urllib.request
import urllib.error

import numpy as np
from PIL import Image

# Use certifi's CA bundle if available (helps on macOS where the default
# SSL context can't always locate system roots). Falls back to the
# platform default, which works on Linux servers (apiai.me runtime).
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

try:
    from script_io import read_input, write_output, write_error
    SCRIPT_IO_AVAILABLE = True
except ImportError:
    SCRIPT_IO_AVAILABLE = False


def decode_param_image(s):
    """Decode a base64 image param. Defined locally instead of relying on
    a script_io helper — fewer assumptions about the runtime surface area."""
    return base64.b64decode(s)

log = logging.getLogger("nb_pro_inpaint")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")

# ── Configuration ──
DEFAULT_GEMINI_MODEL = "gemini-3-pro-image-preview"
GEMINI_ENDPOINT_TMPL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
REQUEST_TIMEOUT_S = 180  # generous; image-gen can take 30-60s, longer under load

DEFAULT_PROMPT = (
    "Replace the highlighted area of the subject image. If a reference "
    "image is provided, apply that material/texture/colour; otherwise, "
    "follow the rest of this prompt. Match the subject's lighting, "
    "shadows, and surface direction. Keep the frame, background, and "
    "all other elements identical to the original."
)

SAFETY_CATEGORIES = [
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
]

# Gemini's supported output aspect ratios → ratio (w/h)
SUPPORTED_ASPECTS = {
    "1:1":  1.0,
    "3:4":  3.0 / 4.0,
    "4:3":  4.0 / 3.0,
    "9:16": 9.0 / 16.0,
    "16:9": 16.0 / 9.0,
}
ASPECT_TOLERANCE = 0.02  # ~2% — accommodates rounding from pad-to-aspect

# Warn if subject:mask area ratio is outside this range (AI output suffers
# when one is dramatically larger than the other).
SUBJECT_MASK_AREA_RATIO_MIN = 0.25
SUBJECT_MASK_AREA_RATIO_MAX = 4.0

# ── Parameter definitions (picked up by admin "Scan Script") ──
PARAM_DEFS = [
    {
        "name": "image_mask",
        "description": "Grayscale mask (typically from smooth_mask). White = where AI output should appear. Defines canvas dimensions for the call.",
        "default_value": "",
        "required": True,
    },
    {
        "name": "image_reference",
        "description": "Optional reference image (fabric swatch, color sample, material to apply). If provided, Gemini receives it as a second image alongside the subject. If omitted, the prompt alone drives the inpainting.",
        "default_value": "",
    },
    {
        "name": "prompt",
        "description": "Instruction for Gemini. Describes how to apply the reference to the subject.",
        "default_value": DEFAULT_PROMPT,
    },
    {
        "name": "model",
        "description": "Gemini model name. Default is what NB Pro uses on apiai.me. Override to try new image-gen variants as they're released.",
        "default_value": DEFAULT_GEMINI_MODEL,
    },
    {
        "name": "negative_prompt",
        "description": "Things to exclude. If set, appended to the prompt as a 'Avoid: ...' clause.",
        "default_value": "",
    },
    {
        "name": "aspect_ratio",
        "description": "Output aspect ratio. Options: 1:1, 3:4, 4:3, 9:16, 16:9. The mask is padded (no crop) to this aspect before the Gemini call, so the final image has exactly this shape.",
        "default_value": "1:1",
    },
    {
        "name": "image_size",
        "description": "Output resolution. Options: 1K, 2K, 4K.",
        "default_value": "1K",
    },
    {
        "name": "temperature",
        "description": "0 = deterministic, max 1. Default 0.3 keeps the AI close to the subject; higher values drift more.",
        "default_value": "0.3",
    },
    {
        "name": "top_k",
        "description": "Top-K sampling (max 64).",
        "default_value": "64",
    },
    {
        "name": "top_p",
        "description": "Nucleus sampling cutoff (0-1).",
        "default_value": "0.95",
    },
    {
        "name": "max_output_tokens",
        "description": "Max output tokens (up to 32768). Leave empty to use the model default.",
        "default_value": "",
    },
    {
        "name": "safety_filter_level",
        "description": "BLOCK_LOW_AND_ABOVE, BLOCK_MEDIUM_AND_ABOVE, BLOCK_ONLY_HIGH, BLOCK_NONE. Applied to all safety categories.",
        "default_value": "BLOCK_ONLY_HIGH",
    },
    {
        "name": "blend_strength",
        "description": "How strongly the AI output replaces the subject inside the mask. 1.0 = full AI; <1.0 mixes in some subject.",
        "default_value": "1.0",
    },
]


# ───────────────────────────── helpers ─────────────────────────────

def _pil_to_png_b64(img):
    """PIL Image -> base64-encoded PNG bytes (utf-8 string)."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _pad_mask_to_aspect(mask_pil, aspect_ratio):
    """Pad a grayscale (L) PIL mask to the given aspect ratio with black
    (0 = outside). Returns a new PIL image; no crop, only padding.

    If aspect_ratio is unsupported, return the mask unchanged and log a
    warning. The caller is expected to then send aspect_ratio through to
    Gemini, which may also reject unknown values.
    """
    target = SUPPORTED_ASPECTS.get(aspect_ratio)
    if target is None:
        log.warning("Unknown aspect_ratio %r; mask not padded. Supported: %s",
                    aspect_ratio, sorted(SUPPORTED_ASPECTS.keys()))
        return mask_pil

    w, h = mask_pil.size
    current_aspect = w / h
    if abs(current_aspect - target) < ASPECT_TOLERANCE:
        return mask_pil  # already correct

    if current_aspect > target:
        # Too wide → add vertical padding
        target_h = int(round(w / target))
        target_w = w
    else:
        # Too tall → add horizontal padding
        target_w = int(round(h * target))
        target_h = h

    canvas = Image.new("L", (target_w, target_h), 0)  # 0 = outside the mask
    ox = (target_w - w) // 2
    oy = (target_h - h) // 2
    canvas.paste(mask_pil, (ox, oy))
    log.info("Padded mask %dx%d → %dx%d to match aspect_ratio=%s",
             w, h, target_w, target_h, aspect_ratio)
    return canvas


def _pad_to_dims(img, target_w, target_h, pad_color=(255, 255, 255)):
    """Pad PIL image to (target_w, target_h) centered.

    If the input is larger than the target in any dimension, it is
    first downsampled to fit (aspect-preserving). Without this guard
    PIL.paste with negative offsets would silently crop the corners.
    """
    w, h = img.size
    if (w, h) == (target_w, target_h):
        return img
    if w > target_w or h > target_h:
        scale = min(target_w / w, target_h / h)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        log.info("Subject %dx%d larger than canvas %dx%d — downsampling to %dx%d",
                 w, h, target_w, target_h, new_w, new_h)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        w, h = new_w, new_h
    canvas = Image.new("RGB", (target_w, target_h), pad_color)
    ox = (target_w - w) // 2
    oy = (target_h - h) // 2
    canvas.paste(img.convert("RGB"), (ox, oy))
    return canvas


def _auto_pad_color(img):
    """Sample the image's four corners and return the median RGB as pad color.

    For product photos with clean backgrounds (white, beige, etc.) this
    picks the right background automatically. For complex inputs it
    picks something reasonable.
    """
    arr = np.asarray(img.convert("RGB"))
    h, w = arr.shape[:2]
    c = min(10, h // 4, w // 4)
    if c < 1:
        return (255, 255, 255)
    samples = np.concatenate([
        arr[:c, :c].reshape(-1, 3),
        arr[:c, -c:].reshape(-1, 3),
        arr[-c:, :c].reshape(-1, 3),
        arr[-c:, -c:].reshape(-1, 3),
    ])
    return tuple(int(v) for v in np.median(samples, axis=0))


def _build_request_body(chair_b64, ref_b64, prompt, params):
    """Construct the Gemini generateContent JSON body.

    `ref_b64` may be None or empty — in that case only the subject image
    is sent and Gemini works purely from the prompt.
    """
    # gemini-3-pro-image-preview supports aspectRatio and imageSize in
    # imageConfig but NOT numberOfImages or personGeneration (those are
    # Imagen-only fields). The model returns one image per call.
    generation_config = {
        "temperature": params["temperature"],
        "topK": params["top_k"],
        "topP": params["top_p"],
        "responseModalities": ["IMAGE"],
        "imageConfig": {
            "aspectRatio": params["aspect_ratio"],
            "imageSize": params["image_size"],
        },
    }
    if params.get("max_output_tokens"):
        generation_config["maxOutputTokens"] = int(params["max_output_tokens"])

    safety_settings = [
        {"category": cat, "threshold": params["safety_filter_level"]}
        for cat in SAFETY_CATEGORIES
    ]

    parts = [{"inline_data": {"mime_type": "image/png", "data": chair_b64}}]
    if ref_b64:
        parts.append({"inline_data": {"mime_type": "image/png", "data": ref_b64}})
    parts.append({"text": prompt})

    return {
        "contents": [{"parts": parts}],
        "generationConfig": generation_config,
        "safetySettings": safety_settings,
    }


def _extract_image_from_response(resp_json):
    """Find the inline image bytes in a Gemini generateContent response.

    Walks all candidates in order and returns the first image found.
    Our config requests one image per call, so there's only ever one.
    """
    candidates = resp_json.get("candidates") or []
    for cand in candidates:
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inline_data") or part.get("inlineData")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    return None


def _finish_reason(resp_json):
    """Return the first candidate's finishReason, or '' if not present."""
    candidates = resp_json.get("candidates") or []
    if candidates:
        return candidates[0].get("finishReason", "") or ""
    return ""


def _composite(ai_arr, subject_arr, mask_arr_01, blend_strength):
    """ai * weight + subject * (1 - weight), weight = mask * blend_strength."""
    weight = np.clip(mask_arr_01 * blend_strength, 0.0, 1.0)
    if weight.ndim == 2:
        weight = weight[..., None]
    final = ai_arr.astype(np.float32) * weight + \
            subject_arr.astype(np.float32) * (1.0 - weight)
    return np.clip(final, 0, 255).astype(np.uint8)


class _InpaintError(Exception):
    """Raised on a recoverable pipeline failure that should surface to the user."""


def process(chair_pil, mask_pil, ref_pil, prompt, gen_params,
            blend_strength, api_key, model):
    """Core pipeline: pad → call Gemini → composite. Returns final PIL image.

    Raises _InpaintError on recoverable failures (with a user-facing message).
    """
    # Pad mask to user's aspect_ratio (defines the working canvas)
    aspect_ratio = gen_params["aspect_ratio"]
    mask_pil = _pad_mask_to_aspect(mask_pil, aspect_ratio)
    mask_w, mask_h = mask_pil.size

    # Pad subject to match the mask, using auto-detected background color
    pad_color = _auto_pad_color(chair_pil)
    chair_padded = _pad_to_dims(chair_pil, mask_w, mask_h, pad_color=pad_color)

    # Build the Gemini request
    chair_b64 = _pil_to_png_b64(chair_padded)
    ref_b64 = _pil_to_png_b64(ref_pil) if ref_pil is not None else None
    body = _build_request_body(chair_b64, ref_b64, prompt, gen_params)

    log.info("calling Gemini: model=%s, aspect=%s, size=%s, temp=%.2f, ref=%s",
             model, gen_params["aspect_ratio"],
             gen_params["image_size"], gen_params["temperature"],
             ref_pil is not None)

    req = urllib.request.Request(
        GEMINI_ENDPOINT_TMPL.format(model=model),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S, context=_SSL_CTX) as resp:
            resp_body = resp.read()
    except urllib.error.HTTPError as e:
        try:
            snippet = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            snippet = ""
        raise _InpaintError(f"Gemini returned {e.code}: {snippet or e.reason}")
    except urllib.error.URLError as e:
        raise _InpaintError(f"Gemini request failed: {e.reason}")

    try:
        resp_json = json.loads(resp_body)
    except json.JSONDecodeError as e:
        raise _InpaintError(f"Could not parse Gemini response: {e}")

    ai_bytes = _extract_image_from_response(resp_json)
    finish_reason = _finish_reason(resp_json)
    if not ai_bytes:
        raise _InpaintError(
            "Gemini response contained no image"
            + (f" (finish_reason={finish_reason})" if finish_reason else "")
        )
    if finish_reason and finish_reason not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
        log.info("Gemini finishReason=%s (image present)", finish_reason)

    try:
        ai_pil = Image.open(io.BytesIO(ai_bytes)).convert("RGB")
    except Exception as e:
        raise _InpaintError(f"Could not decode Gemini image: {e}")
    if ai_pil.size != (mask_w, mask_h):
        ai_pil = ai_pil.resize((mask_w, mask_h), Image.LANCZOS)

    # Composite
    final = _composite(
        np.asarray(ai_pil, dtype=np.float32),
        np.asarray(chair_padded, dtype=np.float32),
        np.asarray(mask_pil, dtype=np.float32) / 255.0,
        blend_strength,
    )
    return Image.fromarray(final, mode="RGB")


# ─────────────────────────── apiai.me entry ───────────────────────────

def main():
    chair_bytes, content_type, params = read_input()
    if not chair_bytes:
        write_error("No subject image provided (request body)")
        return

    api_key = os.environ.get(GEMINI_API_KEY_ENV)
    if not api_key:
        write_error(
            f"{GEMINI_API_KEY_ENV} not set in environment. "
            "Configure it in the apiai.me script settings."
        )
        return

    # Required: mask. Optional: reference (prompt-only mode if omitted).
    mask_b64 = (params.get("image_mask") or "").strip()
    ref_b64 = (params.get("image_reference") or "").strip()
    if not mask_b64:
        write_error("image_mask is required")
        return

    # Decode and validate
    try:
        mask_pil = Image.open(io.BytesIO(decode_param_image(mask_b64)))
        if mask_pil.mode in ("RGBA", "LA"):
            mask_pil = mask_pil.split()[-1]
        else:
            mask_pil = mask_pil.convert("L")

        chair_pil = Image.open(io.BytesIO(chair_bytes)).convert("RGB")
        ref_pil = (Image.open(io.BytesIO(decode_param_image(ref_b64))).convert("RGB")
                   if ref_b64 else None)
    except Exception as e:
        write_error(f"Could not decode an input image: {e}")
        return

    if ref_pil is None:
        log.info("No image_reference provided — running in prompt-only mode")

    # Sanity-check size compatibility (AI struggles when one is dramatically
    # larger than the other — mostly empty canvas or heavily downscaled subject).
    subj_area = chair_pil.size[0] * chair_pil.size[1]
    mask_area = mask_pil.size[0]  * mask_pil.size[1]
    if subj_area > 0:
        ratio = mask_area / subj_area
        if ratio < SUBJECT_MASK_AREA_RATIO_MIN or ratio > SUBJECT_MASK_AREA_RATIO_MAX:
            log.warning(
                "Mask area (%dx%d) and subject area (%dx%d) differ by %.1fx. "
                "Output quality may suffer — consider matching their resolutions.",
                *mask_pil.size, *chair_pil.size, max(ratio, 1.0 / ratio),
            )

    # Build prompt (with optional negative_prompt appended)
    prompt = params.get("prompt", DEFAULT_PROMPT) or DEFAULT_PROMPT
    negative_prompt = (params.get("negative_prompt") or "").strip()
    if negative_prompt:
        prompt = f"{prompt}\n\nAvoid: {negative_prompt}"

    # Parse numeric params with safe fallbacks + clamps
    try:
        gen_params = {
            "temperature": float(params.get("temperature", "0.3") or "0.3"),
            "top_k": int(float(params.get("top_k", "64") or "64")),
            "top_p": float(params.get("top_p", "0.95") or "0.95"),
            "aspect_ratio": (params.get("aspect_ratio") or "1:1").strip(),
            "image_size": (params.get("image_size") or "1K").strip(),
            "safety_filter_level": (params.get("safety_filter_level")
                                     or "BLOCK_ONLY_HIGH").strip(),
            "max_output_tokens": (params.get("max_output_tokens") or "").strip(),
        }
        blend_strength = float(params.get("blend_strength", "1.0") or "1.0")
    except ValueError as e:
        write_error(f"Invalid numeric parameter: {e}")
        return

    # Clamp to Gemini's accepted ranges so we fail fast locally
    gen_params["temperature"] = max(0.0, min(1.0, gen_params["temperature"]))
    gen_params["top_p"]       = max(0.0, min(1.0, gen_params["top_p"]))
    gen_params["top_k"]       = max(1,   min(64,  gen_params["top_k"]))
    blend_strength            = max(0.0, min(1.0, blend_strength))

    model = (params.get("model") or DEFAULT_GEMINI_MODEL).strip()

    try:
        final_pil = process(
            chair_pil, mask_pil, ref_pil,
            prompt, gen_params, blend_strength, api_key, model,
        )
    except _InpaintError as e:
        write_error(str(e))
        return

    buf = io.BytesIO()
    final_pil.save(buf, format="PNG", optimize=True)

    log.debug("nb_pro_inpaint done: subject=%dx%d → final=%dx%d",
              *chair_pil.size, *final_pil.size)
    write_output(buf.getvalue(), "image/png")


# ─────────────────────── local CLI entry point ───────────────────────

def run_local_cli():
    """File-based CLI for local testing without apiai.me runtime."""
    # Load .env if available (only relevant for local runs; apiai.me sets
    # env vars natively).
    try:
        from dotenv import load_dotenv
        from pathlib import Path as _Path
        _dir = _Path(__file__).resolve().parent
        for _ in range(5):
            if (_dir / ".env").exists():
                load_dotenv(_dir / ".env")
                break
            _dir = _dir.parent
    except ImportError:
        pass

    import argparse
    p = argparse.ArgumentParser(
        description="NB Pro inpainting (Gemini Image + mask composite).")
    p.add_argument("subject", help="Subject image path (chair photo, etc.)")
    p.add_argument("mask", help="Mask image path")
    p.add_argument("output", help="Output PNG path")
    p.add_argument("--reference", default=None,
                   help="Optional reference image path. If omitted, runs in "
                        "prompt-only mode.")
    p.add_argument("--prompt", default=DEFAULT_PROMPT)
    p.add_argument("--negative-prompt", default="")
    p.add_argument("--aspect-ratio", default="1:1")
    p.add_argument("--image-size", default="1K")
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--top-k", type=int, default=64)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--max-output-tokens", default="")
    p.add_argument("--safety-filter-level", default="BLOCK_ONLY_HIGH")
    p.add_argument("--blend-strength", type=float, default=1.0)
    p.add_argument("--model", default=DEFAULT_GEMINI_MODEL,
                   help=f"Gemini model name (default {DEFAULT_GEMINI_MODEL})")
    args = p.parse_args()

    api_key = os.environ.get(GEMINI_API_KEY_ENV)
    if not api_key:
        log.error("%s not set in environment", GEMINI_API_KEY_ENV)
        sys.exit(1)

    with open(args.subject, "rb") as f:
        chair_pil = Image.open(io.BytesIO(f.read())).convert("RGB")
    mask_pil = Image.open(args.mask)
    if mask_pil.mode in ("RGBA", "LA"):
        mask_pil = mask_pil.split()[-1]
    else:
        mask_pil = mask_pil.convert("L")
    ref_pil = Image.open(args.reference).convert("RGB") if args.reference else None
    if ref_pil is None:
        log.info("No --reference provided — running in prompt-only mode")

    prompt = args.prompt
    if args.negative_prompt:
        prompt = f"{prompt}\n\nAvoid: {args.negative_prompt}"

    gen_params = {
        "temperature": max(0.0, min(1.0, args.temperature)),
        "top_k":       max(1,   min(64,  args.top_k)),
        "top_p":       max(0.0, min(1.0, args.top_p)),
        "aspect_ratio": args.aspect_ratio,
        "image_size":   args.image_size,
        "safety_filter_level": args.safety_filter_level,
        "max_output_tokens":   args.max_output_tokens,
    }
    blend_strength = max(0.0, min(1.0, args.blend_strength))

    try:
        final_pil = process(
            chair_pil, mask_pil, ref_pil,
            prompt, gen_params, blend_strength, api_key, args.model,
        )
    except _InpaintError as e:
        log.error("%s", e)
        sys.exit(1)

    final_pil.save(args.output, optimize=True)
    log.info("Wrote %s", args.output)


if __name__ == "__main__":
    if SCRIPT_IO_AVAILABLE and len(sys.argv) <= 1:
        main()
    else:
        run_local_cli()
