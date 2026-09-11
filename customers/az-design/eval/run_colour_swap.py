#!/usr/bin/env python3
"""
Kör az-change-colour-of-chair för ett varumärke: varje (tyg-)stol × varje
färgprov (bets). Byter träfärgen, bevarar tyget.

Gäller bara stolar MED tyg — vi använder "har en producerad mask" som kriterium
(masker skapades bara för fabric-stolar av generate_masks.py).

Eval körs automatiskt på apiai.me-sajten vid varje POST (profile_id=8) — vi
pullar den inte här.

Kontrakt: POST /api/pipeline/az-change-colour-of-chair
  image = stolbild   (fält 'image', först)
  image = färgprov   (SAMMA fält 'image', repeterat — stol först, färg sen)
  -> image/jpeg (stol med ny träfärg)

Output: {brand}/ColourSwaps/{stol}__{färg}.jpg

Usage:
    python run_colour_swap.py Paged
    python run_colour_swap.py Paged --dry-run
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
COLOUR_PIPELINE = "az-change-colour-of-chair"

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


def has_fabric(brand: str, chair: Path) -> bool:
    """A chair has fabric iff generate_masks.py produced a mask for it."""
    return (GDRIVE / brand / "Masks" / f"{chair.stem}_maskzip" / "mask.png").exists()


def run_colour(chair: Path, colour: Path) -> tuple[bytes | None, str, str]:
    url = f"{PIPELINE_BASE}/{COLOUR_PIPELINE}"
    with open(chair, "rb") as fc, open(colour, "rb") as fr:
        # Both images go in the SAME 'image' field — chair first, colour second
        # (the has-fabric order; the pipeline keeps the upholstery).
        files = [
            ("image", (chair.name, fc, mime(chair))),
            ("image", (colour.name, fr, mime(colour))),
        ]
        try:
            r = requests.post(url, files=files, headers={"X-API-Key": API_KEY}, timeout=300)
        except requests.RequestException as e:
            return None, f"Request failed: {e}", ""
    ct = r.headers.get("content-type", "")
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}", ct
    if "image" not in ct:
        return None, f"Unexpected response (not an image), content-type={ct}", ct
    return r.content, "", ct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("brand", help="Varumärke, t.ex. Paged")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not API_KEY:
        raise SystemExit("ERROR: APIAI_API_KEY saknas i miljön / .env")

    brand = args.brand
    chairs = images_in(GDRIVE / brand / "Chairs")
    colours = images_in(GDRIVE / brand / "Colours")
    if not chairs:
        raise SystemExit(f"Inga stolar i {brand}/Chairs")
    if not colours:
        raise SystemExit(f"Inga färger i {brand}/Colours")

    fabric_chairs = [c for c in chairs if has_fabric(brand, c)]
    skipped = [c.name for c in chairs if not has_fabric(brand, c)]

    jobs = [(chair, colour) for chair in fabric_chairs for colour in colours]

    print(f"Varumärke: {brand}")
    print(f"  Tyg-stolar (har mask): {len(fabric_chairs)}/{len(chairs)}")
    if skipped:
        print(f"  ⚠️  Hoppar över (ingen tyg-mask): {skipped}")
    print(f"  Färger: {len(colours)} -> {[c.stem for c in colours]}")
    print(f"  Totalt jobb: {len(jobs)}\n")

    if args.dry_run:
        for chair, colour in jobs:
            print(f"  {chair.stem}  ×  {colour.stem}")
        print("\n--dry-run: avslutar.")
        return

    out_dir = GDRIVE / brand / "ColourSwaps"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i, (chair, colour) in enumerate(jobs, 1):
        ext = ".jpg"
        out_path = out_dir / f"{chair.stem}__{colour.stem}{ext}"
        print(f"[{i}/{len(jobs)}] {chair.stem}  ×  {colour.stem}")
        content, err, ct = run_colour(chair, colour)
        if err:
            print(f"    ❌ {err}")
            results.append({"chair": chair.name, "colour": colour.name, "status": "error", "error": err})
            continue
        if "png" in ct:
            out_path = out_path.with_suffix(".png")
        out_path.write_bytes(content)
        print(f"    ✅ {out_path.relative_to(GDRIVE)}  ({len(content)//1024} KB)")
        results.append({"chair": chair.name, "colour": colour.name, "status": "ok", "output": str(out_path)})

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    print("\n" + "=" * 56)
    print(f"KLART: {ok}/{len(results)} färgbytta", f"| {err} fel" if err else "")
    if err:
        for r in results:
            if r["status"] == "error":
                print(f"  - {r['chair']} × {r['colour']}: {r['error']}")

    report = Path(__file__).parent / f"colour_report_{brand.lower()}.json"
    report.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nRapport: {report}")


if __name__ == "__main__":
    main()
