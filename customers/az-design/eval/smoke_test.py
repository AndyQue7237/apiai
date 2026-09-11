#!/usr/bin/env python3
"""
Fas A smoke-test (AZ Design fabric-swap validation).

Runs ONE chair + ONE fabric through the new productized chain and dumps exactly
what each endpoint returns, so we learn the real contracts before building the
full runner:

  1. az-smooth-mask-fabric-creator-with-check-sam3  (chair -> zip(mask) + autocheck JSON)
  2. az-change-fabric-mask                    (chair + fabric + mask -> swapped image)
  3. eval.apiai.me/v1/eval/results           (pull eval results schema)

Cost control: the created mask is cached to smoke_out/. Re-runs skip the
mask-creator call unless --remask is passed.

Usage:
    python smoke_test.py            # full chain
    python smoke_test.py --step 1   # only mask-creator
    python smoke_test.py --step 3   # only pull eval results (free, no compute)
    python smoke_test.py --remask   # force re-create the mask
"""
import argparse
import io
import json
import os
import zipfile
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("APIAI_API_KEY")

PIPELINE_BASE = "https://apiai.me/api/pipeline"
MASK_PIPELINE = "az-smooth-mask-fabric-creator-with-check-sam3"
SWAP_PIPELINE = "az-change-fabric-mask"
EVAL_URL = "https://eval.apiai.me/v1/eval/results"

GDRIVE = Path(
    "/Users/andreasquensel/Library/CloudStorage/GoogleDrive-andreas@zebrolabs.com"
    "/Shared drives/Apiai.me/Customers/AZ Design/Content"
)
CHAIR = GDRIVE / "Tailerd" / "Chairs" / "solid_chair.jpg"
FABRIC = GDRIVE / "Tailerd" / "Fabric" / "fabcric_lars27.jpeg"

OUT = Path(__file__).parent / "smoke_out"
OUT.mkdir(exist_ok=True)


def sniff(content: bytes) -> str:
    """Best-effort detection of a response body's type from magic bytes."""
    if content[:4] == b"PK\x03\x04":
        return "zip"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if content[:3] == b"\xff\xd8\xff":
        return "jpg"
    stripped = content.lstrip()[:1]
    if stripped in (b"{", b"["):
        return "json"
    return "unknown"


def post_pipeline(name: str, files: list) -> requests.Response:
    url = f"{PIPELINE_BASE}/{name}"
    print(f"\n>>> POST {url}")
    print(f"    fields: {[f[0] for f in files]}")
    r = requests.post(url, files=files, headers={"X-API-Key": API_KEY}, timeout=300)
    ct = r.headers.get("Content-Type", "")
    print(f"    <- status={r.status_code}  content-type={ct!r}  bytes={len(r.content)}")
    if r.status_code != 200:
        print(f"    !! body: {r.text[:500]}")
    return r


def dump_response(content: bytes, label: str) -> dict:
    """Save the raw body, identify it, and surface any JSON / zip contents."""
    kind = sniff(content)
    raw_path = OUT / f"{label}.{ 'bin' if kind=='unknown' else kind }"
    raw_path.write_bytes(content)
    print(f"    sniff={kind}  saved={raw_path.name}")
    result = {"kind": kind, "path": str(raw_path)}

    if kind == "json":
        data = json.loads(content)
        print(f"    json keys: {list(data.keys()) if isinstance(data, dict) else f'list[{len(data)}]'}")
        result["json"] = data
        # The pipeline may return a URL to the real artifact (image/zip) — follow it.
        if isinstance(data, dict) and "url" in data:
            print(f"    -> following url: {data['url']}")
            sub = requests.get(data["url"], timeout=60)
            print(f"       fetched {len(sub.content)} bytes, sniff={sniff(sub.content)}")
            result["followed"] = dump_response(sub.content, f"{label}_url")

    elif kind == "zip":
        zf = zipfile.ZipFile(io.BytesIO(content))
        names = zf.namelist()
        print(f"    zip members: {names}")
        result["zip_members"] = names
        members = {}
        for n in names:
            data = zf.read(n)
            (OUT / Path(n).name).write_bytes(data)
            if n.lower().endswith(".json"):
                parsed = json.loads(data)
                print(f"    [{n}] JSON -> {json.dumps(parsed, indent=2)[:800]}")
                members[n] = parsed
            else:
                print(f"    [{n}] {len(data)} bytes -> saved {Path(n).name}")
                members[n] = f"<{len(data)} bytes>"
        result["zip"] = members
    return result


