#!/usr/bin/env python3
"""
AI evaluation for team logo processing pipeline.

Usage:
    python eval_heja.py --input /path/to/logos
    python eval_heja.py  # Uses defaults
"""

import argparse
import json
import os
import io
import re
import time
import base64
import html as html_module
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

# Load environment
load_dotenv()

# Defaults
DEFAULT_INPUT = "/Users/andreasquensel/Documents/Happy Art Gallery/Team Merch/Team logos"
DEFAULT_OUTPUT = "./customers/heja/results"
API_NAME = "team-logo-nb-pro"
API_BASE = "https://apiai.me/api/pipeline"
EVAL_MODEL = "gemini-2.0-flash"

EVAL_PROMPT = """You are evaluating a team logo processing pipeline. Compare the Original Logo (Image 1) with the Processed Output (Image 2).

Evaluate these criteria:

FIDELITY: Is the processed logo identical to the original in terms of colors, shapes, and text? All visual elements must match exactly. (Yes/No)

BACKGROUND: Does the logo appear cleanly isolated without any solid colored background visible behind it? There should be no obvious background color (white, colored, or textured) surrounding the logo - just the logo elements themselves. (Yes/No)

RESOLUTION: Does the processed image have at least 1,500,000 total pixels (width x height >= 1.5M)? (Yes/No) - Note: I will tell you the dimensions and total pixel count.

CLEAN_OUTPUT: Is the output free from any added text, watermarks, or artifacts that weren't in the original? Only the original logo elements should be present. (Yes/No)

Respond with ONLY valid JSON in this exact format:
{
  "FIDELITY": "Yes",
  "BACKGROUND": "Yes",
  "RESOLUTION": "Yes",
  "CLEAN_OUTPUT": "Yes",
  "verdict": "PASS",
  "reason": null
}

Set verdict to "PASS" if ALL criteria are "Yes", otherwise "FAIL" with a brief reason explaining the main issue."""


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


def call_api(image_path, api_name):
    """Call the apiai.me API and return result bytes."""
    api_key = os.getenv("APIAI_API_KEY")
    if not api_key:
        raise Exception("APIAI_API_KEY not found in environment")

    url = f"{API_BASE}/{api_name}"

    ext = Path(image_path).suffix.lower()
    mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"

    headers = {"X-API-Key": api_key}

    with open(image_path, "rb") as f:
        files = {"image": (Path(image_path).name, f, mime)}
        response = requests.post(url, files=files, headers=headers, timeout=300)

    if response.status_code != 200:
        raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")

    return response.content, response.headers.get("content-type", "image/png")


def evaluate_output(client, original_bytes, output_bytes, output_dims):
    """AI-evaluate processed output against quality criteria."""
    # Add resolution info to prompt
    total_pixels = output_dims[0] * output_dims[1]
    prompt_with_dims = EVAL_PROMPT + f"\n\nThe processed image dimensions are: {output_dims[0]}x{output_dims[1]} pixels (total: {total_pixels:,} pixels)."

    response = client.models.generate_content(
        model=EVAL_MODEL,
        contents=[
            prompt_with_dims,
            types.Part.from_bytes(data=original_bytes, mime_type="image/png"),
            types.Part.from_bytes(data=output_bytes, mime_type="image/png"),
        ]
    )

    # Parse JSON from response
    text = response.text.strip()
    # Extract JSON from markdown code block if present
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        text = match.group(1).strip()

    return json.loads(text)


def generate_eval_criteria_html(eval_data):
    """Generate HTML for AI evaluation criteria breakdown."""
    if not eval_data or eval_data.get("verdict") == "ERROR":
        return ""

    criteria = [
        ("FIDELITY", "Fidelity", "Colors, shapes, and text match original"),
        ("BACKGROUND", "Background", "Logo isolated, no visible background color"),
        ("RESOLUTION", "Resolution", "At least 1.5M total pixels"),
        ("CLEAN_OUTPUT", "Clean", "No added text or artifacts"),
    ]

    html = '<div class="eval-criteria">'
    for key, label, desc in criteria:
        val = eval_data.get(key, "")
        if val == "Yes":
            html += f'<span class="crit ok" title="{desc}">{label}</span>'
        elif val == "No":
            html += f'<span class="crit fail" title="{desc}">{label}</span>'

    reason = eval_data.get("reason")
    if reason:
        html += f'<span class="reason">{html_module.escape(str(reason))}</span>'

    html += '</div>'
    return html


def generate_html_report(results, output_dir, ai_pass_count, ai_fail_count):
    """Generate self-contained HTML report."""
    success_count = sum(1 for r in results if r["success"])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<title>Team Logo Eval - Heja</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, sans-serif; background: #f5f7fa; padding: 20px; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
