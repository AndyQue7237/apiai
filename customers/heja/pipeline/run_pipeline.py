#!/usr/bin/env python3
"""
⚠️  DEPRECATED — använd run_pipeline_v2.py istället!

v1 saknar quality-based routing och corner-check för bakgrundsdetektering.
v2 har full routing: check_quality → check_transparency → has_solid_background.

Denna fil behålls för bakåtkompatibilitet och jämförelsetester.
"""
"""
Heja team-logo pipeline — local replica of the live apiai.me pipeline `team-logo-nb-pro`.

Runs the SAME node scripts the platform runs (`apiai-tools/scripts/*.py`, driven over their
stdin/stdout JSON contract) and the SAME two hosted models (`/api/process/…`), wired with the same
two conditions. It is a replica so we can swap ONE node and measure the difference — the whole
point being to try GPT Image 2 in place of Nano Banana Pro + the background remover.

Every intermediate is written to out/, because a defect has to be traceable to the NODE that caused
it. Before→after tells you something is wrong; step-by-step tells you where.

The generative node makes byte-identity impossible even at temperature 0.2. "Identical to the
platform" therefore means: same node behaviour, same conditions taken, same output geometry, and a
visually equivalent result — not the same pixels.

Params below were supplied by Andreas 2026-08-31 from the live platform config. Anything marked
DEFAULT is the node script's own default, left untouched there too.

Usage:
    python3 run_pipeline.py "<path to logo>"            # full chain
    python3 run_pipeline.py "<path>" --tag nbpro        # name this run's intermediates
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
from openai import OpenAI

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCRIPTS = REPO / "apiai-tools" / "scripts"
OUT = HERE / "out"
PROCESS_URL = "https://apiai.me/api/process/{slug}"

# ── The live configuration, verbatim ──
NB_PRO_PROMPT = """You are a master Art Restorer and Forensic Image Upscaler. Your sole task is to take low-quality original images of team emblems (which may be pixelated, blurry, or photos of fabric) and reconstruct them as pristine, high-resolution, print-ready vector-style images.

MANDATORY RESTORATION RULES:

FIDELITY ABOVE ALL: The final output must be an exact reconstruction of the original design, shape, text, and structure. Do not "improve" the artistic design. Do not add or remove elements.

PERFECT COLOR MATCH: The colors must be extracted from the original input and maintained with 100% hue and saturation fidelity. If the input is a blurry photo of a faded emblem, your goal is to find the original, intended colors and apply them uniformly. No fading.

NOISE AND ARTIFACT REMOVAL: Completely eliminate any compression artifacts, noise, blur, and fabric texture.

SHARP LINES: All curves, edges, and lines must be rendered with perfect, smooth, clean vector-like precision. All text must be rendered legibly, matching the exact original font structure.

