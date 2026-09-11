#!/usr/bin/env python3
"""
Kör az-change-fabric-mask för ett varumärke: varje stol × varje tyg, med den
producerade masken (från generate_masks.py). Sparar swappade bilder.

Eval körs automatiskt på apiai.me-sajten vid varje POST — vi pullar den inte här.

Kontrakt: POST /api/pipeline/az-change-fabric-mask
  image           = stolbild
  image_reference = tygprov
  image_mask      = mask.png (den godkända masken)
  -> image/png (swappad stol)

Output: {brand}/Swaps/{stol}__{tyg}.png

Usage:
    python run_fabric_swap.py Paged           # kör Paged
    python run_fabric_swap.py Paged --dry-run
"""
import argparse
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
API_KEY = os.getenv("APIAI_API_KEY")

PIPELINE_BASE = "https://apiai.me/api/pipeline"
SWAP_PIPELINE = "az-change-fabric-mask"

GDRIVE = Path(
    "/Users/andreasquensel/Library/CloudStorage/GoogleDrive-andreas@zebrolabs.com"
    "/Shared drives/Apiai.me/Customers/AZ Design/Content"
)


def mime(path: Path) -> str:
    s = path.suffix.lower()
    return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(
        s, "application/octet-stream"
    )


def images_in(d: Path) -> list[Path]:
    if not d.exists():
        return []
    return sorted(
        p for p in d.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png") and not p.name.startswith(".")
    )


def mask_for(brand: str, chair: Path) -> Path:
    return GDRIVE / brand / "Masks" / f"{chair.stem}_maskzip" / "mask.png"


def run_swap(chair: Path, fabric: Path, mask: Path) -> tuple[bytes | None, str]:
    url = f"{PIPELINE_BASE}/{SWAP_PIPELINE}"
    with open(chair, "rb") as fc, open(fabric, "rb") as ff, open(mask, "rb") as fm:
        files = [
            ("image", (chair.name, fc, mime(chair))),
            ("image_reference", (fabric.name, ff, mime(fabric))),
            ("image_mask", (mask.name, fm, "image/png")),
        ]
        try:
            r = requests.post(url, files=files, headers={"X-API-Key": API_KEY}, timeout=600)
        except requests.RequestException as e:
            return None, f"Request failed: {e}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    if r.content[:8] != b"\x89PNG\r\n\x1a\n":
        return None, f"Unexpected response (not a PNG), content-type={r.headers.get('content-type')}"
    return r.content, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("brand", help="Varumärke, t.ex. Paged")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not API_KEY:
        raise SystemExit("ERROR: APIAI_API_KEY saknas i miljön / .env")

    brand = args.brand
    chairs = images_in(GDRIVE / brand / "Chairs")
    fabrics = images_in(GDRIVE / brand / "Fabric")
    if not chairs:
        raise SystemExit(f"Inga stolar i {brand}/Chairs")
    if not fabrics:
        raise SystemExit(f"Inga tyger i {brand}/Fabric")

    # Bygg jobblistan, hoppa över stolar som saknar mask
    jobs = []
    skipped = []
    for chair in chairs:
        m = mask_for(brand, chair)
        if not m.exists():
            skipped.append(chair.name)
            continue
        for fabric in fabrics:
            jobs.append((chair, fabric, m))

    print(f"Varumärke: {brand}")
    print(f"  Stolar med mask: {len(chairs) - len(skipped)}/{len(chairs)}")
    if skipped:
        print(f"  ⚠️  Hoppar över (mask saknas): {skipped}")
    print(f"  Tyger: {len(fabrics)} -> {[f.stem for f in fabrics]}")
    print(f"  Totalt jobb: {len(jobs)}\n")

    if args.dry_run:
        for chair, fabric, _ in jobs:
            print(f"  {chair.stem}  ×  {fabric.stem}")
        print("\n--dry-run: avslutar.")
        return

    out_dir = GDRIVE / brand / "Swaps"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i, (chair, fabric, mask) in enumerate(jobs, 1):
        out_path = out_dir / f"{chair.stem}__{fabric.stem}.png"
        print(f"[{i}/{len(jobs)}] {chair.stem}  ×  {fabric.stem}")
        content, err = run_swap(chair, fabric, mask)
        if err:
            print(f"    ❌ {err}")
            results.append({"chair": chair.name, "fabric": fabric.name, "status": "error", "error": err})
            continue
        out_path.write_bytes(content)
        print(f"    ✅ {out_path.relative_to(GDRIVE)}  ({len(content)//1024} KB)")
        results.append({"chair": chair.name, "fabric": fabric.name, "status": "ok", "output": str(out_path)})

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    print("\n" + "=" * 56)
    print(f"KLART: {ok}/{len(results)} swappade", f"| {err} fel" if err else "")
    if err:
        for r in results:
            if r["status"] == "error":
                print(f"  - {r['chair']} × {r['fabric']}: {r['error']}")

    report = Path(__file__).parent / f"swap_report_{brand.lower()}.json"
    report.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nRapport: {report}")


if __name__ == "__main__":
    main()
