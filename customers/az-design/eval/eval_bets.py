#!/usr/bin/env python3
"""
Evaluate chair wood stain (bets/colours) variants via apiai.me pipelines.

Usage:
    python eval_bets.py                           # Interactive mode - select brand and chair
    python eval_bets.py --brand Pedrali           # Select brand, list chairs
    python eval_bets.py --brand Pedrali --chair "Stol Dome"  # Run specific eval
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
# Generation via apiai.me pipelines
GEN_PIPELINE_WITH_FABRIC = "change-colour-of-chair"
GEN_PIPELINE_WITHOUT_FABRIC = "change-colour-of-chair-without-fabric"
GEN_URL_WITH_FABRIC = f"https://apiai.me/api/pipeline/{GEN_PIPELINE_WITH_FABRIC}"
GEN_URL_WITHOUT_FABRIC = f"https://apiai.me/api/pipeline/{GEN_PIPELINE_WITHOUT_FABRIC}"

# Evaluation via apiai.me process API
EVAL_URL = "https://apiai.me/api/process/gemini-3-1-flash-lite-preview"
MAX_RETRIES = 3
RETRY_DELAY = 30  # seconds

# Eval prompt for chairs WITH fabric
EVAL_PROMPT_WITH_FABRIC = """As a professional product photography auditor, compare the Generated Output (Image 3) against the Reference Chair (Image 1) and the Colour Sample (Image 2).

For each criterion, provide:
- Score 1-10 where 1 = perfect match, 10 = severely wrong
- Only score 5+ if a typical human would notice the issue at normal viewing distance

CRITERIA:
1. GEOMETRY: Chair shape/structure identical to Image 1
2. COLOUR: Material colour matches sample (Image 2) in hue, saturation, temperature
3. MATERIAL: Realistic material texture with appropriate 3D lighting and shadows
4. FABRIC: All upholstered/fabric areas from Image 1 must remain as fabric in Image 3.
   - Score 1-2: All fabric areas preserved exactly as in original
   - Score 7-10: ANY fabric area has been converted to wood/material - this is a CRITICAL ERROR
   - Check specifically: seat cushion, backrest padding, armrest padding - if ANY of these were fabric in Image 1 but are now wood/material in Image 3, score 8+
5. BACKGROUND: Should appear white to a human viewer.
   - Score 1-2: Appears white (minor technical variations OK)
   - Score 3-4: Slightly off-white but acceptable
   - Score 5-6: Noticeably gray - a human would say "that's not white"
   - Score 7+: Obviously gray or colored background
6. BOUNDARY: The spatial relationship between material and fabric must be IDENTICAL to Image 1.
   - Score 1-2: Edge-work matches original exactly
   - Score 5+: Any new borders, frames, or trim that didn't exist in original