header {{ background: linear-gradient(135deg, #38a169, #2f855a); color: white; padding: 40px; border-radius: 12px; margin-bottom: 30px; }}
h1 {{ font-size: 2em; margin-bottom: 10px; }}
.summary {{ background: white; padding: 25px; border-radius: 12px; margin-bottom: 30px; }}
.stats {{ display: flex; gap: 20px; flex-wrap: wrap; }}
.stat {{ background: #f7fafc; padding: 15px 25px; border-radius: 8px; text-align: center; }}
.stat h3 {{ font-size: 0.8em; color: #718096; }}
.stat .val {{ font-size: 1.8em; font-weight: bold; }}
.card {{ background: white; border-radius: 12px; margin-bottom: 20px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.card-head {{ display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }}
.card-head .name {{ font-weight: bold; }}
.gen-ok {{ color: #718096; background: #e2e8f0; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; }}
.gen-fail {{ color: #742a2a; background: #fed7d7; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; }}
.images {{ display: grid; grid-template-columns: 1fr 1fr; background: #f0f0f0; }}
.img-cell {{ padding: 20px; text-align: center; background: #e0e0e0; }}
.img-cell:first-child {{ border-right: 1px solid #ccc; }}
.img-cell h4 {{ margin-bottom: 10px; color: #4a5568; font-size: 0.85em; text-transform: uppercase; }}
.img-cell img {{ max-width: 100%; max-height: 350px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.15); cursor: pointer; }}
.img-cell .dims {{ margin-top: 8px; font-size: 0.8em; color: #718096; }}
.dl-btn {{ display: inline-block; margin-top: 8px; padding: 6px 14px; background: #38a169; color: white; border-radius: 6px; text-decoration: none; font-size: 0.8em; cursor: pointer; border: none; }}
.dl-btn:hover {{ background: #2f855a; }}
.ai-pass {{ color: #22543d; background: #9ae6b4; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: bold; }}
.ai-fail {{ color: #742a2a; background: #fc8181; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: bold; }}
.ai-error {{ color: #744210; background: #faf089; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: bold; }}
.eval-criteria {{ padding: 10px 20px; background: #f7fafc; border-top: 1px solid #e2e8f0; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
.crit {{ padding: 4px 10px; border-radius: 4px; font-size: 0.8em; }}
.crit.ok {{ background: #c6f6d5; color: #22543d; }}
.crit.fail {{ background: #fed7d7; color: #742a2a; }}
.reason {{ font-style: italic; color: #718096; font-size: 0.85em; margin-left: auto; }}
.rating {{ padding: 15px 20px; border-top: 1px solid #e2e8f0; display: flex; align-items: center; gap: 15px; }}
.rating select {{ padding: 8px 12px; border: 2px solid #e2e8f0; border-radius: 8px; }}
.rating input {{ flex: 1; padding: 8px 12px; border: 2px solid #e2e8f0; border-radius: 8px; }}
</style>
</head><body>
<div class="container">
<header>
<h1>Team Logo Pipeline Evaluation</h1>
<p>API: {API_NAME}</p>
<p>AI Model: {EVAL_MODEL}</p>
<p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
</header>
<div class="summary">
<h2>Summary</h2>
<div class="stats">
<div class="stat"><h3>Total</h3><div class="val">{len(results)}</div></div>
<div class="stat"><h3>API Success</h3><div class="val">{success_count}</div></div>
<div class="stat"><h3>API Failed</h3><div class="val">{len(results)-success_count}</div></div>
<div class="stat"><h3>AI Pass</h3><div class="val" style="color:#22543d">{ai_pass_count}</div></div>
<div class="stat"><h3>AI Fail</h3><div class="val" style="color:#742a2a">{ai_fail_count}</div></div>
<div class="stat"><h3>AI Rate</h3><div class="val">{100*ai_pass_count//(ai_pass_count+ai_fail_count) if (ai_pass_count+ai_fail_count) > 0 else 0}%</div></div>
<div class="stat"><h3>Rated</h3><div class="val" id="ratedCount">0</div></div>
<div class="stat"><h3>Avg Rating</h3><div class="val" id="avgRating">-</div></div>
</div>
<div style="margin-top:15px">
<button class="dl-btn" onclick="exportRatings()">Export Ratings</button>
<button class="dl-btn" onclick="window.print()" style="background:#4299e1">Print/PDF</button>
<button class="dl-btn" onclick="shareReport()" style="background:#805ad5">Download Report</button>
<button class="dl-btn" onclick="clearRatings()" style="background:#e53e3e">Clear</button>
</div>
<details style="margin-top:20px">
<summary style="cursor:pointer;font-weight:bold;color:#4a5568">AI Evaluation Criteria</summary>
<div style="margin-top:10px;padding:15px;background:#f7fafc;border-radius:8px;font-size:0.9em;line-height:1.8">
<strong>Fidelity:</strong> Colors, shapes, and text must match the original exactly<br>
<strong>Background:</strong> Logo cleanly isolated, no visible background color behind it<br>
<strong>Resolution:</strong> Output must have at least 1,500,000 total pixels (width x height)<br>
<strong>Clean:</strong> No added text, watermarks, or artifacts
</div>
</details>
</div>
"""

    for idx, r in enumerate(results):
        status = '<span class="gen-ok">OK</span>' if r["success"] else '<span class="gen-fail">Failed</span>'

        eval_data = r.get("eval", {})
        verdict = eval_data.get("verdict", "")
        if verdict == "PASS":
            ai_badge = '<span class="ai-pass">AI PASS</span>'
        elif verdict == "FAIL":
            ai_badge = '<span class="ai-fail">AI FAIL</span>'
        elif verdict == "ERROR":
            ai_badge = '<span class="ai-error">AI ERROR</span>'
        else:
            ai_badge = ''

        output_cell = ""
        if r["success"]:
            output_cell = f"""<img src="{r["output_b64"]}" onclick="window.open(this.src)">
<div class="dims">{r["output_dims"][0]}x{r["output_dims"][1]}</div>
<button class="dl-btn" onclick="download(this, '{Path(r["filename"]).stem}_processed.png')">Download</button>"""
        else:
            output_cell = f'<p style="color:red">{html_module.escape(r.get("error",""))}</p><div class="dims">-</div>'

        html += f"""
<div class="card">
<div class="card-head">
<span class="name">{html_module.escape(r["filename"])}</span>
{status}
{ai_badge}
<span>{r["exec_time"]:.1f}s</span>
</div>
<div class="images">
<div class="img-cell"><h4>Original</h4><img src="{r["original_b64"]}"><div class="dims">{r["original_dims"][0]}x{r["original_dims"][1]}</div></div>
<div class="img-cell"><h4>Processed</h4>{output_cell}</div>
</div>
{generate_eval_criteria_html(eval_data) if eval_data else ''}
<div class="rating">
<span>Rating:</span>
<select id="rating-{idx}" onchange="saveRating({idx})"><option value="">-</option><option value="5">5 Perfect</option><option value="4">4 Good</option><option value="3">3 OK</option><option value="2">2 Poor</option><option value="1">1 Failed</option></select>
<input type="text" id="notes-{idx}" placeholder="Notes..." onchange="saveRating({idx})">
</div>
</div>
"""

    html += f"""
<script>
const STORAGE_KEY = 'eval_heja_{timestamp}';

window.onload = function() {{ loadRatings(); updateStats(); }};

function saveRating(idx) {{
    const ratings = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');
    const rating = document.getElementById('rating-' + idx).value;
    const notes = document.getElementById('notes-' + idx).value;
    if (rating || notes) {{ ratings[idx] = {{ rating: rating, notes: notes }}; }}
    else {{ delete ratings[idx]; }}
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ratings));
    updateStats();
}}

function loadRatings() {{
    const ratings = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');
    for (const [idx, data] of Object.entries(ratings)) {{
        const sel = document.getElementById('rating-' + idx);
        const notes = document.getElementById('notes-' + idx);
        if (sel && data.rating) sel.value = data.rating;
        if (notes && data.notes) notes.value = data.notes;
    }}
}}

function updateStats() {{
    const ratings = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');
    let count = 0, sum = 0;
    for (const data of Object.values(ratings)) {{
        if (data.rating) {{ count++; sum += parseInt(data.rating); }}
    }}
    document.getElementById('ratedCount').textContent = count;
    document.getElementById('avgRating').textContent = count > 0 ? (sum / count).toFixed(1) : '-';
}}

function download(btn, filename) {{
    const img = btn.parentElement.querySelector('img');
    const a = document.createElement('a');
    a.href = img.src; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
}}

function exportRatings() {{
    const ratings = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');
    const blob = new Blob([JSON.stringify(ratings, null, 2)], {{type: 'application/json'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'heja_ratings.json'; a.click();
}}

function clearRatings() {{
    if (confirm('Clear all ratings?')) {{ localStorage.removeItem(STORAGE_KEY); location.reload(); }}
}}

function shareReport() {{
    const blob = new Blob([document.documentElement.outerHTML], {{type: 'text/html'}});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'eval_{output_dir.name}.html';
    a.click();
}}
</script>
</div></body></html>"""

    report_path = output_dir / f"eval_{output_dir.name}.html"
    with open(report_path, "w") as f:
        f.write(html)

    return report_path


def main():
    parser = argparse.ArgumentParser(description="Evaluate team logo processing pipeline")
    parser.add_argument("--input", "-i", default=DEFAULT_INPUT, help="Input folder with logos")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="Output directory")
    args = parser.parse_args()

    # Get API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in environment or .env file")
        return

    # Setup paths
    input_path = Path(args.input)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) / f"team_logo_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize Gemini client
    client = genai.Client(api_key=api_key)

    # Get input images
    images = []
    for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
        images.extend(input_path.glob(ext))
    images = sorted(images)

    print(f"Input: {input_path}")
    print(f"Found {len(images)} images")
    print(f"API: {API_NAME}")
    print(f"Eval Model: {EVAL_MODEL}")
    print(f"Output: {output_dir}\n")

    if not images:
        print("ERROR: No images found")
        return

    results = []

    for idx, img_path in enumerate(images, 1):
        filename = img_path.name
        print(f"[{idx}/{len(images)}] {filename}...", end=" ", flush=True)

        start = time.time()

        try:
            # Load original
            with open(img_path, "rb") as f:
                original_bytes = f.read()
            original_img = Image.open(io.BytesIO(original_bytes))
            original_dims = original_img.size

            # Call API
            output_bytes, content_type = call_api(img_path, API_NAME)
            exec_time = time.time() - start

            # Get output dimensions
            output_img = Image.open(io.BytesIO(output_bytes))
            output_dims = list(output_img.size)

            # Save output
            out_path = output_dir / f"{img_path.stem}_processed.png"
            with open(out_path, "wb") as f:
                f.write(output_bytes)

            print(f"OK ({exec_time:.1f}s) - {original_dims[0]}x{original_dims[1]} -> {output_dims[0]}x{output_dims[1]}", end=" ", flush=True)

            # AI evaluation
            print("| eval...", end=" ", flush=True)
            try:
                eval_result = evaluate_output(client, original_bytes, output_bytes, output_dims)
                print(f"AI: {eval_result.get('verdict', 'ERROR')}")
            except Exception as e:
                eval_result = {"verdict": "ERROR", "reason": str(e)}
                print(f"AI: ERROR ({e})")

            results.append({
                "filename": filename,
                "original_b64": bytes_to_base64(original_bytes, "image/png"),
                "original_dims": original_dims,
                "output_b64": bytes_to_base64(output_bytes, "image/png"),
                "output_dims": output_dims,
                "exec_time": exec_time,
                "success": True,
                "error": None,
                "eval": eval_result
            })

        except Exception as e:
            exec_time = time.time() - start
            print(f"FAILED - {e}")

            # Still try to load original for display
            try:
                with open(img_path, "rb") as f:
                    original_bytes = f.read()
                original_img = Image.open(io.BytesIO(original_bytes))
                original_dims = original_img.size
                original_b64 = bytes_to_base64(original_bytes, "image/png")
            except:
                original_dims = [0, 0]
                original_b64 = ""

            results.append({
                "filename": filename,
                "original_b64": original_b64,
                "original_dims": original_dims,
                "output_b64": "",
                "output_dims": [0, 0],
                "exec_time": exec_time,
                "success": False,
                "error": str(e),
                "eval": {}
            })

    # Calculate stats
    ai_pass = sum(1 for r in results if r.get("eval", {}).get("verdict") == "PASS")
    ai_fail = sum(1 for r in results if r.get("eval", {}).get("verdict") == "FAIL")

    # Generate report
    print("\nGenerating HTML report...")
    report_path = generate_html_report(results, output_dir, ai_pass, ai_fail)

    # Save JSON results
    json_path = output_dir / "results.json"
    with open(json_path, "w") as f:
        # Don't include base64 in JSON (too large)
        json_results = [{k: v for k, v in r.items() if not k.endswith("_b64")} for r in results]
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "api": API_NAME,
            "eval_model": EVAL_MODEL,
            "input_dir": str(input_path),
            "total": len(results),
            "api_success": sum(1 for r in results if r["success"]),
            "ai_pass": ai_pass,
            "ai_fail": ai_fail,
            "results": json_results
        }, f, indent=2)

    success_count = sum(1 for r in results if r["success"])
    print(f"\n{'='*60}")
    print(f"API: {success_count}/{len(results)} successful")
    print(f"AI Eval: {ai_pass} PASS, {ai_fail} FAIL ({100*ai_pass//(ai_pass+ai_fail) if (ai_pass+ai_fail) > 0 else 0}%)")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
