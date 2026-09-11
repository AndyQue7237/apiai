#!/usr/bin/env python3
"""
Run the whole logo set through the local pipeline and build a STEP-BY-STEP report.

Before→after tells you something is wrong; step-by-step tells you WHICH NODE did it. That is the
whole reason this exists: on Trollbäckens the report shows Nano Banana Pro handing over a clean
1024px emblem on white, and the background remover leaving a white pocket between the K and the T —
so the defect belongs to node 4, not to the model everyone would have blamed first.

One tab per method, appended never overwritten (`../../evaluator/EVAL_GUIDELINES.md`). Swapping
nodes 3+4 for GPT Image 2 becomes a second tab beside this one, same logos, same everything else.

Usage:
    python3 run_all.py                      # skip logos already done
    python3 run_all.py --fresh              # re-run everything
    python3 run_all.py --only troll         # one logo
    python3 run_all.py --tag gpt2           # name the method (= the tab)
    python3 run_all.py --report-only        # rebuild the HTML from what is on disk
"""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import io
import json
import time
from pathlib import Path

from PIL import Image

import run_pipeline as rp
import run_pipeline_v2 as rp_v2

LOGO_DIR = Path(
    "/Users/andreasquensel/Library/CloudStorage/GoogleDrive-andreas@zebrolabs.com/"
    "Shared drives/Apiai.me/Customers/Heja/Content/Team Logos"
)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
REPORT = OUT / "steps.html"

# What each node is for, shown under its thumbnail so the report explains itself.
STEP_LABEL = {
    "0-input": ("0 · Original", "handlarens fil, som den är"),
    "1-crop": ("1 · Detect and Crop", "Florence-2 → beskär med padding"),
    # v1 pipeline steps
    "3-nbpro": ("3 · Nano Banana Pro", "ritar om loggan på vit botten"),
    "3-gpt2": ("3 · GPT Image 2", "ritar om OCH tar bort bakgrund — ersätter nod 3+4"),
    "4-removebg": ("4 · Detect and Remove Background", "DINO skyddar emblemet, fyller utifrån"),
    # v2 pipeline steps (quality routing)
    "4-gpt2": ("4 · GPT Image 2", "förbättrar kvalitet + tar bort bakgrund"),
    "4b-removebg": ("4b · Remove Solid BG", "flood-fill från kanter (script)"),
    "4c-gpt2": ("4c · GPT Image 2", "edge case — multi-color bakgrund"),
    # common
    "6-upscale": ("6 · Real-ESRGAN", "skalar upp 4×"),
    "7-final": ("7 · Transparent Crop", "beskär mot alfa, ramar 1:1"),
}


