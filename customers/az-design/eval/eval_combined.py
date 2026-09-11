#!/usr/bin/env python3
"""
Combined evaluation: change chair colour, then change fabric.

Flow:
1. Base chair + colour sample → change-colour-of-chair → Chair with new wood
2. Generated chair + fabric sample → change-colour-of-fabric → Final variant

Usage:
    python eval_combined.py --brand Tailerd --chair black_chair --limit-colours 1 --limit-fabrics 1
    python eval_combined.py --brand Tailerd --chair black_chair  # Full run
"""

import argparse
import json
import os
import io
import re
import tempfile
import time
import base64
import html as html_module
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image

# Load environment
load_dotenv()

# Google Drive base path
GDRIVE_BASE = "/Users/andreasquensel/Library/CloudStorage/GoogleDrive-andreas@zebrolabs.com/Shared drives/Apiai.me/Customers/AZ Design"
CONTENT_PATH = Path(GDRIVE_BASE) / "Content"
EVALS_PATH = Path(GDRIVE_BASE) / "Evals"

# Pipelines
COLOUR_PIPELINE = "change-colour-of-chair"
FABRIC_PIPELINE = "change-colour-of-fabric"
COLOUR_URL = f"https://apiai.me/api/pipeline/{COLOUR_PIPELINE}"
FABRIC_URL = f"https://apiai.me/api/pipeline/{FABRIC_PIPELINE}"

# Evaluation via apiai.me process API
EVAL_URL = "https://apiai.me/api/process/gemini-3-1-flash-lite-preview"
MAX_RETRIES = 3
RETRY_DELAY = 30

# Eval prompt for combined result
EVAL_PROMPT = """As a professional product photography auditor, evaluate this chair variant creation.

You are given:
- Image 1: Original chair (reference for shape/geometry)
- Image 2: Wood colour sample (reference for wood color)
- Image 3: Fabric sample (reference for fabric color/pattern)
- Image 4: Final generated output

Evaluate these criteria (score 1-10, where 1=perfect, 10=severely wrong):

1. GEOMETRY: Chair shape/structure identical to Image 1
   - Score 1-2: Perfect match
   - Score 5+: Noticeable shape changes

2. COLOUR: Wood/frame colour matches sample (Image 2) in hue, saturation, temperature
   - Score 1-2: Good colour match
   - Score 5+: Wrong colour family

3. FABRIC: The upholstery in Image 4 (output) should match the FABRIC SAMPLE in Image 3.
   IMPORTANT: Do NOT compare to the original fabric in Image 1 - the fabric is SUPPOSED to change!
   Compare ONLY Image 3 (fabric sample) with the upholstery in Image 4 (output).
   - Score 1-2: Output fabric matches the sample (Image 3) in color and texture
   - Score 5+: Output fabric color differs noticeably from sample (Image 3)
   - Score 8-10: Completely wrong color family compared to sample (Image 3)

4. FABRIC_AREA: All upholstered areas from Image 1 remain as fabric (not converted to wood)
   - Score 1-2: All fabric areas preserved
   - Score 8-10: Fabric areas converted to wood - CRITICAL ERROR

5. BACKGROUND: Should appear white
   - Score 1-2: White background
   - Score 5+: Noticeably gray or colored

6. BOUNDARY: Wood/fabric boundaries match Image 1
   - Score 1-2: Boundaries preserved
   - Score 5+: New borders or trim added

Respond with ONLY valid JSON:
{
  "geometry": 1,
  "colour": 1,
  "fabric": 1,
  "fabric_area": 1,
  "background": 1,
  "boundary": 1,
  "max_score": 1,
  "verdict": "PASS",
  "reason": null
}

RULES:
- max_score = highest of all scores
- verdict = "PASS" if max_score < 5, else "FAIL"
- reason = brief explanation if any score >= 3, else null"""


