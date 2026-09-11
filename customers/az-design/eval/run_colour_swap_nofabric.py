#!/usr/bin/env python3
"""
Kör az-change-colour-of-chair-without-fabric för ett varumärke utan tyg (Pedrali).
Byter färgen på hela stolen (plast/trä utan klädsel).

Pedrali-färger är MODELL-specifika (DOME* hör till Stol Dome, Nolita* till Stol
Nolita), så vi matchar färg→stol på modellnamn — ingen full korsprodukt.

Eval körs automatiskt på apiai.me-sajten vid varje POST.

Kontrakt: POST /api/pipeline/az-change-colour-of-chair-without-fabric
  image = färgprov   (fält 'image', FÖRST — omvänt mot with-fabric)
  image = stolbild   (SAMMA fält 'image', stol sen)
  -> image/jpeg (stol i ny färg)

Output: {brand}/ColourSwaps/{stol}__{färg}.jpg

Usage:
    python run_colour_swap_nofabric.py Pedrali
    python run_colour_swap_nofabric.py Pedrali --dry-run
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
COLOUR_PIPELINE = "az-change-colour-of-chair-without-fabric"

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


def model_key(chair: Path) -> str:
    """First word after 'Stol' — the model name colours are prefixed with."""
    stem = chair.stem
    rest = stem[4:].strip() if stem.lower().startswith("stol") else stem
    return rest.split()[0].lower() if rest.split() else ""


def colours_for(chair: Path, colours: list[Path]) -> list[Path]:
    key = model_key(chair)
    return [c for c in colours if c.stem.lower().startswith(key)]


def run_colour(colour: Path, chair: Path) -> tuple[bytes | None, str, str]:
    url = f"{PIPELINE_BASE}/{COLOUR_PIPELINE}"
    with open(colour, "rb") as fr, open(chair, "rb") as fc:
        # Both in the SAME 'image' field, colour FIRST then chair (without-fabric order).
        files = [
            ("image", (colour.name, fr, mime(colour))),
            ("image", (chair.name, fc, mime(chair))),
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
    ap.add_argument("brand", help="Varumärke utan tyg, t.ex. Pedrali")
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

    jobs = []
    for chair in chairs:
        matched = colours_for(chair, colours)
        if not matched:
            print(f"  ⚠️  {chair.stem}: ingen matchande färg (nyckel '{model_key(chair)}')")
        for colour in matched:
            jobs.append((chair, colour))

    print(f"Varumärke: {brand}  (without-fabric)")
    print(f"  Stolar: {len(chairs)} | Färger: {len(colours)}")
    for chair in chairs:
        print(f"    {chair.stem}: {[c.stem for c in colours_for(chair, colours)]}")
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
        out_path = out_dir / f"{chair.stem}__{colour.stem}.jpg"
        print(f"[{i}/{len(jobs)}] {chair.stem}  ×  {colour.stem}")
        content, err, ct = run_colour(colour, chair)
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

    report = Path(__file__).parent / f"colour_report_{brand.lower()}_nofabric.json"
    report.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nRapport: {report}")


if __name__ == "__main__":
    main()
