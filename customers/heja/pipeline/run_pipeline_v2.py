#!/usr/bin/env python3
"""
Heja team-logo pipeline v2 — with intelligent quality routing.

New routing logic:
1. check_quality → needs_enhancement (based on MP + hard edges)
2. check_transparency → is_transparent
3. IF transparent: skip enhancement + bg removal
4. IF needs_enhancement: GPT2 (handles both quality + bg)
5. IF good quality but not transparent:
   a. has_solid_background → check corners
   b. IF solid: remove_solid_background (fast script)
   c. IF not solid: edge case (skip or GPT2)

Usage:
    python3 run_pipeline_v2.py "<path to logo>"
    python3 run_pipeline_v2.py "<path>" --tag v2
"""

import argparse
import base64
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import replicate
import requests
from openai import OpenAI
from PIL import Image as PILImage

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCRIPTS = REPO / "apiai-tools" / "scripts"
OUT = HERE / "out"
PROCESS_URL = "https://apiai.me/api/process/{slug}"

# GPT2 prompt for enhancement + bg removal
GPT2_PROMPT = ("Remove background outside the team emblem. "
               "Important keep the logo identical with shape and colours. "
               "The colours must match the original exactly.")

PARAMS = {
    "detect_and_crop": {
        "query": "complete logo with text, full team logo with text, entire emblem, club logo",
        "min_padding": "5",
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
    },
    "has_solid_background": {
        "field": "has_solid_bg",
        "sample_size": "10",
        "color_threshold": "50",
    },
    "remove_solid_background": {
        "bg_color": "auto",
        "tolerance": "20",
        "feather": "1",
    },
    "openai-gpt-image-2": {
        "background": "transparent",
        "moderation": "low",
        "output_format": "png",
        "quality": "medium",
        "size": "auto",
    },
    "check_resolution": {
        "field": "is_high_resolution",
        "max_pixels": "2000000",
    },
    "real-esrgan": {
        "scale": "4",
    },
    "crop_transparent": {
        "format": "1:1",
        "margin": "10",
        "alpha_threshold": "10",
    },
}

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


def load_env() -> None:
    """Load .env into os.environ."""
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
    """Drive a node script: JSON on stdin, JSON on stdout."""
    payload = json.dumps({"image": base64.b64encode(image).decode(), "params": params})
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