def checker(size, square=22):
    import numpy as np
    w, h = size
    a = np.full((h, w, 3), 255, dtype=np.uint8)
    ys, xs = np.mgrid[0:h, 0:w]
    a[((ys // square + xs // square) % 2) == 1] = 202
    return Image.fromarray(a)


# Checkerboard square size in DISPLAYED pixels. Drawn after the thumbnail, never before: at full
# resolution a 22px square on a 4096px file shrinks to two pixels and reads as plain white, which
# hides exactly the defect the checkerboard exists to reveal (Andreas, on Knivsta — over-removal
# looked correct at a glance). Composited last, the grid is the same size at every step.
CHECKER_PX = 15


def embed(path: Path, max_dim: int = 420) -> str:
    """Thumbnail as a data URI. Transparent images go on a checkerboard — against white, leftover
    white background is invisible, which is exactly how the first false pass happened."""
    im = Image.open(path)
    im.thumbnail((max_dim, max_dim))
    if im.mode == "RGBA":
        im = Image.alpha_composite(checker(im.size, CHECKER_PX).convert("RGBA"), im)
    im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=86)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def settings_box(tag: str, recs: list) -> str:
    """The full knob space for this method, prompts included. Required by
    `../../evaluator/EVAL_GUIDELINES.md`: a tab you cannot reproduce from is evidence you cannot
    trust later, and showing the parameters left at their API default (`null`) makes it obvious at
    a glance which knob is still untuned."""
    # Detect pipeline from records, not tag name: v2 records have "routing" key, v1 have "conditions"
    is_v2 = any(r.get("routing") for r in recs)
    method = next((r.get("method") for r in recs if r.get("method")), tag)

    if is_v2:
        # v2 pipeline: quality routing determines which nodes run
        order = ["detect_and_crop", "check_quality", "check_transparency",
                 "openai-gpt-image-2", "has_solid_background", "remove_solid_background",
                 "check_resolution", "real-esrgan", "crop_transparent"]
        params_source = rp_v2.PARAMS
        gen = "openai-gpt-image-2"
    else:
        # v1 pipeline - detect generator from actual steps, not tag name
        # Check if any step contains "gpt2" to determine which generator was used
        used_gpt2 = any("gpt2" in s.get("step", "") for r in recs for s in r.get("steps", []))
        gen = "openai-gpt-image-2" if used_gpt2 else "nano-banana-pro"
        order = ["detect_and_crop", "check_quality", "check_transparency", gen, "detect_and_remove_bg",
                 "check_resolution", "real-esrgan", "crop_transparent"]
        if used_gpt2:
            order.remove("detect_and_remove_bg")
        params_source = rp.PARAMS

    rows = ""
    for node in order:
        ps = params_source.get(node, {})
        cells = []
        for k, v in ps.items():
            if k == "prompt":
                continue
            cells.append(f"{html.escape(k)}=" + (f'<span class="null">null</span>' if v is None
                                                 else html.escape(str(v))))
        # the node scripts' own defaults, shown as null so the untuned knobs are visible
        for k in DEFAULTED.get(node, []):
            cells.append(f'{html.escape(k)}=<span class="null">default</span>')
        rows += (f'<tr><td>{html.escape(node)}</td><td>{" · ".join(cells) or "—"}</td></tr>')

    # Get prompt from routing (v2) or conditions (v1)
    prompt = ""
    if is_v2:
        used = {r["routing"].get("prompt") for r in recs if r.get("routing", {}).get("prompt")}
        texts = list(used) or [rp_v2.GPT2_PROMPT]
    else:
        used = {r["conditions"].get("prompt") for r in recs if r.get("conditions", {}).get("prompt")}
        # Use actual generator detected above, not tag name
        texts = list(used) or ([rp.NB_PRO_PROMPT] if gen == "nano-banana-pro" else [rp.GPT2_PROMPT])
    for i, txt in enumerate(texts):
        prompt += (f'<details><summary>Prompt till {html.escape(gen)}'
                   f'{" (" + str(i + 1) + ")" if len(texts) > 1 else ""}</summary>'
                   f'<pre>{html.escape(txt)}</pre></details>')

    # Add v2 routing explanation
    routing_note = ""
    if is_v2:
        routing_note = ('<div style="margin-top:10px;font-size:11px;color:#8b93a1">'
                        '<b>Routing:</b> check_quality → needs_enhancement? '
                        'Om ja: GPT2 (4). Om nej + transparent: skip. '
                        'Om nej + ej transparent: has_solid_background → script (4b) eller GPT2 (4c).'
                        '</div>')

    return (f'<div class="settings"><h2>Vad som kördes — metod <b>{html.escape(tag)}</b></h2>'
            f'<table>{rows}</table>{prompt}{routing_note}</div>')


# Params the node scripts leave at their own defaults — listed so the settings box shows the whole
# knob space, not only what we set. From each script's docstring.
DEFAULTED = {
    "detect_and_crop": ["box_threshold", "text_threshold", "padding_percent", "safety_margin"],
    "check_quality": [],  # all thresholds explicit in PARAMS
    "check_transparency": ["threshold"],
    "detect_and_remove_bg": ["box_threshold", "bg_color", "tolerance", "feather"],
    "real-esrgan": ["face_enhance"],
    "crop_transparent": ["subject_scale", "background"],
}

HTML = """<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><title>Heja · steg för steg</title>
<style>
 :root{font-family:system-ui,-apple-system,sans-serif}
 body{margin:0;background:#0f1115;color:#e8eaed}
 header{padding:18px 24px;border-bottom:1px solid #262a33;position:sticky;top:0;background:#0f1115;z-index:2}
 h1{font-size:16px;margin:0 0 12px;letter-spacing:.5px}
 .tab{background:#1a1d24;color:#aeb4bf;border:1px solid #2b303b;border-radius:999px;padding:7px 14px;font-size:13px;cursor:pointer;margin-right:8px}
 .tab.active{background:#2563eb;color:#fff;border-color:#2563eb}
 section.tabsec[hidden]{display:none}
 .settings{margin:18px 24px 0;background:#161922;border:1px solid #262a33;border-radius:10px;padding:14px 16px;font-size:12px;color:#cbd2dc}
 .settings h2{font-size:12px;margin:0 0 10px;color:#8b93a1;text-transform:uppercase;letter-spacing:.6px}
 .settings h2 b{color:#e8eaed}
 .settings table{border-collapse:collapse;margin-bottom:8px}
 .settings td{padding:2px 14px 2px 0;vertical-align:top}
 .settings td:first-child{color:#8b93a1;white-space:nowrap}
 .settings .null{color:#5c6473;font-style:italic}
 .settings details summary{cursor:pointer;color:#8b93a1;margin-top:6px}
 .settings pre{white-space:pre-wrap;background:#10131a;border:1px solid #262a33;border-radius:8px;padding:12px;margin:8px 0 0;max-width:900px}
 .card{margin:22px 24px;background:#161922;border:1px solid #262a33;border-radius:12px;padding:16px}
 .card h3{margin:0 0 4px;font-size:14px}
 .cond{font-size:12px;color:#8b93a1;margin-bottom:12px}
 .cond b{color:#cbd2dc;font-weight:600}
 .chain{display:flex;gap:10px;align-items:flex-start;overflow-x:auto;padding-bottom:6px}
 .step{flex:0 0 auto;width:210px}
 .step img{width:100%;border-radius:6px;display:block;background:#000;cursor:zoom-in}
 .step .n{font-size:11px;color:#cbd2dc;margin-top:6px;font-weight:600}
 .step .d{font-size:11px;color:#7d8593;line-height:1.35}
 .step .px{font-size:10px;color:#5c6473;font-family:ui-monospace,monospace}
 .arrow{flex:0 0 auto;align-self:center;color:#3a4150;font-size:20px}
 #lb{display:none;position:fixed;inset:0;background:rgba(0,0,0,.93);z-index:10;place-items:center;cursor:zoom-out;padding:24px}
 #lb img{max-width:96vw;max-height:92vh;border-radius:8px}
</style></head><body>
<header><h1>Heja · pipeline steg för steg</h1><div>%TABS%</div></header>
%SECTIONS%
<div id="lb" onclick="this.style.display='none'"><img id="lbimg" alt=""></div>
<script>
 function zoom(s){document.getElementById('lbimg').src=s;document.getElementById('lb').style.display='grid'}
 document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
   document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));t.classList.add('active');
   document.querySelectorAll('section.tabsec').forEach(s=>s.hidden=s.id!==t.dataset.sec)})
</script></body></html>"""


def card(rec: dict) -> str:
    src = LOGO_DIR / rec["logo"]
    chain = [("0-input", src)] + [(s["step"], OUT / s["file"]) for s in rec["steps"]]

    # Build timing lookup: step number → seconds (e.g. "1" → 2.3)
    timing_map = {}
    for t in rec.get("timings", []):
        node = t.get("node", "")
        # Extract step number from "1 · detect_and_crop" or "4a · has_solid_background"
        if " · " in node:
            step_num = node.split(" · ")[0].strip()
            timing_map[step_num] = t.get("seconds", 0)

    parts = []
    for i, (step, path) in enumerate(chain):
        if not path.exists():
            continue
        name, desc = STEP_LABEL.get(step, (step, ""))
        im = Image.open(path)

        # Get timing for this step (extract number from "1-crop" → "1", "4b-removebg" → "4b")
        step_num = step.split("-")[0] if "-" in step else step
        step_time = timing_map.get(step_num, 0)
        time_str = f" · <b>{step_time:.1f}s</b>" if step_time > 0 else ""

        if i:
            parts.append('<div class="arrow">›</div>')
        parts.append(
            f'<div class="step"><img src="{embed(path)}" onclick="zoom(this.src)">'
            f'<div class="n">{html.escape(name)}</div>'
            f'<div class="d">{html.escape(desc)}</div>'
            f'<div class="px">{im.width}×{im.height} · {im.mode}{time_str}</div></div>')

    # Support both old "conditions" and new "routing" keys
    c = rec.get("conditions", rec.get("routing", {}))
    bits = []
    if "dino" in c:
        bits.append(f'Florence-2: <b>{html.escape(str(c["dino"]))}</b>')
    # Quality metrics (from check_quality)
    if "megapixels" in c:
        mp = c["megapixels"]
        flat = c.get("flatness_pct", 0)
        grad = c.get("gradient_pct")
        grad_str = f"{grad:.0f}%" if grad is not None else "—"
        bits.append(f'<span title="megapixels · flatness · gradient">quality: <b>{mp:.2f}MP · {flat:.0f}% · {grad_str}</b></span>')
    # v2 routing info
    if "route" in c:
        route_labels = {
            "gpt2_enhancement": "GPT2 (förbättring)",
            "transparent_skip": "skip (redan transparent + bra kvalitet)",
            "script_bg_removal": "script (solid bg)",
            "gpt2_edge_case": "GPT2 (edge case bg)",
        }
        route = c.get("route", "")
        bits.append(f'route: <b>{html.escape(route_labels.get(route, route))}</b>')
    if "needs_enhancement" in c:
        if c["needs_enhancement"]:
            reason = c.get("quality_reason", "")
            bits.append(f'behöver förbättring: <b>{html.escape(reason)}</b>')
    # Legacy v1 routing
    if "is_transparent" in c and "route" not in c:
        bits.append("redan transparent → <b>hoppade över nod 3–4</b>" if c["is_transparent"]
                    else "ej transparent → <b>körde nod 3–4</b>")
    if "is_high_resolution" in c:
        bits.append("redan högupplöst → <b>hoppade över nod 6</b>" if c["is_high_resolution"]
                    else "för låg upplösning → <b>körde nod 6</b>")
    bits.append(f'{rec.get("seconds", "?")} s totalt')
    return (f'<div class="card"><h3>{html.escape(rec["logo"])}</h3>'
            f'<div class="cond">{" · ".join(bits)}</div>'
            f'<div class="chain">{"".join(parts)}</div></div>')


def build_report() -> Path:
    tags = {}
    tag_mtime = {}  # Track newest file per tag for sorting
    for f in sorted(OUT.glob("*-steps.json")):
        rec = json.loads(f.read_text())
        if isinstance(rec, list):  # a run from before run_one() returned a record
            continue
        tag = rec.get("tag", "?")
        tags.setdefault(tag, []).append(rec)
        # Track newest modification time per tag
        mtime = f.stat().st_mtime
        tag_mtime[tag] = max(tag_mtime.get(tag, 0), mtime)

    # Sort by newest first (descending mtime)
    sorted_tags = sorted(tags.items(), key=lambda x: tag_mtime.get(x[0], 0), reverse=True)

    tabs, sections = [], []
    for i, (tag, recs) in enumerate(sorted_tags):
        sid, active = f"sec-{tag}", (" active" if i == 0 else "")
        tabs.append(f'<button class="tab{active}" data-sec="{sid}">{html.escape(tag)} '
                    f'({len(recs)})</button>')
        cards = "".join(card(r) for r in sorted(recs, key=lambda r: r["logo"]))
        sections.append(f'<section class="tabsec" id="{sid}"{"" if i == 0 else " hidden"}>'
                        f'{settings_box(tag, recs)}{cards}</section>')
    REPORT.write_text(HTML.replace("%TABS%", "".join(tabs)).replace("%SECTIONS%", "".join(sections)),
                      encoding="utf-8")
    return REPORT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="nbpro")
    ap.add_argument("--method", default="", choices=["", "nbpro", "gpt2a", "v2"])
    ap.add_argument("--only", default="")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--workers", type=int, default=4, help="hur många loggor parallellt")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    # Use v2 pipeline for tags starting with "v2"
    use_v2 = args.tag.startswith("v2")

    if args.report_only:
        print(f"rapport: {build_report()}")
        return

    logos = sorted(p for p in LOGO_DIR.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if args.only:  # comma-separated, so a handful of logos can be re-run together
        wanted = [w.strip().lower() for w in args.only.split(",") if w.strip()]
        logos = [p for p in logos if any(w in p.name.lower() for w in wanted)]
    pipeline_name = "v2 (quality routing)" if use_v2 else "v1"
    print(f"{len(logos)} loggor, tag '{args.tag}', pipeline {pipeline_name}")

    todo = [s_ for s_ in logos
            if args.fresh or not (OUT / f"{s_.stem}-{args.tag}-steps.json").exists()]
    for s_ in logos:
        if s_ not in todo:
            print(f"  {s_.name} — hoppar (redan klar)")
    if not todo:
        print("inget att köra")
    # A pool, because the sequential loop was OUR bottleneck, not the API: six generative logos at
    # ~95s each is ten minutes of mostly waiting. Kept modest on purpose — the hosted models have
    # per-minute limits, and hammering them turns a slow run into a failed one.
    t0 = time.time()
    done_n = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        if use_v2:
            # v2 pipeline: run_one(src, tag) — no method param, routing is automatic
            futures = {pool.submit(rp_v2.run_one, s_, args.tag): s_ for s_ in todo}
        else:
            # v1 pipeline: run_one(src, tag, method)
            futures = {pool.submit(rp.run_one, s_, args.tag, args.method or args.tag): s_
                       for s_ in todo}
        for fut in as_completed(futures):
            src = futures[fut]
            done_n += 1
            try:
                fut.result()
                status = "klar"
            except Exception as e:
                status = f"✗ {e}"
            el = time.time() - t0
            print(f"[{done_n}/{len(todo)}] {src.name[:34]:<36}{status[:70]}"
                  f"   · {el/60:.1f} min, ETA {el/done_n*(len(todo)-done_n)/60:.1f} min", flush=True)

    print(f"\nrapport: {build_report()}")


if __name__ == "__main__":
    main()