SOLID BACKGROUND: Isolate the finished, reconstructed emblem on a pristine, solid white background (#FFFFFF). This is for pre-processing purposes.

Task: Reconstruct the original input emblem with perfect fidelity, making it a crystal-clear vector-style image on a solid white background."""

# ── The challenger: GPT Image 2 replaces nodes 3 AND 4 ──
# It draws the emblem AND removes the background in one call, so the chain loses the node where
# both background defects live. `size=auto` rather than 1024x1024, measured: forcing a square puts
# 59% of Trollbäckens' generated pixels into white padding that is then thrown away, so the logo
# itself is rendered at 866x496 and upscaled 4x from that. Nothing downstream needs a square —
# crop_transparent frames 1:1 at the end. Cost is the one trade-off: auto may pick a larger canvas
# than a square, and OpenAI bills by size.
# Andreas's own wording, kept verbatim — including "Important", which is exactly the kind of
# emphasis word a model reacts to and which I had no business tidying away. The third sentence is
# his addition: colour is the known risk on this pipeline, so the prompt is pointed at it.
# Deliberately three plain sentences. His freestyled prompt beat NB Pro's six numbered rule blocks,
# which is the repo's standing lesson rather than a surprise: simpler prompts win.
GPT2_PROMPT = ("Remove background outside the team emblem. "
               "Important keep the logo identical with shape and colours. "
               "The colours must match the original exactly.")

PARAMS = {
    "detect_and_crop": {
        "query": "complete logo with text, full team logo with text, entire emblem, club logo",
        "min_padding": "5",
        # DEFAULT: box_threshold 0.25 · text_threshold 0.25 · padding_percent 5 · safety_margin 30
    },
    "check_quality": {
        "field": "needs_enhancement",
        "mp_high_threshold": "1.0",
        "mp_low_threshold": "0.09",
        "flatness_threshold": "80",
        "gradient_threshold": "50",
    },
    "check_transparency": {
        "field": "is_transparent",
        "sample_percent": "5",
        # DEFAULT: threshold 250
    },
    "nano-banana-pro": {
        "prompt": NB_PRO_PROMPT,
        "temperature": "0.2",
        "top_k": "15",
        "top_p": "0.1",
        "image_size": "1K",
    },
    "detect_and_remove_bg": {
        "query": "emblem or shield or badge",
        "remove_holes_threshold": "2",
        # DEFAULT: box_threshold 0.25 · bg_color auto · tolerance 20 · feather 1
    },
    "check_resolution": {
        "field": "is_high_resolution",
        # NOTE: 2,000,000 here, while README states the delivery bar to Heja as 1,500,000.
        # Two different numbers in two places — the gate is this one.
        "max_pixels": "2000000",
    },
    "real-esrgan": {
        "scale": "4",
        # face_enhance deliberately OFF — these are emblems, and face enhancement on a crest
        # invents detail in exactly the places fidelity matters.
    },
    "openai-gpt-image-2": {
        "background": "transparent",
        "moderation": "low",   # Andreas, 2026-08-31
        "output_format": "png",
        "quality": "medium",   # Andreas: high is too slow and too expensive for Heja
        "size": "auto",
        # `prompt` is injected per method so the two prompt variants stay one variable apart
    },
    "crop_transparent": {
        "format": "1:1",
        "margin": "10",
        "alpha_threshold": "10",
        # DEFAULT: subject_scale off · background transparent
    },
}


def load_env() -> None:
    """Put the repo-root .env into os.environ. The node scripts run as SUBPROCESSES and call
    Replicate themselves (Grounding DINO), so the token has to be in the inherited environment —
    reading it here into a variable would not reach them."""
    for p in [HERE, *HERE.parents]:
        f = p / ".env"
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        break


def api_key() -> str:
    key = os.environ.get("APIAI_API_KEY")
    if not key:
        sys.exit("APIAI_API_KEY not set (env or .env).")
    return key


def run_script(name: str, image: bytes, params: dict) -> dict:
    """Drive a node script exactly as the platform does: JSON on stdin, JSON on stdout."""
    payload = json.dumps({"image": base64.b64encode(image).decode(), "params": params})
    # HERE is on the path so the scripts find the local `script_io` shim; the runtime supplies
    # its own, and these scripts have no local fallback of their own.
    env = {**os.environ, "PYTHONPATH": f"{HERE}:{os.environ.get('PYTHONPATH', '')}"}
    proc = subprocess.run([sys.executable, str(SCRIPTS / f"{name}.py")],
                          input=payload, capture_output=True, text=True,
                          cwd=str(SCRIPTS), env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"{name} exited {proc.returncode}: {proc.stderr[-600:]}")
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"{name} did not return JSON: {proc.stdout[:300]}")
    if "error" in out:
        raise RuntimeError(f"{name}: {out['error']}")
    return out


# Retries, because running several logos at once provably trips the rate limit: four workers
# earned a 429 on the first parallel run (2026-08-31). Transient 5xx are retried by the same path.
# A refusal is NOT retried — Gemini's IMAGE_RECITATION on Chicago is a verdict, not a hiccup, and
# retrying it three times just burns three minutes to get the same answer.
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


def run_model(slug: str, image: bytes, params: dict, key: str) -> bytes:
    last = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        r = requests.post(PROCESS_URL.format(slug=slug), headers={"X-API-Key": key},
                          files={"image": ("input.png", image, "image/png")},
                          data=params, timeout=600)
        if r.status_code == 200:
            return r.content
        if "IMAGE_RECITATION" in r.text or r.status_code not in RETRY_STATUS:
            r.raise_for_status()
            raise RuntimeError(f"{slug}: HTTP {r.status_code} {r.text[:200]}")
        last = f"HTTP {r.status_code}"
        if attempt < MAX_ATTEMPTS:
            wait = min(60, 4 * 2 ** (attempt - 1))  # 4s, 8s, 16s
            print(f"      {last} — försök {attempt}/{MAX_ATTEMPTS}, väntar {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"{slug}: gav upp efter {MAX_ATTEMPTS} försök ({last})")


def run_openai_direct(image: bytes, prompt: str, params: dict) -> bytes:
    """Call OpenAI GPT Image directly — enables parallel requests (5x faster than via apiai)."""
    import io
    from PIL import Image as PILImage

    client = OpenAI()  # Uses OPENAI_API_KEY from env

    # OpenAI needs the image as a file-like object
    img_file = io.BytesIO(image)
    img_file.name = "input.png"

    # Map our params to OpenAI's API (carpx uses gpt-image-2, size=auto, quality=medium/high)
    size = params.get("size", "auto")
    quality = params.get("quality", "medium")

    response = client.images.edit(
        model="gpt-image-2",
        image=img_file,
        prompt=prompt,
        size=size,
        quality=quality,
        background="transparent",  # Request actual alpha channel, not drawn pattern
        output_format="png",       # PNG supports alpha, JPG does not
    )

    # API returns b64_json by default
    b64_data = response.data[0].b64_json
    img_bytes = base64.b64decode(b64_data)

    # Ensure we have RGBA (transparent background)
    img = PILImage.open(io.BytesIO(img_bytes))
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run_one(src: Path, tag: str = "nbpro", method: str = "nbpro") -> dict:
    """Run the whole chain for one logo, writing every intermediate. Returns a run record:
    the ordered steps, which conditions were taken, and the wall clock."""
    OUT.mkdir(parents=True, exist_ok=True)
    load_env()
    stem = f"{src.stem}-{tag}"
    key = api_key()
    steps, t0 = [], time.time()
    taken = {}
    timings: list[tuple[str, float]] = []

    def timed(label: str, fn):
        """Wall clock per node. The chain is slow end to end (~90-100 s via apiai) and the point of
        measuring here is to see WHICH node owns that time rather than assume."""
        start = time.time()
        out = fn()
        dt = time.time() - start
        timings.append((label, dt))
        print(f"      {dt:6.1f}s", flush=True)
        return out

    def save(step: str, data: bytes) -> None:
        p = OUT / f"{stem}-{step}.png"
        p.write_bytes(data)
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(data))
        steps.append({"step": step, "file": p.name, "size": list(im.size), "mode": im.mode})
        print(f"    → {p.name}  {im.size[0]}×{im.size[1]}  {im.mode}", flush=True)

    image = src.read_bytes()
    print(f"\n{src.name}  ({len(image)//1024} kB)\n")

    print("  [1] detect_and_crop")
    r = timed("1 · detect_and_crop (Florence-2)", lambda: run_script("detect_and_crop", image, PARAMS["detect_and_crop"]))
    image = base64.b64decode(r["image"])
    taken["dino"] = f"{r.get('detection_label')} @ {r.get('detection_confidence')}"
    print(f"      Florence-2: {taken['dino']}")
    save("1-crop", image)

    # Quality metrics (informational only in v1 - doesn't affect routing)
    print("  [1b] check_quality (info)")
    r_quality = timed("1b · check_quality", lambda: run_script("check_quality", image, PARAMS["check_quality"]))
    taken["megapixels"] = r_quality.get("megapixels", 0)
    taken["flatness_pct"] = r_quality.get("flatness_pct", 0)
    taken["gradient_pct"] = r_quality.get("gradient_pct")  # None if not transparent
    taken["quality_reason"] = r_quality.get("quality_reason", "")
    taken["needs_enhancement"] = str(r_quality.get("needs_enhancement")).lower() == "true"
    grad_str = f"{taken['gradient_pct']:.1f}%" if taken['gradient_pct'] is not None else "N/A"
    print(f"      MP={taken['megapixels']:.2f}, flatness={taken['flatness_pct']:.1f}%, gradient={grad_str}")
    print(f"      reason={taken['quality_reason']} → v2 would: {'GPT2' if taken['needs_enhancement'] else 'skip'}")

    print("  [2] check_transparency")
    r = timed("2 · check_transparency", lambda: run_script("check_transparency", image, PARAMS["check_transparency"]))
    image = base64.b64decode(r["image"])
    is_transparent = str(r.get("is_transparent")).lower() == "true"
    taken["is_transparent"] = is_transparent
    print(f"      is_transparent = {is_transparent}"
          f"  → {'hoppar över nod 3–4' if is_transparent else 'kör nod 3–4'}")

    if not is_transparent:
        if method == "nbpro":
            print("  [3] nano-banana-pro")
            image = timed("3 · nano-banana-pro", lambda: run_model("nano-banana-pro", image, PARAMS["nano-banana-pro"], key))
            save("3-nbpro", image)

            print("  [4] detect_and_remove_bg")
            r = timed("4 · detect_and_remove_bg (DINO)", lambda: run_script("detect_and_remove_bg", image, PARAMS["detect_and_remove_bg"]))
            image = base64.b64decode(r["image"])
            save("4-removebg", image)
        else:
            prompt = GPT2_PROMPT
            print("  [3] openai-gpt-image-2 (direct)")
            params = PARAMS["openai-gpt-image-2"]
            image = timed("3 · openai-gpt-image-2", lambda: run_openai_direct(image, prompt, params))
            save("3-gpt2", image)
            taken["prompt"] = prompt
            # Node 4 is deliberately absent: the model was asked to remove the background itself,
            # and whether it really did is the thing under test. If the alpha is fake the
            # checkerboard view shows it at once.
            import io as _io
            from PIL import Image as _Image
            mode = _Image.open(_io.BytesIO(image)).mode
            print(f"      utdata är {mode}"
                  f"{'  ✅ äkta alfa' if mode in ('RGBA', 'LA') else '  ❌ INGEN alfakanal'}")
            taken["gpt2_mode"] = mode

    print("  [5] check_resolution")
    r = timed("5 · check_resolution", lambda: run_script("check_resolution", image, PARAMS["check_resolution"]))
    image = base64.b64decode(r["image"])
    is_high = str(r.get("is_high_resolution")).lower() == "true"
    taken["is_high_resolution"] = is_high
    print(f"      is_high_resolution = {is_high}"
          f"  → {'hoppar över nod 6' if is_high else 'kör nod 6'}")

    if not is_high:
        print("  [6] real-esrgan")
        image = timed("6 · real-esrgan", lambda: run_model("real-esrgan", image, PARAMS["real-esrgan"], key))
        save("6-upscale", image)

    print("  [7] crop_transparent")
    r = timed("7 · crop_transparent", lambda: run_script("crop_transparent", image, PARAMS["crop_transparent"]))
    image = base64.b64decode(r["image"])
    save("7-final", image)

    total = time.time() - t0
    record = {"logo": src.name, "tag": tag, "method": method, "steps": steps, "conditions": taken,
              "timings": [{"node": n, "seconds": round(d, 1)} for n, d in timings],
              "seconds": round(total, 1)}
    print("\n  " + "─" * 52)
    for name, dt in sorted(timings, key=lambda x: -x[1]):
        bar = "█" * max(1, round(dt / max(total, 0.001) * 30))
        print(f"  {name:<34}{dt:6.1f}s {dt/total*100:4.0f}%  {bar}")
    print(f"  {'TOTALT':<34}{total:6.1f}s")
    (OUT / f"{stem}-steps.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    print(f"\n  klart på {record['seconds']:.0f}s · {len(steps)} mellansteg sparade i {OUT}")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logo", help="path to a team logo")
    ap.add_argument("--tag", default="nbpro", help="names this run's intermediates")
    ap.add_argument("--method", default="", choices=["", "nbpro", "gpt2a"],
                    help="which generative path (default: same as --tag)")
    args = ap.parse_args()
    src = Path(args.logo)
    if not src.exists():
        sys.exit(f"finns inte: {src}")
    run_one(src, args.tag, args.method or args.tag)


if __name__ == "__main__":
    main()
