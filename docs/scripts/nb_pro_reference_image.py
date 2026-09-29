#!/usr/bin/env python3
"""
NB Pro Reference Image — image generation with a subject + a reference image.

Calls Google's Gemini Image model (gemini-3-pro-image-preview, branded "NB Pro"
on apiai.me) with TWO images — the subject (the request-body image) and a
reference image (a base64 parameter) — plus a prompt, and returns the generated
result. The prompt decides how the reference is applied to the subject (compose
the subject into the reference scene, apply its material/style, etc.).

Why a script: an apiai.me node receives ONE body image (from the previous step
OR user input, never both). To use a second image, it must arrive as a base64
parameter. This node takes the subject from the body and the reference as the
`image_reference` param, so a pipeline can feed a previous-step image as the
subject while the user supplies the reference.

This is the sibling of nb_pro_inpaint.py without the mask/composite step: here the
model's output is returned directly.

Inputs:
  request body:    subject image (alpha is preserved — send RGBA to keep a cut-out)
  image_reference: reference image (base64) — required

All Gemini parameters NB Pro exposes are available as script parameters.
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

from PIL import Image

# Use certifi's CA bundle if available (helps on macOS); fall back to the
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
    """Decode a base64 image param to bytes."""
    return base64.b64decode(s)


log = logging.getLogger("nb_pro_reference_image")
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
    "Compose the subject image into the scene shown in the reference image. "
    "Place the subject realistically — match the reference's perspective, "
    "lighting, shadows, and reflections. Keep the subject's identity, shape, "
    "proportions, and details unchanged. Output a single photorealistic image."
)

SAFETY_CATEGORIES = [
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
]

# Gemini's supported output aspect ratios (for a local warning; the model is the
# final authority).
SUPPORTED_ASPECTS = {"1:1", "3:4", "4:3", "9:16", "16:9"}

# ── Parameter definitions (picked up by admin "Scan Script") ──
# NOTE: every default_value MUST be a plain string literal — the scanner reads
# PARAM_DEFS statically and skips variables/f-strings (see SCRIPT_GUIDELINES.md).
PARAM_DEFS = [
    {
        "name": "image_reference",
        "description": "Reference image (base64). The scene, environment, material, or context to combine with the subject. Sent to the model as a second image alongside the subject.",
        "default_value": "",
        "required": True,
    },
    {
        "name": "prompt",
        "description": "Instruction for the model — how to apply the reference to the subject.",
        "default_value": "Compose the subject image into the scene shown in the reference image. Place the subject realistically — match the reference's perspective, lighting, shadows, and reflections. Keep the subject's identity, shape, proportions, and details unchanged. Output a single photorealistic image.",
    },
    {
        "name": "model",
        "description": "Gemini model name. Default is what NB Pro uses. Override to try new image-gen variants.",
        "default_value": "gemini-3-pro-image-preview",
    },
    {
        "name": "negative_prompt",
        "description": "Things to exclude. If set, appended to the prompt as an 'Avoid: ...' clause.",
        "default_value": "",
    },
    {
        "name": "aspect_ratio",
        "description": "Output aspect ratio. Options: 1:1, 3:4, 4:3, 9:16, 16:9.",
        "default_value": "1:1",
    },
    {
        "name": "image_size",
        "description": "Output resolution. Options: 1K, 2K, 4K.",
        "default_value": "1K",
    },
    {
        "name": "temperature",
        "description": "How creative the model gets — lower stays close to your inputs (consistent, safe), higher is more creative. Range 0-1; 0.3 is a good default.",
        "default_value": "0.3",
    },
    {
        "name": "top_k",
        "description": "How many options the model weighs at each step — higher allows more variety, lower stays more focused. Range 1-64; the default suits most cases.",
        "default_value": "64",
    },
    {
        "name": "top_p",
        "description": "How much variety the model allows in the result — lower is more predictable, higher is more varied. Range 0-1; leave at 0.95 unless you want more or less variation.",
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
]


# ───────────────────────────── helpers ─────────────────────────────

def _pil_to_png_b64(img):
    """PIL Image -> base64-encoded PNG bytes (utf-8 string). PNG preserves alpha."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _build_request_body(subject_b64, ref_b64, prompt, params):
    """Construct the Gemini generateContent JSON body with subject + reference."""
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

    parts = [
        {"inline_data": {"mime_type": "image/png", "data": subject_b64}},
        {"inline_data": {"mime_type": "image/png", "data": ref_b64}},
        {"text": prompt},
    ]

    return {
        "contents": [{"parts": parts}],
        "generationConfig": generation_config,
        "safetySettings": safety_settings,
    }