Respond with ONLY valid JSON:
{
  "geometry": 1,
  "colour": 1,
  "material": 1,
  "fabric": 1,
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

# Eval prompt for chairs WITHOUT fabric
EVAL_PROMPT_WITHOUT_FABRIC = """As a professional product photography auditor, compare the Generated Output (Image 3) against the Reference Chair (Image 1) and the Colour Sample (Image 2).

For each criterion, provide:
- Score 1-10 where 1 = perfect match, 10 = severely wrong
- Only score 5+ if a typical human would notice the issue at normal viewing distance

CRITERIA:
1. GEOMETRY: Chair shape/structure identical to Image 1
2. COLOUR: Material colour matches sample (Image 2) in hue, saturation, temperature
3. MATERIAL: Realistic material texture with appropriate 3D lighting and shadows
4. BACKGROUND: Should appear white to a human viewer.
   - Score 1-2: Appears white (minor technical variations OK)
   - Score 3-4: Slightly off-white but acceptable
   - Score 5-6: Noticeably gray - a human would say "that's not white"
   - Score 7+: Obviously gray or colored background

Respond with ONLY valid JSON:
{
  "geometry": 1,
  "colour": 1,
  "material": 1,
  "background": 1,
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


def brand_has_fabric(brand_name):
    """Check if a brand has a Fabric folder."""
    fabric_path = CONTENT_PATH / brand_name / "Fabric"
    return fabric_path.exists()


def generate_via_apiai(api_key, base_bytes, variant_bytes, has_fabric=True, max_retries=MAX_RETRIES):
    """Generate image via apiai.me pipeline with retry logic."""
    # Save bytes to temp files for upload
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f1:
        f1.write(base_bytes)
        base_path = f1.name
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f2:
        f2.write(variant_bytes)
        variant_path = f2.name

    def cleanup():
        for p in [base_path, variant_path]:
            try:
                os.unlink(p)
            except OSError:
                pass

    last_error = None

    # Select pipeline based on whether brand has fabric
    if has_fabric:
        gen_url = GEN_URL_WITH_FABRIC
    else:
        gen_url = GEN_URL_WITHOUT_FABRIC

    for attempt in range(max_retries):
        try:
            with open(base_path, "rb") as f1, open(variant_path, "rb") as f2:
                if has_fabric:
                    # With fabric: chair first, then color
                    files = [
                        ("image", ("chair.jpg", f1, "image/jpeg")),
                        ("image", ("stain.jpg", f2, "image/jpeg")),
                    ]
                else:
                    # Without fabric: color first, then chair
                    files = [
                        ("image", ("stain.jpg", f2, "image/jpeg")),
                        ("image", ("chair.jpg", f1, "image/jpeg")),
                    ]

                response = requests.post(
                    gen_url,
                    files=files,
                    headers={"X-API-Key": api_key},
                    timeout=120
                )

            if response.status_code == 503:
                last_error = "503 Service Unavailable"
                if attempt < max_retries - 1:
                    print(f"\n    503 error, retry {attempt + 2}/{max_retries} in {RETRY_DELAY}s...", end="", flush=True)
                    time.sleep(RETRY_DELAY)
                    continue

            if response.status_code != 200:
                cleanup()
                return None, f"API error: {response.status_code} - {response.text[:200]}"

            # Pipeline returns image directly or JSON with image URL
            content_type = response.headers.get("Content-Type", "")

            if "image" in content_type:
                # Direct image response
                cleanup()
                return response.content, None
            else:
                # JSON response - extract image
                try:
                    data = response.json()
                    if "image" in data:
                        # Base64 encoded image
                        img_data = base64.b64decode(data["image"])
                        cleanup()
                        return img_data, None
                    elif "url" in data:
                        # Image URL - fetch it
                        img_response = requests.get(data["url"], timeout=30)
                        if img_response.status_code == 200:
                            cleanup()
                            return img_response.content, None
                        else:
                            cleanup()
                            return None, f"Failed to fetch image from URL: {img_response.status_code}"
                    else:
                        cleanup()
                        return None, f"Unexpected response format: {list(data.keys())}"
                except Exception as e:
                    cleanup()
                    return None, f"Failed to parse response: {e}"

        except requests.exceptions.RequestException as e:
            last_error = f"Request error: {str(e)[:50]}"
            if attempt < max_retries - 1:
                print(f"\n    Request error, retry {attempt + 2}/{max_retries} in {RETRY_DELAY}s...", end="", flush=True)
                time.sleep(RETRY_DELAY)
                continue
            cleanup()
            return None, last_error

    cleanup()
    return None, f"Max retries exceeded: {last_error}"


def evaluate_output_apiai(api_key, base_bytes, stain_bytes, output_bytes, eval_prompt, max_retries=3):
    """AI-evaluate generated output via apiai.me API with retry logic."""
    # Save bytes to temp files for upload
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f1:
        f1.write(base_bytes)
        base_path = f1.name
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f2:
        f2.write(stain_bytes)
        stain_path = f2.name
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f3:
        f3.write(output_bytes)
        output_path = f3.name

    def cleanup():
        for p in [base_path, stain_path, output_path]:
            try:
                os.unlink(p)
            except OSError:
                pass

    last_error = None

    for attempt in range(max_retries):
        try:
            with open(base_path, "rb") as f1, open(stain_path, "rb") as f2, open(output_path, "rb") as f3:
                files = [
                    ("image", ("base_chair.jpg", f1, "image/jpeg")),
                    ("image", ("stain_sample.jpg", f2, "image/jpeg")),
                    ("image", ("generated_output.png", f3, "image/png")),
                ]
                data = {"prompt": eval_prompt}

                response = requests.post(
                    EVAL_URL,
                    files=files,
                    data=data,
                    headers={"X-API-Key": api_key},
                    timeout=60
                )

            if response.status_code != 200:
                last_error = f"API error: {response.status_code}"
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                cleanup()
                return {"verdict": "ERROR", "reason": f"{last_error} - {response.text[:200]}"}

            # Parse JSON response
            resp_json = response.json()

            # apiai.me returns {"text": "..."} - extract the text field
            if "text" in resp_json:
                text = resp_json["text"].strip()
            else:
                text = response.text.strip()

            # Extract JSON from markdown code block if present
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
            if match:
                text = match.group(1).strip()

            try:
                result = json.loads(text)
                cleanup()
                return result
            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {str(e)[:50]}"
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                cleanup()
                return {"verdict": "ERROR", "reason": f"{last_error} | text: {text[:100]}"}

        except requests.exceptions.RequestException as e:
            last_error = f"Request error: {str(e)[:50]}"
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            cleanup()
            return {"verdict": "ERROR", "reason": last_error}

    cleanup()
    return {"verdict": "ERROR", "reason": f"Max retries exceeded: {last_error}"}


def generate_eval_criteria_html(eval_data):
    """Generate HTML for AI evaluation criteria breakdown with severity scores."""
    if not eval_data or eval_data.get("verdict") == "ERROR":
        return ""

    # All possible criteria (key, label, description)
    # Function will only show criteria that exist in eval_data
    all_criteria = [
        ("geometry", "Geometry", "Chair shape and structure"),
        ("colour", "Colour", "Colour match to sample"),
        ("material", "Material", "Material texture realism"),
        ("fabric", "Fabric", "Upholstery preservation"),
        ("background", "BG", "Background purity"),
        ("boundary", "Edge", "Material/fabric boundary unchanged"),
    ]

    html = '<div class="eval-criteria">'
    for key, label, desc in all_criteria:
        score = eval_data.get(key)
        if score is not None and (isinstance(score, int) or isinstance(score, float)):
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


def generate_html_report(results, base_b64, base_dims, base_name, output_dir, ai_pass_count, ai_fail_count, pipeline_name):
    """Generate self-contained HTML report."""
    success_count = sum(1 for r in results if r["success"])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<title>Bets Eval - {base_name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, sans-serif; background: #f5f7fa; padding: 20px; }}
.container {{ max-width: 1600px; margin: 0 auto; }}
header {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 40px; border-radius: 12px; margin-bottom: 30px; }}
h1 {{ font-size: 2em; margin-bottom: 10px; }}
.summary {{ background: white; padding: 25px; border-radius: 12px; margin-bottom: 30px; }}
.stats {{ display: flex; gap: 20px; flex-wrap: wrap; }}
.stat {{ background: #f7fafc; padding: 15px 25px; border-radius: 8px; text-align: center; }}
.stat h3 {{ font-size: 0.8em; color: #718096; }}
.stat .val {{ font-size: 1.8em; font-weight: bold; }}
.card {{ background: white; border-radius: 12px; margin-bottom: 20px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.card-head {{ display: flex; justify-content: space-between; padding: 15px 20px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }}
.card-head .name {{ font-weight: bold; }}
.gen-ok {{ color: #718096; background: #e2e8f0; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; }}
.gen-fail {{ color: #742a2a; background: #fed7d7; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; }}
.images {{ display: grid; grid-template-columns: 1fr 1fr 1fr; background: #ffffff; }}
.img-cell {{ padding: 20px; text-align: center; border-right: 1px solid #e2e8f0; background: #ffffff; }}
.img-cell:last-child {{ border-right: none; }}
.img-cell h4 {{ margin-bottom: 10px; color: #4a5568; font-size: 0.85em; text-transform: uppercase; }}
.img-cell img {{ max-width: 100%; max-height: 300px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); cursor: pointer; background: #ffffff !important; }}
.img-cell .dims {{ margin-top: 8px; font-size: 0.8em; color: #718096; }}
.dl-btn {{ display: inline-block; margin-top: 8px; padding: 6px 14px; background: #667eea; color: white; border-radius: 6px; text-decoration: none; font-size: 0.8em; cursor: pointer; border: none; }}
.dl-btn:hover {{ background: #5a67d8; }}
.rating {{ padding: 15px 20px; border-top: 1px solid #e2e8f0; display: flex; align-items: center; gap: 15px; }}
.rating select {{ padding: 8px 12px; border: 2px solid #e2e8f0; border-radius: 8px; }}
.rating input {{ flex: 1; padding: 8px 12px; border: 2px solid #e2e8f0; border-radius: 8px; }}
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
<h1>Chair Colour Evaluation</h1>
<p>Pipeline: {pipeline_name}</p>
<p>Base: {base_name}</p>
<p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
</header>
<div class="summary">
<h2>Summary</h2>
<div class="stats">
<div class="stat"><h3>Total</h3><div class="val">{len(results)}</div></div>
<div class="stat"><h3>Success</h3><div class="val">{success_count}</div></div>
<div class="stat"><h3>Failed</h3><div class="val">{len(results)-success_count}</div></div>
<div class="stat"><h3>Rate</h3><div class="val">{100*success_count//len(results) if results else 0}%</div></div>
<div class="stat"><h3>AI Pass</h3><div class="val" style="color:#22543d">{ai_pass_count}</div></div>
<div class="stat"><h3>AI Fail</h3><div class="val" style="color:#742a2a">{ai_fail_count}</div></div>
<div class="stat"><h3>AI Rate</h3><div class="val">{100*ai_pass_count//(ai_pass_count+ai_fail_count) if (ai_pass_count+ai_fail_count) > 0 else 0}%</div></div>
<div class="stat"><h3>Rated</h3><div class="val" id="ratedCount">0</div></div>
<div class="stat"><h3>Avg Rating</h3><div class="val" id="avgRating">-</div></div>
</div>
<div style="margin-top:15px">
<button class="dl-btn" onclick="exportRatings()">Export Ratings</button>
<button class="dl-btn" onclick="window.print()" style="background:#48bb78">Print/PDF</button>
<button class="dl-btn" onclick="shareReport()" style="background:#4299e1">Download Report</button>
<button class="dl-btn" onclick="clearRatings()" style="background:#f56565">Clear</button>
</div>
<details style="margin-top:20px">
<summary style="cursor:pointer;font-weight:bold;color:#4a5568">AI Evaluation Criteria (Severity 1-10)</summary>
<div style="margin-top:10px;padding:15px;background:#f7fafc;border-radius:8px;font-size:0.9em;line-height:1.8">
<strong>Scoring:</strong> 1 = perfect, 5+ = human-noticeable issue, 10 = severely wrong<br>
<strong>Verdict:</strong> PASS if max score &lt; 5, FAIL if any score &ge; 5<br><br>
<strong>Geometry:</strong> Chair shape and structure identical to original<br>
<strong>Colour:</strong> Material colour matches sample in hue, saturation, temperature<br>
<strong>Material:</strong> Realistic material texture with appropriate 3D lighting and shadows<br>
<strong>Fabric:</strong> Upholstery unchanged, no contamination from new colour (if applicable)<br>
<strong>BG:</strong> Pure white, isolated background<br>
<strong>Edge:</strong> Material/fabric boundary unchanged, no added frames or trim
</div>
</details>
</div>
"""

    for idx, r in enumerate(results):
        status = '<span class="gen-ok">Generated</span>' if r["success"] else '<span class="gen-fail">Failed</span>'

        # AI verdict badge
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

        html += f"""
<div class="card">
<div class="card-head">
<span class="name">{html_module.escape(r["variant_name"])}</span>
{status}
{ai_badge}
<span>{r["exec_time"]:.1f}s</span>
</div>
<div class="images">
<div class="img-cell"><h4>Base (Chair)</h4><img src="{base_b64}"><div class="dims">{base_dims[0]}x{base_dims[1]}</div></div>
<div class="img-cell"><h4>Variant (Stain)</h4><img src="{r["variant_b64"]}"><div class="dims">{r["variant_dims"][0]}x{r["variant_dims"][1]}</div></div>
<div class="img-cell"><h4>Output</h4>{"<img src='" + r["output_b64"] + "' onclick='window.open(this.src)'><div class='dims'>" + str(r["output_dims"][0]) + "x" + str(r["output_dims"][1]) + "</div><button class='dl-btn' onclick='download(this, \"" + Path(r["variant_name"]).stem + "_chair.jpg\")'>Download</button>" if r["success"] else "<p style='color:red'>" + html_module.escape(r.get("error","")) + "</p><div class='dims'>-</div>"}</div>
</div>
{generate_eval_criteria_html(eval_data) if eval_data else ''}
<div class="rating">
<span>User Rating:</span>
<select id="rating-{idx}" onchange="saveRating({idx})"><option value="">-</option><option value="5">5 Perfect</option><option value="4">4 Good</option><option value="3">3 OK</option><option value="2">2 Poor</option><option value="1">1 Failed</option></select>
<input type="text" id="notes-{idx}" placeholder="Notes..." onchange="saveRating({idx})">
</div>
</div>
"""

    html += f"""
<script>
const STORAGE_KEY = 'eval_bets_{timestamp}';
const totalItems = {success_count};

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
    a.href = URL.createObjectURL(blob); a.download = 'bets_ratings.json'; a.click();
}}

function clearRatings() {{
    if (confirm('Clear all ratings?')) {{ localStorage.removeItem(STORAGE_KEY); location.reload(); }}
}}

function shareReport() {{
    // Download the HTML file
    const blob = new Blob([document.documentElement.outerHTML], {{type: 'text/html'}});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'eval_{output_dir.name}.html';
    a.click();

    // Open mail client with pre-filled subject
    setTimeout(() => {{
        const subject = encodeURIComponent('Chair Colour Evaluation Report');
        const body = encodeURIComponent('Hi,\\n\\nPlease find the colour evaluation report attached.\\n\\nSummary:\\n- Total variants: {len(results)}\\n- AI Pass: {ai_pass_count}\\n- AI Fail: {ai_fail_count}\\n\\nBest regards');
        window.location.href = 'mailto:?subject=' + subject + '&body=' + body;
    }}, 500);
}}
</script>
</div></body></html>"""

    report_path = output_dir / f"eval_{output_dir.name}.html"
    with open(report_path, "w") as f:
        f.write(html)

    return report_path


def list_brands():
    """List available brands in Content folder."""
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
    chairs = []
    for p in chairs_path.iterdir():
        if p.suffix.lower() in ['.png', '.jpg', '.jpeg']:
            chairs.append(p.stem)
    return sorted(chairs)


def get_colours_for_chair(brand, chair_name):
    """Get colour variants that match a chair (by prefix)."""
    colours_path = CONTENT_PATH / brand / "Colours"
    if not colours_path.exists():
        return []

    # Extract model name from chair (e.g., "Stol Dome" -> "DOME", "Stol Nolita 3658" -> "Nolita")
    # Try to match colours that start with similar prefix
    chair_lower = chair_name.lower()

    colours = []
    for p in colours_path.iterdir():
        if p.suffix.lower() in ['.png', '.jpg', '.jpeg']:
            colours.append(p)

    # If chair name contains a known model, filter colours
    # Otherwise return all colours
    return sorted(colours, key=lambda x: x.name)


def select_interactive():
    """Interactive selection of brand and chair."""
    brands = list_brands()
    if not brands:
        print("ERROR: No brands found in", CONTENT_PATH)
        return None, None

    print("\n=== Available Brands ===")
    for i, brand in enumerate(brands, 1):
        print(f"  {i}. {brand}")

    try:
        choice = input("\nSelect brand (number): ").strip()
        brand = brands[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid selection")
        return None, None

    chairs = list_chairs(brand)
    if not chairs:
        print(f"ERROR: No chairs found for {brand}")
        return None, None

    print(f"\n=== Chairs for {brand} ===")
    for i, chair in enumerate(chairs, 1):
        print(f"  {i}. {chair}")

    try:
        choice = input("\nSelect chair (number): ").strip()
        chair = chairs[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid selection")
        return None, None

    return brand, chair


def run_eval(brand, chair_name, apiai_key, limit=None):
    """Run evaluation for a specific brand and chair."""
    # Check if brand has fabric
    has_fabric = brand_has_fabric(brand)
    pipeline_name = GEN_PIPELINE_WITH_FABRIC if has_fabric else GEN_PIPELINE_WITHOUT_FABRIC

    # Find chair image
    chairs_path = CONTENT_PATH / brand / "Chairs"
    chair_path = None
    for ext in ['.png', '.jpg', '.jpeg']:
        p = chairs_path / f"{chair_name}{ext}"
        if p.exists():
            chair_path = p
            break

    if not chair_path:
        print(f"ERROR: Chair image not found: {chair_name}")
        return

    # Get colour variants
    colours = get_colours_for_chair(brand, chair_name)
    if not colours:
        print(f"ERROR: No colours found for {brand}")
        return

    # Apply limit if specified
    if limit:
        colours = colours[:limit]

    # Setup output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = EVALS_PATH / f"bets_{brand.lower()}_{chair_name.lower().replace(' ', '_')}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load base image
    with open(chair_path, "rb") as f:
        base_bytes = f.read()
    base_img = Image.open(io.BytesIO(base_bytes))
    base_dims = base_img.size
    base_b64 = image_to_base64(str(chair_path))

    print(f"\n{'='*60}")
    print(f"Brand: {brand}")
    print(f"Chair: {chair_name} ({base_dims[0]}x{base_dims[1]})")
    print(f"Colours: {len(colours)}")
    print(f"Pipeline: {pipeline_name}")
    print(f"Has Fabric: {has_fabric}")
    print(f"Output: {output_dir}")
    print(f"{'='*60}\n")

    results = []

    for idx, variant_path in enumerate(colours, 1):
        variant_name = variant_path.name
        print(f"[{idx}/{len(colours)}] {variant_name}...", end=" ", flush=True)

        start = time.time()

        try:
            with open(variant_path, "rb") as f:
                variant_bytes = f.read()

            variant_img = Image.open(io.BytesIO(variant_bytes))
            variant_dims = variant_img.size

            # Generate via apiai.me pipeline
            output_data, error = generate_via_apiai(apiai_key, base_bytes, variant_bytes, has_fabric=has_fabric)

            exec_time = time.time() - start
            output_dims = [0, 0]

            if output_data:
                output_img = Image.open(io.BytesIO(output_data))
                output_dims = list(output_img.size)

                out_path = output_dir / f"{variant_path.stem}_output.png"
                with open(out_path, "wb") as f:
                    f.write(output_data)

            if output_data:
                print(f"OK ({exec_time:.1f}s) - {output_dims[0]}x{output_dims[1]}", end=" ", flush=True)

                # AI evaluation via apiai.me
                print("| eval...", end=" ", flush=True)
                try:
                    eval_prompt = EVAL_PROMPT_WITH_FABRIC if has_fabric else EVAL_PROMPT_WITHOUT_FABRIC
                    eval_result = evaluate_output_apiai(apiai_key, base_bytes, variant_bytes, output_data, eval_prompt)
                    verdict = eval_result.get('verdict', 'ERROR')
                    if verdict == "ERROR":
                        print(f"AI: ERROR ({eval_result.get('reason', 'unknown')})")
                    else:
                        print(f"AI: {verdict}")
                except Exception as e:
                    eval_result = {"verdict": "ERROR", "reason": str(e)}
                    print(f"AI: ERROR ({e})")

                results.append({
                    "variant_name": variant_name,
                    "variant_b64": image_to_base64(str(variant_path)),
                    "variant_dims": variant_dims,
                    "output_b64": bytes_to_base64(output_data, "image/png"),
                    "output_dims": output_dims,
                    "exec_time": exec_time,
                    "success": True,
                    "error": None,
                    "eval": eval_result
                })
            else:
                error_msg = error or "No image in response"
                print(f"FAILED - {error_msg}")
                results.append({
                    "variant_name": variant_name,
                    "variant_b64": image_to_base64(str(variant_path)),
                    "variant_dims": variant_dims,
                    "output_b64": "",
                    "output_dims": [0, 0],
                    "exec_time": exec_time,
                    "success": False,
                    "error": error_msg,
                    "eval": {}
                })

        except Exception as e:
            exec_time = time.time() - start
            print(f"FAILED - {e}")
            results.append({
                "variant_name": variant_name,
                "variant_b64": image_to_base64(str(variant_path)),
                "variant_dims": [0, 0],
                "output_b64": "",
                "output_dims": [0, 0],
                "exec_time": exec_time,
                "success": False,
                "error": str(e),
                "eval": {}
            })

    # Calculate AI stats
    ai_pass = sum(1 for r in results if r.get("eval", {}).get("verdict") == "PASS")
    ai_fail = sum(1 for r in results if r.get("eval", {}).get("verdict") == "FAIL")

    # Generate report
    print("\nGenerating HTML report...")
    report_path = generate_html_report(results, base_b64, base_dims, chair_path.name, output_dir, ai_pass, ai_fail, pipeline_name)

    # Save JSON results
    json_path = output_dir / "results.json"
    with open(json_path, "w") as f:
        json_results = [{k: v for k, v in r.items() if not k.endswith("_b64")} for r in results]
        json.dump({
            "brand": brand,
            "chair": chair_name,
            "pipeline": pipeline_name,
            "timestamp": datetime.now().isoformat(),
            "ai_pass": ai_pass,
            "ai_fail": ai_fail,
            "results": json_results
        }, f, indent=2)

    success_count = sum(1 for r in results if r["success"])
    print(f"\n{'='*60}")
    print(f"DONE: {success_count}/{len(results)} successful")
    print(f"AI Eval: {ai_pass} PASS, {ai_fail} FAIL ({100*ai_pass//(ai_pass+ai_fail) if (ai_pass+ai_fail) > 0 else 0}%)")
    print(f"Report: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate chair colour variants via apiai.me")
    parser.add_argument("--brand", "-b", help="Brand name (e.g., Pedrali, Paged)")
    parser.add_argument("--chair", "-c", help="Chair name (e.g., 'Stol Dome')")
    parser.add_argument("--limit", "-n", type=int, help="Limit number of colours to process")
    parser.add_argument("--list", "-l", action="store_true", help="List available brands and chairs")
    args = parser.parse_args()

    # Get API key from environment
    apiai_key = os.getenv("APIAI_API_KEY")
    if not apiai_key:
        print("ERROR: APIAI_API_KEY not found in environment or .env file")
        return

    # List mode
    if args.list:
        brands = list_brands()
        print("\n=== Available Brands ===")
        for brand in brands:
            chairs = list_chairs(brand)
            colours_path = CONTENT_PATH / brand / "Colours"
            num_colours = len(list(colours_path.glob("*.*"))) if colours_path.exists() else 0
            print(f"\n{brand}:")
            print(f"  Chairs: {', '.join(chairs)}")
            print(f"  Colours: {num_colours}")
        return

    # Interactive mode if no brand specified
    if not args.brand:
        brand, chair = select_interactive()
        if not brand:
            return
    else:
        brand = args.brand
        if not args.chair:
            chairs = list_chairs(brand)
            if not chairs:
                print(f"ERROR: No chairs found for {brand}")
                return
            print(f"\n=== Chairs for {brand} ===")
            for i, chair in enumerate(chairs, 1):
                print(f"  {i}. {chair}")
            try:
                choice = input("\nSelect chair (number): ").strip()
                chair = chairs[int(choice) - 1]
            except (ValueError, IndexError):
                print("Invalid selection")
                return
        else:
            chair = args.chair

    run_eval(brand, chair, apiai_key, limit=args.limit)


if __name__ == "__main__":
    main()