def step1_mask(remask: bool):
    cached = OUT / "mask.png"
    if cached.exists() and not remask:
        print(f"\n[1] mask-creator: SKIP (cached {cached.name}; --remask to force)")
        return
    print("\n[1] mask-creator")
    with open(CHAIR, "rb") as f:
        files = [("image", (CHAIR.name, f, "image/jpeg"))]
        r = post_pipeline(MASK_PIPELINE, files)
    if r.status_code == 200:
        dump_response(r.content, "mask_response")
    print("    (review smoke_out/ for the mask + autocheck JSON)")


def step2_swap():
    print("\n[2] change-fabric-mask")
    # Find the mask the previous step extracted (any png that looks like a mask).
    mask_path = OUT / "mask.png"
    if not mask_path.exists():
        cands = [p for p in OUT.glob("*.png") if "mask" in p.name.lower()]
        mask_path = cands[0] if cands else None
    if not mask_path or not mask_path.exists():
        print("    !! no mask found in smoke_out/ — run step 1 first and check the zip contents.")
        return
    print(f"    using mask: {mask_path.name}")
    # Contract confirmed from eval input_slots: image (chair) + image_reference
    # (fabric) + image_mask (mask).
    with open(CHAIR, "rb") as fc, open(FABRIC, "rb") as ff, open(mask_path, "rb") as fm:
        files = [
            ("image", (CHAIR.name, fc, "image/jpeg")),
            ("image_reference", (FABRIC.name, ff, "image/jpeg")),
            ("image_mask", (mask_path.name, fm, "image/png")),
        ]
        r = post_pipeline(SWAP_PIPELINE, files)
    if r.status_code == 200:
        dump_response(r.content, "swap_response")


def step3_eval():
    print("\n[3] eval results")
    print(f">>> GET {EVAL_URL}?limit=50")
    r = requests.get(EVAL_URL, params={"limit": 50}, headers={"X-API-Key": API_KEY}, timeout=60)
    print(f"    <- status={r.status_code}  bytes={len(r.content)}")
    if r.status_code != 200:
        print(f"    !! body: {r.text[:500]}")
        return
    data = r.json()
    (OUT / "eval_results.json").write_bytes(r.content)
    if isinstance(data, dict):
        print(f"    top-level keys: {list(data.keys())}")
        results = data.get("results") or data.get("data") or data.get("items")
    else:
        results = data
    if isinstance(results, list) and results:
        print(f"    {len(results)} result(s). First record:")
        print(json.dumps(results[0], indent=2)[:1200])
        print(f"\n    field names in record: {list(results[0].keys()) if isinstance(results[0], dict) else type(results[0])}")
    else:
        print(f"    full payload (truncated):\n{json.dumps(data, indent=2)[:1200]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, choices=[1, 2, 3], help="run a single step")
    ap.add_argument("--remask", action="store_true", help="force re-create the mask")
    args = ap.parse_args()

    if not API_KEY:
        raise SystemExit("ERROR: APIAI_API_KEY not found in environment / .env")
    for p in (CHAIR, FABRIC):
        if not p.exists():
            raise SystemExit(f"ERROR: missing asset: {p}")

    print(f"chair  = {CHAIR}")
    print(f"fabric = {FABRIC}")
    print(f"out    = {OUT}")

    if args.step == 1:
        step1_mask(args.remask)
    elif args.step == 2:
        step2_swap()
    elif args.step == 3:
        step3_eval()
    else:
        step1_mask(args.remask)
        step2_swap()
        step3_eval()


if __name__ == "__main__":
    main()
