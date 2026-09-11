#!/usr/bin/env python3
"""
Genererar masker för alla AZ Design-stolar med tyg (Paged + Tailerd).

Kör az-smooth-mask-fabric-creator-with-check-sam3 för varje stol och sparar:
  - {brand}/Masks/{chair_name}_maskzip/mask.zip
  - {brand}/Masks/{chair_name}_maskzip/mask.png
  - {brand}/Masks/{chair_name}_maskzip/overlay.png
  - {brand}/Masks/{chair_name}_maskzip/result.json

Dubbelkollar result.json för mask_ok status.

Usage:
    python generate_masks.py           # kör alla
    python generate_masks.py --dry-run # visa vad som skulle köras
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

GDRIVE = Path(
    "/Users/andreasquensel/Library/CloudStorage/GoogleDrive-andreas@zebrolabs.com"
    "/Shared drives/Apiai.me/Customers/AZ Design/Content"
)

# Brands med tyg
BRANDS_WITH_FABRIC = ["Paged", "Tailerd"]


def get_chairs(brand: str) -> list[Path]:
    """Hämta alla stolfiler för ett varumärke."""
    chairs_dir = GDRIVE / brand / "Chairs"
    if not chairs_dir.exists():
        return []
    return sorted([
        p for p in chairs_dir.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png") and not p.name.startswith(".")
    ])


def get_mime_type(path: Path) -> str:
    """Returnera MIME-typ baserat på filändelse."""
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    elif suffix == ".png":
        return "image/png"
    return "application/octet-stream"


def run_mask_pipeline(chair_path: Path) -> tuple[bytes | None, str]:
    """Kör mask-pipeline och returnera (zip_content, error_msg)."""
    url = f"{PIPELINE_BASE}/{MASK_PIPELINE}"

    with open(chair_path, "rb") as f:
        files = [("image", (chair_path.name, f, get_mime_type(chair_path)))]
        try:
            r = requests.post(
                url,
                files=files,
                headers={"X-API-Key": API_KEY},
                timeout=300
            )
        except requests.RequestException as e:
            return None, f"Request failed: {e}"

    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"

    # Verifiera att det är en zip
    if r.content[:4] != b"PK\x03\x04":
        return None, f"Unexpected response type (not a zip)"

    return r.content, ""


def extract_and_verify(zip_content: bytes, output_dir: Path) -> dict:
    """Extrahera zip och verifiera mask_ok. Returnerar result.json innehåll."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Spara original-zip
    (output_dir / "mask.zip").write_bytes(zip_content)

    # Extrahera
    zf = zipfile.ZipFile(io.BytesIO(zip_content))
    for name in zf.namelist():
        data = zf.read(name)
        (output_dir / Path(name).name).write_bytes(data)

    # Läs result.json
    result_path = output_dir / "result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Visa vad som skulle köras")
    args = ap.parse_args()

    if not API_KEY:
        raise SystemExit("ERROR: APIAI_API_KEY not found in environment / .env")

    # Samla alla stolar
    all_chairs = []
    for brand in BRANDS_WITH_FABRIC:
        chairs = get_chairs(brand)
        for chair in chairs:
            all_chairs.append((brand, chair))

    print(f"Hittade {len(all_chairs)} stolar med tyg:\n")
    for brand, chair in all_chairs:
        print(f"  [{brand}] {chair.name}")

    if args.dry_run:
        print("\n--dry-run: Avslutar utan att köra pipelines.")
        return

    print("\n" + "="*60)
    print("Kör mask-pipeline för varje stol...")
    print("="*60 + "\n")

    results = []

    for i, (brand, chair) in enumerate(all_chairs, 1):
        chair_stem = chair.stem  # filnamn utan ändelse
        output_dir = GDRIVE / brand / "Masks" / f"{chair_stem}_maskzip"

        print(f"[{i}/{len(all_chairs)}] {brand}/{chair.name}")
        print(f"    Output: {output_dir.relative_to(GDRIVE)}")

        # Kör pipeline
        zip_content, error = run_mask_pipeline(chair)

        if error:
            print(f"    ❌ FEL: {error}")
            results.append({
                "brand": brand,
                "chair": chair.name,
                "status": "error",
                "error": error
            })
            continue

        # Extrahera och verifiera
        result_json = extract_and_verify(zip_content, output_dir)

        mask_ok = result_json.get("mask_ok", False)
        mask_area = result_json.get("mask_area_pct", 0)
        mask_drift = result_json.get("mask_drift_px", 0)
        warnings = result_json.get("mask_warnings", [])

        status_icon = "✅" if mask_ok else "⚠️"
        print(f"    {status_icon} mask_ok={mask_ok}, area={mask_area:.1f}%, drift={mask_drift:.1f}px")
        if warnings:
            print(f"    ⚠️  Varningar: {warnings}")

        results.append({
            "brand": brand,
            "chair": chair.name,
            "status": "ok" if mask_ok else "warning",
            "mask_ok": mask_ok,
            "mask_area_pct": mask_area,
            "mask_drift_px": mask_drift,
            "warnings": warnings,
            "output_dir": str(output_dir)
        })
        print()

    # Sammanfattning
    print("="*60)
    print("SAMMANFATTNING")
    print("="*60)

    ok_count = sum(1 for r in results if r.get("mask_ok"))
    warn_count = sum(1 for r in results if r["status"] == "warning")
    err_count = sum(1 for r in results if r["status"] == "error")

    print(f"  ✅ Godkända masker: {ok_count}/{len(results)}")
    if warn_count:
        print(f"  ⚠️  Masker med varning: {warn_count}")
    if err_count:
        print(f"  ❌ Fel: {err_count}")

    # Lista problem
    problems = [r for r in results if not r.get("mask_ok", False)]
    if problems:
        print("\nBehöver granskning:")
        for r in problems:
            print(f"  - [{r['brand']}] {r['chair']}: {r.get('error') or r.get('warnings')}")

    # Spara resultat till JSON
    report_path = Path(__file__).parent / "mask_generation_report.json"
    report_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nRapport sparad: {report_path}")


if __name__ == "__main__":
    main()