def run_model(slug: str, image: bytes, params: dict, key: str) -> bytes:
    """Call apiai.me hosted model with retries."""
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
            wait = min(60, 4 * 2 ** (attempt - 1))
            print(f"      {last} — försök {attempt}/{MAX_ATTEMPTS}, väntar {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"{slug}: gav upp efter {MAX_ATTEMPTS} försök ({last})")


def run_openai_direct(image: bytes, prompt: str, params: dict) -> bytes:
    """Call OpenAI GPT Image directly — enables parallel requests (5x faster than via apiai)."""
    client = OpenAI()  # Uses OPENAI_API_KEY from env

    # OpenAI needs the image as a file-like object
    img_file = io.BytesIO(image)
    img_file.name = "input.png"

    # Map our params to OpenAI's API
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


def run_replicate_esrgan(image: bytes, scale: int = 4) -> bytes:
    """Call Real-ESRGAN directly via Replicate — no rate limiting from apiai.me."""
    # Convert image bytes to data URI for Replicate
    b64 = base64.b64encode(image).decode()
    data_uri = f"data:image/png;base64,{b64}"

    # Run the model (nightmareai/real-esrgan is the most common)
    output = replicate.run(
        "nightmareai/real-esrgan:f121d640bd286e1fdc67f9799164c1d5be36ff74576ee11c803ae5b665dd46aa",
        input={
            "image": data_uri,
            "scale": scale,
            "face_enhance": False,
        }
    )

    # Output is a URL, download it
    response = requests.get(output, timeout=120)
    response.raise_for_status()

    # Ensure RGBA for transparency
    img = PILImage.open(io.BytesIO(response.content))
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run_one(src: Path, tag: str = "v2") -> dict:
    """Run the v2 pipeline with intelligent routing."""
    OUT.mkdir(parents=True, exist_ok=True)
    load_env()
    stem = f"{src.stem}-{tag}"
    key = api_key()
    steps, t0 = [], time.time()
    taken = {}
    timings: list[tuple[str, float]] = []

    def timed(label: str, fn):
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

    # Step 1: Detect and crop
    print("  [1] detect_and_crop")
    r = timed("1 · detect_and_crop", lambda: run_script("detect_and_crop", image, PARAMS["detect_and_crop"]))
    image = base64.b64decode(r["image"])
    taken["dino"] = f"{r.get('detection_label')} @ {r.get('detection_confidence')}"
    print(f"      Florence-2: {taken['dino']}")
    save("1-crop", image)

    # Step 2: Check quality (flatness-based)
    print("  [2] check_quality")
    r = timed("2 · check_quality", lambda: run_script("check_quality", image, PARAMS["check_quality"]))
    image = base64.b64decode(r["image"])
    needs_enhancement = str(r.get("needs_enhancement")).lower() == "true"
    mp = r.get("megapixels", 0)
    flatness = r.get("flatness_pct", 0)
    gradient = r.get("gradient_pct")  # Can be None for non-transparent images
    reason = r.get("quality_reason", "")
    taken["needs_enhancement"] = needs_enhancement
    taken["megapixels"] = mp
    taken["flatness_pct"] = flatness
    taken["gradient_pct"] = gradient
    taken["quality_reason"] = reason
    print(f"      MP={mp}, flatness={flatness}%, gradient={gradient}%, reason={reason}")
    print(f"      needs_enhancement = {needs_enhancement}")

    # Step 3: Check transparency
    print("  [3] check_transparency")
    r = timed("3 · check_transparency", lambda: run_script("check_transparency", image, PARAMS["check_transparency"]))
    image = base64.b64decode(r["image"])
    is_transparent = str(r.get("is_transparent")).lower() == "true"
    taken["is_transparent"] = is_transparent
    print(f"      is_transparent = {is_transparent}")

    # Routing decision — QUALITY FIRST, then transparency
    # Quality routing has priority: if the image needs enhancement, run GPT2 regardless
    # of transparency. GPT2 will both enhance AND ensure proper transparency.
    if needs_enhancement:
        print("      → ROUTE: Needs enhancement, using GPT2 (quality + bg)")
        taken["route"] = "gpt2_enhancement"

        # Step 4: GPT2 for enhancement + bg removal (direct OpenAI call)
        print("  [4] openai-gpt-image-2 (direct)")
        params = PARAMS["openai-gpt-image-2"]
        image = timed("4 · openai-gpt-image-2", lambda: run_openai_direct(image, GPT2_PROMPT, params))
        save("4-gpt2", image)
        taken["prompt"] = GPT2_PROMPT
    elif is_transparent:
        # Good quality AND already transparent — nothing to do
        print("      → ROUTE: Good quality + already transparent, skip enhancement + bg removal")
        taken["route"] = "transparent_skip"
    else:
        # Good quality, but needs bg removal
        print("      → ROUTE: Good quality, checking background...")

        # Step 4a: Check if solid background
        print("  [4a] has_solid_background")
        r = timed("4a · has_solid_background", lambda: run_script("has_solid_background", image, PARAMS["has_solid_background"]))
        image = base64.b64decode(r["image"])
        has_solid_bg = str(r.get("has_solid_bg")).lower() == "true"
        corner_dist = r.get("corner_distance", 0)
        bg_color = r.get("bg_color", "")
        taken["has_solid_bg"] = has_solid_bg
        taken["corner_distance"] = corner_dist
        taken["bg_color"] = bg_color
        print(f"      corner_distance={corner_dist}, has_solid_bg={has_solid_bg}")

        if has_solid_bg:
            print("      → ROUTE: Solid background, using script removal")
            taken["route"] = "script_bg_removal"

            # Step 4b: Remove solid background with script
            print("  [4b] remove_solid_background")
            r = timed("4b · remove_solid_background", lambda: run_script("remove_solid_background", image, PARAMS["remove_solid_background"]))
            image = base64.b64decode(r["image"])
            save("4b-removebg", image)
            taken["bg_removed_pct"] = r.get("bg_removed_pct", 0)
        else:
            print("      → ROUTE: Multi-color background (edge case), using GPT2")
            taken["route"] = "gpt2_edge_case"

            # Step 4c: GPT2 for edge case (direct OpenAI call)
            print("  [4c] openai-gpt-image-2 (direct)")
            params = PARAMS["openai-gpt-image-2"]
            image = timed("4c · openai-gpt-image-2", lambda: run_openai_direct(image, GPT2_PROMPT, params))
            save("4c-gpt2", image)

    # Step 5: Check resolution
    print("  [5] check_resolution")
    r = timed("5 · check_resolution", lambda: run_script("check_resolution", image, PARAMS["check_resolution"]))
    image = base64.b64decode(r["image"])
    is_high = str(r.get("is_high_resolution")).lower() == "true"
    taken["is_high_resolution"] = is_high
    print(f"      is_high_resolution = {is_high}")

    if not is_high:
        print("  [6] real-esrgan (replicate)")
        scale = int(PARAMS["real-esrgan"].get("scale", 4))
        image = timed("6 · real-esrgan", lambda: run_replicate_esrgan(image, scale))
        save("6-upscale", image)

    # Step 7: Final crop
    print("  [7] crop_transparent")
    r = timed("7 · crop_transparent", lambda: run_script("crop_transparent", image, PARAMS["crop_transparent"]))
    image = base64.b64decode(r["image"])
    save("7-final", image)

    total = time.time() - t0
    record = {"logo": src.name, "tag": tag, "steps": steps, "routing": taken,
              "timings": [{"node": n, "seconds": round(d, 1)} for n, d in timings],
              "seconds": round(total, 1)}

    print("\n  " + "─" * 52)
    print(f"  ROUTE: {taken.get('route', 'unknown')}")
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
    ap.add_argument("--tag", default="v2", help="names this run's intermediates")
    args = ap.parse_args()
    src = Path(args.logo)
    if not src.exists():
        sys.exit(f"finns inte: {src}")
    run_one(src, args.tag)


if __name__ == "__main__":
    main()