def image_to_base64(path):
    """Convert image file to base64 data URI."""
    with open(path, "rb") as f:
        data = f.read()
    ext = Path(path).suffix.lower()
    mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def bytes_to_base64(data, mime="image/png"):
    """Convert bytes to base64 data URI."""
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def call_colour_pipeline(api_key, chair_bytes, colour_bytes, has_fabric=True):
    """Call change-colour-of-chair pipeline."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f1:
        f1.write(chair_bytes)
        chair_path = f1.name
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f2:
        f2.write(colour_bytes)
        colour_path = f2.name

    try:
        with open(chair_path, "rb") as f1, open(colour_path, "rb") as f2:
            if has_fabric:
                files = [
                    ("image", ("chair.jpg", f1, "image/jpeg")),
                    ("image", ("colour.jpg", f2, "image/jpeg")),
                ]
            else:
                files = [
                    ("image", ("colour.jpg", f2, "image/jpeg")),
                    ("image", ("chair.jpg", f1, "image/jpeg")),
                ]
            response = requests.post(
                COLOUR_URL,
                files=files,
                headers={"X-API-Key": api_key},
                timeout=120
            )

        if response.status_code != 200:
            return None, f"Colour API error: {response.status_code}"

        if "image" in response.headers.get("Content-Type", ""):
            return response.content, None
        else:
            return None, "Unexpected response format"
    finally:
        os.unlink(chair_path)
        os.unlink(colour_path)


def call_fabric_pipeline(api_key, chair_bytes, fabric_bytes):
    """Call change-colour-of-fabric pipeline."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1:
        f1.write(chair_bytes)
        chair_path = f1.name
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f2:
        f2.write(fabric_bytes)
        fabric_path = f2.name

    try:
        with open(chair_path, "rb") as f1, open(fabric_path, "rb") as f2:
            files = [
                ("image", ("chair.png", f1, "image/png")),
                ("image", ("fabric.jpg", f2, "image/jpeg")),
            ]
            response = requests.post(
                FABRIC_URL,
                files=files,
                headers={"X-API-Key": api_key},
                timeout=120
            )

        if response.status_code != 200:
            return None, f"Fabric API error: {response.status_code}"

        if "image" in response.headers.get("Content-Type", ""):
            return response.content, None
        else:
            return None, "Unexpected response format"
    finally:
        os.unlink(chair_path)
        os.unlink(fabric_path)


def evaluate_combined(api_key, original_bytes, colour_bytes, fabric_bytes, output_bytes):
    """Evaluate combined result with 4 images."""
    temps = []
    try:
        for data, suffix in [(original_bytes, ".png"), (colour_bytes, ".jpg"),
                              (fabric_bytes, ".jpg"), (output_bytes, ".png")]:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(data)
                temps.append(f.name)

        with open(temps[0], "rb") as f1, open(temps[1], "rb") as f2, \
             open(temps[2], "rb") as f3, open(temps[3], "rb") as f4:
            files = [
                ("image", ("original.png", f1, "image/png")),
                ("image", ("colour.jpg", f2, "image/jpeg")),
                ("image", ("fabric.jpg", f3, "image/jpeg")),
                ("image", ("output.png", f4, "image/png")),
            ]
            response = requests.post(
                EVAL_URL,
                files=files,
                data={"prompt": EVAL_PROMPT},
                headers={"X-API-Key": api_key},
                timeout=60
            )

        if response.status_code != 200:
            return {"verdict": "ERROR", "reason": f"API {response.status_code}"}

        resp_json = response.json()
        text = resp_json.get("text", response.text).strip()

        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if match:
            text = match.group(1).strip()

        return json.loads(text)
    except Exception as e:
        return {"verdict": "ERROR", "reason": str(e)[:100]}
    finally:
        for t in temps:
            try:
                os.unlink(t)
            except:
                pass


def generate_eval_criteria_html(eval_data):
    """Generate HTML for evaluation criteria."""
    if not eval_data or eval_data.get("verdict") == "ERROR":
        return ""

    criteria = [
        ("geometry", "Geometry", "Chair shape"),
        ("colour", "Colour", "Wood colour match"),
        ("fabric", "Fabric", "Fabric colour match"),
        ("fabric_area", "FabricArea", "Fabric areas preserved"),
        ("background", "BG", "Background"),
        ("boundary", "Edge", "Boundaries"),
    ]

    html = '<div class="eval-criteria">'
    for key, label, desc in criteria:
        score = eval_data.get(key)
        if score is not None and isinstance(score, (int, float)):
            if score <= 2:
                css_class = "ok"
            elif score <= 4:
                css_class = "warn"
            else:
                css_class = "fail"
            html += f'<span class="crit {css_class}" title="{desc}: {score}/10">{label}:{score}</span>'

    max_score = eval_data.get("max_score", 0)
    html += f'<span class="max-score">Max:{max_score}</span>'

    reason = eval_data.get("reason")
    if reason:
        html += f'<span class="reason">{html_module.escape(str(reason))}</span>'

    html += '</div>'
    return html