def _extract_image_from_response(resp_json):
    """Find the first inline image bytes in a Gemini generateContent response."""
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


class _ReferenceImageError(Exception):
    """Raised on a recoverable failure that should surface to the user."""


def process(subject_pil, ref_pil, prompt, gen_params, api_key, model):
    """Call Gemini with subject + reference and return the generated PIL image (RGBA).

    Raises _ReferenceImageError on recoverable failures (with a user-facing message).
    """
    if gen_params["aspect_ratio"] not in SUPPORTED_ASPECTS:
        log.warning("Unknown aspect_ratio %r; the model may reject it. Supported: %s",
                    gen_params["aspect_ratio"], sorted(SUPPORTED_ASPECTS))

    subject_b64 = _pil_to_png_b64(subject_pil)  # RGBA — alpha (cut-out) preserved
    ref_b64 = _pil_to_png_b64(ref_pil)
    body = _build_request_body(subject_b64, ref_b64, prompt, gen_params)

    log.info("calling Gemini: model=%s, aspect=%s, size=%s, temp=%.2f",
             model, gen_params["aspect_ratio"], gen_params["image_size"],
             gen_params["temperature"])
    log.debug("prompt: %s", prompt)

    req = urllib.request.Request(
        GEMINI_ENDPOINT_TMPL.format(model=model),
        data=json.dumps(body).encode("utf-8"),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
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
        raise _ReferenceImageError(f"Gemini returned {e.code}: {snippet or e.reason}")
    except urllib.error.URLError as e:
        raise _ReferenceImageError(f"Gemini request failed: {e.reason}")

    try:
        resp_json = json.loads(resp_body)
    except json.JSONDecodeError as e:
        raise _ReferenceImageError(f"Could not parse Gemini response: {e}")

    ai_bytes = _extract_image_from_response(resp_json)
    finish_reason = _finish_reason(resp_json)
    if not ai_bytes:
        raise _ReferenceImageError(
            "Gemini response contained no image"
            + (f" (finish_reason={finish_reason})" if finish_reason else "")
        )
    if finish_reason and finish_reason not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
        log.info("Gemini finishReason=%s (image present)", finish_reason)

    try:
        # RGBA output per the pipeline output-format rule (SCRIPT_GUIDELINES.md).
        return Image.open(io.BytesIO(ai_bytes)).convert("RGBA")
    except Exception as e:
        raise _ReferenceImageError(f"Could not decode Gemini image: {e}")


def _parse_gen_params(params):
    """Parse + clamp the generation params from a string-keyed dict. Raises ValueError."""
    gen = {
        "temperature": float(params.get("temperature", "0.3") or "0.3"),
        "top_k": int(float(params.get("top_k", "64") or "64")),
        "top_p": float(params.get("top_p", "0.95") or "0.95"),
        "aspect_ratio": (params.get("aspect_ratio") or "1:1").strip(),
        "image_size": (params.get("image_size") or "1K").strip(),
        "safety_filter_level": (params.get("safety_filter_level") or "BLOCK_ONLY_HIGH").strip(),
    }
    # Validate max_output_tokens as an int HERE so a bad value fails clearly in main()
    # ("Invalid numeric parameter") instead of crashing unhandled later in the request build.
    mot = (params.get("max_output_tokens") or "").strip()
    gen["max_output_tokens"] = int(mot) if mot else None
    # Clamp to Gemini's accepted ranges so we fail fast locally.
    gen["temperature"] = max(0.0, min(1.0, gen["temperature"]))
    gen["top_p"] = max(0.0, min(1.0, gen["top_p"]))
    gen["top_k"] = max(1, min(64, gen["top_k"]))
    return gen


def _full_prompt(base_prompt, negative_prompt):
    prompt = base_prompt or DEFAULT_PROMPT
    negative_prompt = (negative_prompt or "").strip()
    if negative_prompt:
        prompt = f"{prompt}\n\nAvoid: {negative_prompt}"
    return prompt


# ─────────────────────────── apiai.me entry ───────────────────────────

def main():
    subject_bytes, content_type, params = read_input()
    if not subject_bytes:
        write_error("No subject image provided (request body)")
        return

    api_key = os.environ.get(GEMINI_API_KEY_ENV)
    if not api_key:
        write_error(
            f"{GEMINI_API_KEY_ENV} not set in environment. "
            "Configure it in the apiai.me script settings."
        )
        return

    ref_b64 = (params.get("image_reference") or "").strip()
    if not ref_b64:
        write_error("image_reference is required")
        return

    try:
        ref_bytes = decode_param_image(ref_b64)
    except Exception:
        write_error("image_reference is not valid base64.")
        return

    try:
        # Keep alpha on both (RGBA) so a cut-out subject/reference stays a cut-out.
        subject_pil = Image.open(io.BytesIO(subject_bytes)).convert("RGBA")
        ref_pil = Image.open(io.BytesIO(ref_bytes)).convert("RGBA")
    except Exception as e:
        write_error(f"Could not decode an input image: {e}")
        return

    prompt = _full_prompt(params.get("prompt"), params.get("negative_prompt"))
    try:
        gen_params = _parse_gen_params(params)
    except ValueError as e:
        write_error(f"Invalid numeric parameter: {e}")
        return
    model = (params.get("model") or DEFAULT_GEMINI_MODEL).strip()

    try:
        final_pil = process(subject_pil, ref_pil, prompt, gen_params, api_key, model)
    except _ReferenceImageError as e:
        write_error(str(e))
        return

    buf = io.BytesIO()
    final_pil.save(buf, format="PNG")
    log.debug("nb_pro_reference_image done: subject=%dx%d → final=%dx%d",
              *subject_pil.size, *final_pil.size)
    write_output(buf.getvalue(), "image/png")


# ─────────────────────── local CLI entry point ───────────────────────

def run_local_cli():
    """File-based CLI for local testing without the apiai.me runtime."""
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
        description="NB Pro reference-image generation (subject + reference → Gemini Image).")
    p.add_argument("subject", help="Subject image path (alpha preserved).")
    p.add_argument("reference", help="Reference image path.")
    p.add_argument("output", help="Output PNG path.")
    p.add_argument("--prompt", default=DEFAULT_PROMPT)
    p.add_argument("--negative-prompt", default="")
    p.add_argument("--aspect-ratio", default="1:1")
    p.add_argument("--image-size", default="1K")
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--top-k", type=int, default=64)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--max-output-tokens", default="")
    p.add_argument("--safety-filter-level", default="BLOCK_ONLY_HIGH")
    p.add_argument("--model", default=DEFAULT_GEMINI_MODEL,
                   help=f"Gemini model name (default {DEFAULT_GEMINI_MODEL})")
    args = p.parse_args()

    api_key = os.environ.get(GEMINI_API_KEY_ENV)
    if not api_key:
        log.error("%s not set in environment", GEMINI_API_KEY_ENV)
        sys.exit(1)

    subject_pil = Image.open(args.subject).convert("RGBA")
    ref_pil = Image.open(args.reference).convert("RGB")

    prompt = _full_prompt(args.prompt, args.negative_prompt)
    gen_params = {
        "temperature": max(0.0, min(1.0, args.temperature)),
        "top_k": max(1, min(64, args.top_k)),
        "top_p": max(0.0, min(1.0, args.top_p)),
        "aspect_ratio": args.aspect_ratio,
        "image_size": args.image_size,
        "safety_filter_level": args.safety_filter_level,
        "max_output_tokens": (int(args.max_output_tokens) if str(args.max_output_tokens).strip() else None),
    }

    try:
        final_pil = process(subject_pil, ref_pil, prompt, gen_params, api_key, args.model)
    except _ReferenceImageError as e:
        log.error("%s", e)
        sys.exit(1)

    final_pil.save(args.output)
    log.info("Wrote %s", args.output)


if __name__ == "__main__":
    if SCRIPT_IO_AVAILABLE and len(sys.argv) <= 1:
        main()
    else:
        run_local_cli()