def generate_html_report(results, base_b64, base_dims, base_name, output_dir):
    """Generate HTML report for combined eval."""
    success_count = sum(1 for r in results if r["success"])
    ai_pass = sum(1 for r in results if r.get("eval", {}).get("verdict") == "PASS")
    ai_fail = sum(1 for r in results if r.get("eval", {}).get("verdict") == "FAIL")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<title>Combined Eval - {base_name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, sans-serif; background: #f5f7fa; padding: 20px; }}
.container {{ max-width: 1800px; margin: 0 auto; }}
header {{ background: linear-gradient(135deg, #f093fb, #f5576c); color: white; padding: 40px; border-radius: 12px; margin-bottom: 30px; }}
h1 {{ font-size: 2em; margin-bottom: 10px; }}
.summary {{ background: white; padding: 25px; border-radius: 12px; margin-bottom: 30px; }}
.stats {{ display: flex; gap: 20px; flex-wrap: wrap; }}
.stat {{ background: #f7fafc; padding: 15px 25px; border-radius: 8px; text-align: center; }}
.stat h3 {{ font-size: 0.8em; color: #718096; }}
.stat .val {{ font-size: 1.8em; font-weight: bold; }}
.card {{ background: white; border-radius: 12px; margin-bottom: 20px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.card-head {{ display: grid; grid-template-columns: repeat(5, 1fr); padding: 15px 20px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; align-items: center; }}
.card-head .name {{ font-weight: bold; }}
.card-head .col {{ text-align: center; }}
.card-head .col-right {{ text-align: right; }}
.gen-ok {{ color: #22543d; background: #c6f6d5; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; }}
.gen-fail {{ color: #742a2a; background: #fed7d7; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; }}
.images {{ display: grid; grid-template-columns: repeat(5, 1fr); background: #ffffff; }}
.img-cell {{ padding: 15px; text-align: center; border-right: 1px solid #e2e8f0; background: #ffffff; }}
.img-cell:last-child {{ border-right: none; }}
.img-cell h4 {{ margin-bottom: 8px; color: #4a5568; font-size: 0.75em; text-transform: uppercase; }}
.img-cell img {{ max-width: 100%; max-height: 250px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); cursor: pointer; }}
.img-cell .dims {{ margin-top: 6px; font-size: 0.75em; color: #718096; }}
.dl-btn {{ display: inline-block; margin-top: 6px; padding: 4px 10px; background: #f093fb; color: white; border-radius: 6px; text-decoration: none; font-size: 0.75em; cursor: pointer; border: none; }}
.ai-pass {{ color: #22543d; background: #9ae6b4; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: bold; }}
.ai-fail {{ color: #742a2a; background: #fc8181; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: bold; }}
.ai-error {{ color: #744210; background: #faf089; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: bold; }}
.eval-criteria {{ padding: 10px 20px; background: #f7fafc; border-top: 1px solid #e2e8f0; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
.crit {{ padding: 4px 10px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
.crit.ok {{ background: #c6f6d5; color: #22543d; }}
.crit.warn {{ background: #fef3c7; color: #92400e; }}
.crit.fail {{ background: #fed7d7; color: #742a2a; }}
.max-score {{ padding: 4px 10px; border-radius: 4px; font-size: 0.8em; background: #e2e8f0; color: #4a5568; font-weight: bold; }}
.reason {{ font-style: italic; color: #718096; font-size: 0.85em; margin-left: auto; }}
</style>
</head><body>
<div class="container">
<header>
<h1>Combined Variant Evaluation</h1>
<p>Colour → Fabric Pipeline</p>
<p>Base: {base_name}</p>
<p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
</header>
<div class="summary">
<h2>Summary</h2>
<div class="stats">
<div class="stat"><h3>Total</h3><div class="val">{len(results)}</div></div>
<div class="stat"><h3>Success</h3><div class="val">{success_count}</div></div>
<div class="stat"><h3>Failed</h3><div class="val">{len(results)-success_count}</div></div>
<div class="stat"><h3>AI Pass</h3><div class="val" style="color:#22543d">{ai_pass}</div></div>
<div class="stat"><h3>AI Fail</h3><div class="val" style="color:#742a2a">{ai_fail}</div></div>
<div class="stat"><h3>AI Rate</h3><div class="val">{100*ai_pass//(ai_pass+ai_fail) if (ai_pass+ai_fail) > 0 else 0}%</div></div>
</div>
<div style="margin-top:15px">
<button class="dl-btn" onclick="window.print()">Print/PDF</button>
<button class="dl-btn" onclick="shareReport()">Download Report</button>
</div>
</div>
"""

    for idx, r in enumerate(results):
        # Status badge for colour step (After Colour)
        if r.get("mid_b64"):
            colour_status = '<span class="gen-ok">Succeeded</span>'
        else:
            colour_status = '<span class="gen-fail">Failed</span>'

        # AI badge for final result
        eval_data = r.get("eval", {})
        verdict = eval_data.get("verdict", "")
        if verdict == "PASS":
            ai_badge = '<span class="ai-pass">AI PASS</span>'
        elif verdict == "FAIL":
            ai_badge = '<span class="ai-fail">AI FAIL</span>'
        elif verdict == "ERROR":
            ai_badge = '<span class="ai-error">AI ERROR</span>'
        elif not r["success"]:
            ai_badge = '<span class="gen-fail">Failed</span>'
        else:
            ai_badge = ''

        # Build image cells
        mid_cell = ""
        if r.get("mid_b64"):
            mid_cell = f"<img src='{r['mid_b64']}' onclick='window.open(this.src)'><div class='dims'>{r['mid_dims'][0]}x{r['mid_dims'][1]}</div>"
        else:
            mid_cell = f"<p style='color:orange'>Colour step failed</p>"

        out_cell = ""
        if r["success"]:
            vname = r["variant_name"]
            out_cell = f"<img src='{r['output_b64']}' onclick='window.open(this.src)'><div class='dims'>{r['output_dims'][0]}x{r['output_dims'][1]}</div><button class='dl-btn' onclick='download(this, \"{vname}\")'>Download</button>"
        else:
            out_cell = f"<p style='color:red'>{html_module.escape(r.get('error',''))}</p>"

        html += f"""
<div class="card">
<div class="card-head">
<span class="name">{html_module.escape(r["variant_name"])}</span>
<span class="col"></span>
<span class="col">{colour_status}</span>
<span class="col"></span>
<span class="col-right">{ai_badge} <span style="color:#718096;font-size:0.85em">{r["exec_time"]:.1f}s</span></span>
</div>
<div class="images">
<div class="img-cell"><h4>Original</h4><img src="{base_b64}"><div class="dims">{base_dims[0]}x{base_dims[1]}</div></div>
<div class="img-cell"><h4>Colour Sample</h4><img src="{r['colour_b64']}"><div class="dims">{r['colour_dims'][0]}x{r['colour_dims'][1]}</div></div>
<div class="img-cell"><h4>After Colour</h4>{mid_cell}</div>
<div class="img-cell"><h4>Fabric Sample</h4><img src="{r['fabric_b64']}"><div class="dims">{r['fabric_dims'][0]}x{r['fabric_dims'][1]}</div></div>
<div class="img-cell"><h4>Final Output</h4>{out_cell}</div>
</div>
{generate_eval_criteria_html(eval_data) if eval_data else ''}
</div>
"""

    html += f"""
<script>
function download(btn, filename) {{
    const img = btn.parentElement.querySelector('img');
    const a = document.createElement('a');
    a.href = img.src; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
}}
function shareReport() {{
    const blob = new Blob([document.documentElement.outerHTML], {{type: 'text/html'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'eval_{output_dir.name}.html';
    a.click();
}}
</script>
</div></body></html>"""

    report_path = output_dir / f"eval_{output_dir.name}.html"
    with open(report_path, "w") as f:
        f.write(html)

    return report_path


def brand_has_fabric(brand_name):
    """Check if a brand has a Fabric folder."""
    fabric_path = CONTENT_PATH / brand_name / "Fabric"
    return fabric_path.exists()


def list_brands():
    """List available brands."""
    brands = []
    for p in CONTENT_PATH.iterdir():
        if p.is_dir() and not p.name.startswith('.'):
            brands.append(p.name)
    return sorted(brands)


def list_chairs(brand):
    """List available chairs for a brand."""
    chairs_path = CONTENT_PATH / brand / "Chairs"
    if not chairs_path.exists():
        return []
    return sorted([p.stem for p in chairs_path.iterdir() if p.suffix.lower() in ['.png', '.jpg', '.jpeg']])


def get_colours(brand):
    """Get colour samples for a brand."""
    colours_path = CONTENT_PATH / brand / "Colours"
    if not colours_path.exists():
        return []
    return sorted([p for p in colours_path.iterdir() if p.suffix.lower() in ['.png', '.jpg', '.jpeg']], key=lambda x: x.name)


def get_fabrics(brand):
    """Get fabric samples for a brand."""
    fabrics_path = CONTENT_PATH / brand / "Fabric"
    if not fabrics_path.exists():
        return []
    return sorted([p for p in fabrics_path.iterdir() if p.suffix.lower() in ['.png', '.jpg', '.jpeg']], key=lambda x: x.name)


def run_eval(brand, chair_name, api_key, limit_colours=None, limit_fabrics=None):
    """Run combined evaluation."""
    has_fabric = brand_has_fabric(brand)

    # Find chair image
    chairs_path = CONTENT_PATH / brand / "Chairs"
    chair_path = None
    for ext in ['.png', '.jpg', '.jpeg']:
        p = chairs_path / f"{chair_name}{ext}"
        if p.exists():
            chair_path = p
            break

    if not chair_path:
        print(f"ERROR: Chair not found: {chair_name}")
        return

    # Get colours and fabrics
    colours = get_colours(brand)
    fabrics = get_fabrics(brand)

    if not colours:
        print(f"ERROR: No colours found for {brand}")
        return
    if not fabrics:
        print(f"ERROR: No fabrics found for {brand}")
        return

    if limit_colours:
        colours = colours[:limit_colours]
    if limit_fabrics:
        fabrics = fabrics[:limit_fabrics]

    # Setup output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = EVALS_PATH / f"combined_{brand.lower()}_{chair_name.lower()}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load base chair
    with open(chair_path, "rb") as f:
        base_bytes = f.read()
    base_img = Image.open(io.BytesIO(base_bytes))
    base_dims = base_img.size
    base_b64 = image_to_base64(str(chair_path))

    total_variants = len(colours) * len(fabrics)
    print(f"\n{'='*60}")
    print(f"Brand: {brand}")
    print(f"Chair: {chair_name} ({base_dims[0]}x{base_dims[1]})")
    print(f"Colours: {len(colours)}, Fabrics: {len(fabrics)}")
    print(f"Total variants: {total_variants}")
    print(f"Has Fabric folder: {has_fabric}")
    print(f"Output: {output_dir}")
    print(f"{'='*60}\n")

    results = []
    variant_idx = 0

    for colour_path in colours:
        # Load colour sample
        with open(colour_path, "rb") as f:
            colour_bytes = f.read()
        colour_img = Image.open(io.BytesIO(colour_bytes))
        colour_dims = colour_img.size
        colour_b64 = image_to_base64(str(colour_path))

        # Step 1: Change colour
        print(f"[Colour] {colour_path.name}...", end=" ", flush=True)
        start = time.time()

        mid_bytes, colour_error = call_colour_pipeline(api_key, base_bytes, colour_bytes, has_fabric)

        if not mid_bytes:
            print(f"FAILED - {colour_error}")
            # Skip all fabrics for this colour
            for fabric_path in fabrics:
                variant_idx += 1
                results.append({
                    "variant_name": f"{colour_path.stem}_{fabric_path.stem}.png",
                    "colour_b64": colour_b64,
                    "colour_dims": colour_dims,
                    "fabric_b64": image_to_base64(str(fabric_path)),
                    "fabric_dims": Image.open(fabric_path).size,
                    "mid_b64": "",
                    "mid_dims": [0, 0],
                    "output_b64": "",
                    "output_dims": [0, 0],
                    "exec_time": time.time() - start,
                    "success": False,
                    "error": colour_error,
                    "eval": {}
                })
            continue

        mid_img = Image.open(io.BytesIO(mid_bytes))
        mid_dims = list(mid_img.size)
        mid_b64 = bytes_to_base64(mid_bytes)
        colour_time = time.time() - start
        print(f"OK ({colour_time:.1f}s)")

        # Step 2: Change fabric for each fabric sample
        for fabric_path in fabrics:
            variant_idx += 1
            variant_name = f"{colour_path.stem}_{fabric_path.stem}.png"

            with open(fabric_path, "rb") as f:
                fabric_bytes = f.read()
            fabric_img = Image.open(io.BytesIO(fabric_bytes))
            fabric_dims = fabric_img.size
            fabric_b64 = image_to_base64(str(fabric_path))

            print(f"  [{variant_idx}/{total_variants}] + {fabric_path.name}...", end=" ", flush=True)
            start = time.time()

            output_bytes, fabric_error = call_fabric_pipeline(api_key, mid_bytes, fabric_bytes)
            exec_time = colour_time + (time.time() - start)

            if not output_bytes:
                print(f"FAILED - {fabric_error}")
                results.append({
                    "variant_name": variant_name,
                    "colour_b64": colour_b64,
                    "colour_dims": colour_dims,
                    "fabric_b64": fabric_b64,
                    "fabric_dims": fabric_dims,
                    "mid_b64": mid_b64,
                    "mid_dims": mid_dims,
                    "output_b64": "",
                    "output_dims": [0, 0],
                    "exec_time": exec_time,
                    "success": False,
                    "error": fabric_error,
                    "eval": {}
                })
                continue

            output_img = Image.open(io.BytesIO(output_bytes))
            output_dims = list(output_img.size)

            # Save output
            out_path = output_dir / variant_name
            with open(out_path, "wb") as f:
                f.write(output_bytes)

            print(f"OK ({exec_time:.1f}s)", end=" ", flush=True)

            # Evaluate
            print("| eval...", end=" ", flush=True)
            eval_result = evaluate_combined(api_key, base_bytes, colour_bytes, fabric_bytes, output_bytes)
            verdict = eval_result.get("verdict", "ERROR")
            print(f"AI: {verdict}")

            results.append({
                "variant_name": variant_name,
                "colour_b64": colour_b64,
                "colour_dims": colour_dims,
                "fabric_b64": fabric_b64,
                "fabric_dims": fabric_dims,
                "mid_b64": mid_b64,
                "mid_dims": mid_dims,
                "output_b64": bytes_to_base64(output_bytes),
                "output_dims": output_dims,
                "exec_time": exec_time,
                "success": True,
                "error": None,
                "eval": eval_result
            })

    # Generate report
    print("\nGenerating HTML report...")
    report_path = generate_html_report(results, base_b64, base_dims, chair_path.name, output_dir)

    # Save JSON
    json_path = output_dir / "results.json"
    with open(json_path, "w") as f:
        json_results = [{k: v for k, v in r.items() if not k.endswith("_b64")} for r in results]
        json.dump({
            "brand": brand,
            "chair": chair_name,
            "colours": [c.name for c in colours],
            "fabrics": [f.name for f in fabrics],
            "timestamp": datetime.now().isoformat(),
            "results": json_results
        }, f, indent=2)

    # Summary
    success_count = sum(1 for r in results if r["success"])
    ai_pass = sum(1 for r in results if r.get("eval", {}).get("verdict") == "PASS")
    ai_fail = sum(1 for r in results if r.get("eval", {}).get("verdict") == "FAIL")

    print(f"\n{'='*60}")
    print(f"DONE: {success_count}/{len(results)} successful")
    print(f"AI Eval: {ai_pass} PASS, {ai_fail} FAIL ({100*ai_pass//(ai_pass+ai_fail) if (ai_pass+ai_fail) > 0 else 0}%)")
    print(f"Report: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Combined colour + fabric evaluation")
    parser.add_argument("--brand", "-b", required=True, help="Brand name")
    parser.add_argument("--chair", "-c", required=True, help="Chair name")
    parser.add_argument("--limit-colours", "-lc", type=int, help="Limit number of colours")
    parser.add_argument("--limit-fabrics", "-lf", type=int, help="Limit number of fabrics")
    parser.add_argument("--list", "-l", action="store_true", help="List available options")
    args = parser.parse_args()

    api_key = os.getenv("APIAI_API_KEY")
    if not api_key:
        print("ERROR: APIAI_API_KEY not found")
        return

    if args.list:
        print(f"\nBrand: {args.brand}")
        print(f"Chairs: {', '.join(list_chairs(args.brand))}")
        print(f"Colours: {len(get_colours(args.brand))}")
        print(f"Fabrics: {len(get_fabrics(args.brand))}")
        return

    run_eval(args.brand, args.chair, api_key, args.limit_colours, args.limit_fabrics)


if __name__ == "__main__":
    main()
