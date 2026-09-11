#!/usr/bin/env python3
"""
Heja team-logo pipeline tester.

Runs each team logo through the LIVE apiai.me pipeline `team-logo-nb-pro`, then judges the
result two ways:

  1. DETERMINISTIC checks, computed here — resolution, real transparency, background trapped
     inside enclosed areas, and hue drift against the original. These exist because the AI judge
     provably cannot do them: it cannot count pixels, it cannot see an alpha channel, and it very
     likely sees the output composited on white, which makes leftover WHITE background invisible.
     That last one produced a 100% false pass on Trollbäckens GK (2026-08-31).
  2. The apiai.me eval PROFILE (optional, --profile-id), which scores logo/text/colour fidelity.
     Its rubric lives in `heja_eval_profile.md` — do not duplicate it here.

The report is one self-contained tabbed HTML, one tab per run, outputs frozen per tab so a later
run cannot clobber the evidence. See `../../EVAL_GUIDELINES.md` for the conventions this follows.

Local dev tool (uses `requests`/`scipy`, not the apiai.me runtime).

Usage:
    python3 eval_logo.py --limit 1                 # smoke test on one logo
    python3 eval_logo.py                           # the whole set
    python3 eval_logo.py --profile-id 17           # also pull judge scores
    python3 eval_logo.py --report-only             # rebuild the report from frozen runs
    python3 eval_logo.py --dry-run                 # list the set, spend nothing
"""

import argparse
import base64
import colorsys
import html
import io
import json
import os
import re
import shutil
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from scipy import ndimage

# ── Config ──
PIPELINE_SLUG = "team-logo-nb-pro"
PIPELINE_URL = f"https://apiai.me/api/pipeline/{PIPELINE_SLUG}"
EVAL_URL = "https://eval.apiai.me/v1/eval/results"

LOGO_DIR = Path(
    "/Users/andreasquensel/Library/CloudStorage/GoogleDrive-andreas@zebrolabs.com/"
    "Shared drives/Apiai.me/Customers/Heja/Content/Team Logos"
)

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "out"
RUNS_JSON = OUT_DIR / "runs.json"
EVALS_JSON = OUT_DIR / "evals.json"
TABS_DIR = OUT_DIR / "tabs"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
PIPELINE_TIMEOUT_S = 600  # NB Pro + Real-ESRGAN on a 15 MP output is slow
EVAL_POLL_TIMEOUT_S = 240

# The contract Heja is delivered against.
MIN_PIXELS = 1_500_000

# Anything smaller than this, in an enclosed background-coloured region, is anti-aliasing fringe
# rather than trapped background. Calibrated on Trollbäckens GK: a floor of 2000 px isolated the
# one real defect (the K/T pocket) and gave zero false positives, where 50 px gave 68.
TRAPPED_FLOOR_PX = 2000
TRAPPED_FLOOR_FRAC = 0.0005  # …or this share of the subject, whichever is larger

# A trapped region this flat and this wide is a tiling seam from the upscaler, not a pocket.
# How far the palette may move before it stops being the club's colours. Calibrated on the two
# Trollbäckens outputs: the drifted one scores 15.5, the faithful one 5.0.
MAX_COLOUR_MEAN = 10          # share-weighted mean RGB distance
MAX_COLOUR_DISTANCE = 40      # …and no single colour holding ≥5% of the logo may move this far

SEAM_MIN_ASPECT = 20
SEAM_MAX_HEIGHT = 8


# ── The pipeline as it actually runs, recorded so every tab is reproducible ──
NODE_CHAIN = [
    ("1", "Detect and Crop", "detect_and_crop.py", "Grounding DINO → crop with padding"),
    ("2", "Check Transparency", "check_transparency.py", "→ if transparent, skip nodes 3–4"),
    ("3", "Nano Banana Pro", "/api/process/nano-banana-pro", "generative restore onto solid white"),
    ("4", "Detect and Remove Background", "detect_and_remove_bg.py", "DINO-protected removal, outside-in"),
    ("5", "Check Resolution", "check_resolution.py", "→ if high-res, skip node 6"),
    ("6", "Real-ESRGAN Upscaler", "/api/process/real-esrgan", "upscale"),
    ("7", "Transparent Crop", "crop_transparent.py", "crop to alpha, frame on target canvas"),
]

# Node 3's prompt, verbatim, as supplied by Andreas 2026-08-31.
# NOTE: `evaluator/batch_evaluate.py` carries a DIFFERENT, older prompt for nano-banana-pro
# ("You are an image model that will make team emblems crystal clear…") AND temperature=1, where
# the live node runs 0.2. That file is stale on both counts; trust the platform, not it.
NB_PRO_PROMPT = """You are a master Art Restorer and Forensic Image Upscaler. Your sole task is to take low-quality original images of team emblems (which may be pixelated, blurry, or photos of fabric) and reconstruct them as pristine, high-resolution, print-ready vector-style images.

MANDATORY RESTORATION RULES:

FIDELITY ABOVE ALL: The final output must be an exact reconstruction of the original design, shape, text, and structure. Do not "improve" the artistic design. Do not add or remove elements.

PERFECT COLOR MATCH: The colors must be extracted from the original input and maintained with 100% hue and saturation fidelity. If the input is a blurry photo of a faded emblem, your goal is to find the original, intended colors and apply them uniformly. No fading.

NOISE AND ARTIFACT REMOVAL: Completely eliminate any compression artifacts, noise, blur, and fabric texture.

SHARP LINES: All curves, edges, and lines must be rendered with perfect, smooth, clean vector-like precision. All text must be rendered legibly, matching the exact original font structure.

SOLID BACKGROUND: Isolate the finished, reconstructed emblem on a pristine, solid white background (#FFFFFF). This is for pre-processing purposes.

Task: Reconstruct the original input emblem with perfect fidelity, making it a crystal-clear vector-style image on a solid white background."""

# The full knob space. `null` = left at the API default, i.e. still untuned and worth a look.
# Filled in from the node scripts' docstrings + what the pipeline is known to send.
PARAM_SURFACE = {
    "detect_and_crop": {"query": "complete logo with text, full team logo with text, entire emblem, club logo",
                        "box_threshold": 0.25, "padding_percent": None},
    "check_transparency": {"field": "is_transparent", "threshold": 250, "sample_percent": 10},
    # temperature/top_k/top_p supplied by Andreas 2026-08-31 — already tightened well below the
    # defaults, which matters here: this node is the one that can rewrite a club's name.
    "nano-banana-pro": {"prompt": "(see below)", "temperature": 0.2, "top_k": 15, "top_p": 0.1,
                        "seed": None, "aspect_ratio": None, "output_format": None},
    "detect_and_remove_bg": {"query": None, "box_threshold": None, "tolerance": None},
    "check_resolution": {"field": None, "threshold": None},
    "real-esrgan": {"scale": None, "face_enhance": None, "tile": None},
    "crop_transparent": {"aspect": None, "margin_px": None, "subject_percent": None,
                         "alpha_threshold": None},
}


def api_key() -> str:
    key = os.environ.get("APIAI_API_KEY")
    if not key:
        for p in [HERE] + list(HERE.parents):
            env = p / ".env"
            if env.exists():
                for line in env.read_text().splitlines():
                    if line.startswith("APIAI_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"')
                        break
            if key:
                break
    if not key:
        sys.exit("APIAI_API_KEY not set (env or .env).")
    return key


def load_set(limit: int, only: str = "") -> list:
    """Every image in the logo folder, sorted. Printed before any spend — a silently wrong or
    truncated set invalidates the comparison with earlier runs. `only` narrows to one input, which
    is how a single failing logo gets re-run without disturbing the other frozen results."""
    files = sorted(p for p in LOGO_DIR.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if only:
        files = [f for f in files if only.lower() in f.name.lower()]
    return files[:limit] if limit else files


# ── Deterministic checks — the things the judge cannot do ──

def _dominant(img: Image.Image, n: int = 8) -> list:
    """The most common SATURATED colours, quantised, each with its share of the subject.
    White/grey/black are skipped: they carry no hue, and here they are background rather than
    brand colour."""
    rgb = np.asarray(img.convert("RGB")).astype(int)
    alpha = np.asarray(img.convert("RGBA").getchannel("A"))
    px = rgb.reshape(-1, 3)[alpha.reshape(-1) > 200]
    if not len(px):
        return []
    mx, mn = px.max(1), px.min(1)
    px = px[(mx - mn > 40) & (mx > 40)]
    if not len(px):
        return []
    counts = Counter(map(tuple, (px // 24 * 24)))
    total = sum(counts.values())
    out = []
    for col, cnt in counts.most_common(n):
        hue = colorsys.rgb_to_hls(*[v / 255 for v in col])[0] * 360
        out.append({"rgb": [int(c) for c in col], "hue": round(hue, 1),
                    "share": round(cnt / total * 100, 1)})
    return out


def _colour_drift(orig: Image.Image, out: Image.Image) -> dict:
    """For each main colour of the original, the nearest colour actually present in the output,
    measured as RGB distance.

    Distance, not hue, and deliberately. Two earlier attempts both failed, in opposite directions:
    matching the top-4 to the top-4 by hue reported 162° for a gold that had merely dropped in
    rank, and widening the pool made every hue find an exact twin, so the check could never fail.
    Distance handles both — a shifted colour AND a colour that has left the palette score badly,
    because nothing near it exists. A colour must hold at least 1% of the subject to count as
    present, so a stray handful of pixels cannot satisfy the match. Calibrated on Trollbäckens GK
    2026-08-31: the drifted output scores 59, the good one 0.
    """
    ref = [c for c in _dominant(orig, 6) if c["share"] >= 2]
    pool = [c for c in _dominant(out, 12) if c["share"] >= 1]
    if not ref or not pool:
        return {"pairs": [], "mean_distance": None, "max_distance": None, "major_moved": []}
    pairs = []
    for c in ref:
        near = min(pool, key=lambda d: sum((a - b) ** 2 for a, b in zip(d["rgb"], c["rgb"])))
        dist = sum((a - b) ** 2 for a, b in zip(near["rgb"], c["rgb"])) ** 0.5
        hue_delta = min(abs(near["hue"] - c["hue"]), 360 - abs(near["hue"] - c["hue"]))
        pairs.append({"orig": c, "out": near, "distance": round(dist, 1),
                      "hue_delta": round(hue_delta, 1)})
    # Share-weighted mean, not the max. Quantisation splits one gold into several neighbouring
    # bins, and the smallest of those are JPEG artefacts in the ORIGINAL rather than anything the
    # pipeline did; a max would let that noise set the score. Weighting lets the colours that
    # actually cover the logo decide. A separate alarm covers the other failure the mean would
    # hide: one MAJOR colour moving a long way while everything else stays put.
    weight = sum(p["orig"]["share"] for p in pairs) or 1
    mean = sum(p["distance"] * p["orig"]["share"] for p in pairs) / weight
    major = [p for p in pairs if p["orig"]["share"] >= 5 and p["distance"] > MAX_COLOUR_DISTANCE]
    return {"pairs": pairs, "mean_distance": round(mean, 1),
            "max_distance": round(max(p["distance"] for p in pairs), 1),
            "major_moved": [p["orig"]["rgb"] for p in major]}


def _trapped_background(img: Image.Image) -> dict:
    """Opaque regions that (a) look like the removed background and (b) are fully surrounded by
    the subject. The background is removed from the outside in, so an enclosed pocket keeps it.

    Reported separately as pockets and SEAMS: a long flat sliver right across the image is a
    tiling artefact from the upscaler, not a hole the removal missed, and it wants a different fix.
    """
    rgb = np.asarray(img.convert("RGB")).astype(int)
    alpha = np.asarray(img.getchannel("A"))
    opaque = alpha > 200
    subject_px = int(opaque.sum())
    whiteish = (rgb.min(axis=2) > 225) & opaque

    floor = max(TRAPPED_FLOOR_PX, int(subject_px * TRAPPED_FLOOR_FRAC))
    lbl, n = ndimage.label(whiteish)
    if n == 0:
        return {"pockets": [], "seams": [], "total_px": 0, "floor": floor, "subject_px": subject_px}
    sizes = ndimage.sum(whiteish, lbl, range(1, n + 1))
    boxes = ndimage.find_objects(lbl)
    h, w = whiteish.shape

    pockets, seams, mask = [], [], np.zeros_like(whiteish)
    for i, size in enumerate(sizes):
        if size < floor:
            continue
        ys, xs = boxes[i]
        if ys.start == 0 or xs.start == 0 or ys.stop == h or xs.stop == w:
            continue  # touches the border → it is the outside, not trapped
        bh, bw = ys.stop - ys.start, xs.stop - xs.start
        item = {"px": int(size), "box": [int(xs.start), int(ys.start), int(bw), int(bh)]}
        (seams if (bh <= SEAM_MAX_HEIGHT and bw >= bh * SEAM_MIN_ASPECT) else pockets).append(item)
        mask |= (lbl == i + 1)

    return {"pockets": pockets, "seams": seams, "floor": floor, "subject_px": subject_px,
            "total_px": int(sum(p["px"] for p in pockets + seams)), "_mask": mask}


def inspect(orig_path: Path, out_path: Path) -> dict:
    """Every deterministic assertion for one result, plus a pass/fail per assertion."""
    out = Image.open(out_path)
    orig = Image.open(orig_path)
    w, h = out.size
    alpha = np.asarray(out.convert("RGBA").getchannel("A"))
    transparent_pct = float((alpha == 0).mean() * 100)
    trapped = _trapped_background(out.convert("RGBA"))
    drift = _colour_drift(orig, out)

    checks = {
        "resolution": {"ok": w * h >= MIN_PIXELS, "value": f"{w}×{h} = {w*h/1e6:.2f} MP",
                       "want": f"≥ {MIN_PIXELS/1e6:.1f} MP"},
        "transparency": {"ok": transparent_pct > 1, "value": f"{transparent_pct:.1f}% genomskinligt",
                         "want": "alfakanal med faktiskt genomskinliga pixlar"},
        # Removed as a check entirely, 2026-08-31. Two detectors were built and both were
        # falsified against Andreas's own verdicts within minutes: "enclosed background left
        # behind" flagged 4.3M px on Warner and 1.55M on team USA (their own light areas), and the
        # inverted "holes punched inside the logo" stayed silent on Knivsta — the one real
        # over-removal — while flagging Hammarby, which he called perfect. The rule is semantic,
        # not topological: background OUTSIDE the design goes, everything the design encloses
        # stays, and a lettering-only logo inverts that. No pixel count knows where a design ends.
        # Background correctness belongs to the judge and to human eyes.
        "seam": {"ok": not trapped["seams"],
                 "value": ", ".join(f"{s['px']:,} px ({s['box'][2]}×{s['box'][3]})"
                                    for s in trapped["seams"]) or "ingen",
                 "want": "inga långsmala fogar"},
        # Colour is measured (see `drift` below) but NOT judged. Three metrics were tried and
        # all three failed against the human verdicts: hue-vs-hue reported 162° for a colour that
        # merely dropped in rank; a wider pool could never fail; share-weighted distance missed
        # Chicago entirely, whose fault is that a colour DRAINED TO GREY — and the metric skips
        # grey to avoid the background. Mean saturation failed too (+6.6 on the broken one, -67.3
        # on an approved one). The metric can see that a colour CHANGED, never whether the change
        # was wanted: leopards' white text turning blue was flagged by the code and praised by the
        # human. That is a question about intent, and it belongs in the rubric.
    }
    return {"checks": checks, "trapped": {k: v for k, v in trapped.items() if k != "_mask"},
            "drift": drift, "_mask": trapped.get("_mask")}


# ── Pipeline + judge ──

def run_pipeline(path: Path, key: str) -> dict:
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    t0 = time.time()
    with open(path, "rb") as f:
        r = requests.post(PIPELINE_URL, headers={"X-API-Key": key},
                          files={"image": (path.name, f, mime)}, timeout=PIPELINE_TIMEOUT_S)
    r.raise_for_status()
    out_name = f"{path.stem}.png"
    (OUT_DIR / out_name).write_bytes(r.content)
    return {"logo": path.name, "output": out_name,
            "request_id": r.headers.get("x-request-id", ""),
            "cost": float(r.headers.get("x-cost", 0) or 0),
            "latency_s": round(time.time() - t0, 1)}


def poll_for(request_ids: set, key: str, profile_id: int) -> dict:
    deadline = time.time() + EVAL_POLL_TIMEOUT_S
    found = {}
    while time.time() < deadline and request_ids:
        r = requests.get(EVAL_URL, headers={"X-API-Key": key},
                         params={"limit": max(50, len(request_ids) + 10), "profile_id": profile_id},
                         timeout=30)
        r.raise_for_status()
        results = {res["request_id"]: res for res in r.json().get("results", [])}
        found = {rid: results[rid] for rid in request_ids if rid in results}
        if len(found) == len(request_ids):
            return found
        print(f"  …väntar på domaren ({len(found)}/{len(request_ids)} klara)", flush=True)
        time.sleep(5)
    return found


# ── Report ──

_REPORT_HTML = """<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><title>Heja · team-logo</title>
<style>
  :root { font-family: system-ui, -apple-system, sans-serif; }
  body { margin: 0; background: #0f1115; color: #e8eaed; }
  header { padding: 18px 24px; border-bottom: 1px solid #262a33; position: sticky; top: 0; background: #0f1115; z-index: 2; }
  h1 { font-size: 16px; margin: 0 0 12px; letter-spacing: .5px; }
  .tab { background: #1a1d24; color: #aeb4bf; border: 1px solid #2b303b; border-radius: 999px; padding: 7px 14px; font-size: 13px; cursor: pointer; margin-right: 8px; }
  .tab.active { background: #2563eb; color: #fff; border-color: #2563eb; }
  section.tabsec[hidden] { display: none; }
  .settings { margin: 18px 24px 0; background: #161922; border: 1px solid #262a33; border-radius: 10px; padding: 14px 16px; font-size: 12px; color: #cbd2dc; }
  .settings h2 { font-size: 12px; margin: 0 0 10px; color: #8b93a1; text-transform: uppercase; letter-spacing: .6px; }
  .settings table { border-collapse: collapse; margin-bottom: 10px; }
  .settings td { padding: 2px 14px 2px 0; vertical-align: top; }
  .settings .null { color: #5c6473; font-style: italic; }
  .settings details summary { cursor: pointer; color: #8b93a1; margin-top: 6px; }
  .settings pre { white-space: pre-wrap; background: #10131a; border: 1px solid #262a33; border-radius: 8px; padding: 12px; margin: 8px 0 0; max-width: 900px; font-size: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(760px, 1fr)); gap: 20px; padding: 24px; }
  .card { background: #161922; border: 1px solid #262a33; border-radius: 12px; padding: 14px; }
  .card h3 { margin: 0 0 10px; font-size: 13px; color: #e8eaed; font-weight: 600; }
  .cols { display: flex; gap: 12px; }
  figure { margin: 0; flex: 1; min-width: 0; }
  figcaption { font-size: 11px; color: #8b93a1; margin-bottom: 5px; text-transform: uppercase; letter-spacing: .5px; }
  img { width: 100%; height: auto; border-radius: 6px; display: block; background: #000; cursor: zoom-in; }
  .checks { margin-top: 12px; width: 100%; border-collapse: collapse; font-size: 12px; }
  .checks td { padding: 4px 8px; border-top: 1px solid #22262f; }
  .checks td:first-child { color: #8b93a1; width: 150px; }
  .ok { color: #4ade80; } .bad { color: #f87171; }
  .verdict { margin-top: 10px; font-size: 12px; color: #aeb4bf; }
  .missing { aspect-ratio: 1; display: grid; place-items: center; color: #4a505c; border: 1px dashed #2b303b; border-radius: 6px; }
  #lb { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.92); z-index: 10; place-items: center; cursor: zoom-out; padding: 24px; }
  #lb img { width: auto; height: auto; max-width: 96vw; max-height: 92vh; object-fit: contain; border-radius: 8px; }
</style></head>
<body>
  <header><h1>Heja · team-logo-nb-pro</h1><div class="tabs">%TABS%</div></header>
  %SECTIONS%
  <div id="lb" onclick="this.style.display='none'"><img id="lbimg" alt=""></div>
  <script>
    function zoom(s){ document.getElementById('lbimg').src = s; document.getElementById('lb').style.display = 'grid'; }
    document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
      document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      document.querySelectorAll('section.tabsec').forEach(s => s.hidden = s.id !== t.dataset.sec);
    });
  </script>
</body></html>"""


# Drawn AFTER the thumbnail — see run_all.py: a grid rendered at full resolution and then shrunk
# reads as flat white, which hides the very thing it is there to show.
def _checkerboard(size, square=15) -> Image.Image:
    w, h = size
    a = np.full((h, w, 3), 255, dtype=np.uint8)
    ys, xs = np.mgrid[0:h, 0:w]
    a[((ys // square + xs // square) % 2) == 1] = 200
    return Image.fromarray(a)


def _embed(im: Image.Image, max_dim: int = 1100) -> str:
    im = im.convert("RGB")
    if max(im.size) > max_dim:
        im.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _views(orig_path: Path, out_path: Path, mask) -> list:
    """Original · output on a checkerboard · defects marked. The checkerboard is not decoration:
    against white, leftover white background is invisible, which is exactly how it slipped past
    the judge. The third view is the same data with the deterministic finding drawn on it, so a
    defect is traceable rather than merely asserted."""
    views = [("Original", _embed(Image.open(orig_path)))]
    out = Image.open(out_path).convert("RGBA")
    small = out.copy()
    small.thumbnail((1100, 1100))
    views.append(("Utdata · rutmönster = genomskinligt",
                  _embed(Image.alpha_composite(_checkerboard(small.size).convert("RGBA"), small))))
    if mask is not None and mask.any():
        arr = np.asarray(out).copy()
        arr[mask] = (255, 0, 0, 255)
        plate = Image.alpha_composite(Image.new("RGBA", out.size, (40, 40, 48, 255)),
                                      Image.fromarray(arr))
        views.append(("Fynd · rött = instängd bakgrund", _embed(plate)))
    return views


def _card(logo: str, out_rel: str, checks: dict, judge: dict | None) -> str:
    orig_path, out_path = LOGO_DIR / logo, OUT_DIR / out_rel
    if not out_path.exists():
        return (f'<div class="card"><h3>{html.escape(logo)}</h3>'
                f'<div class="missing">utdata saknas</div></div>')

    mask = None
    if checks:
        mask = inspect(orig_path, out_path).get("_mask")  # recomputed for the overlay only
    cols = "".join(
        f'<figure><figcaption>{html.escape(label)}</figcaption>'
        f'<img src="{uri}" onclick="zoom(this.src)"></figure>'
        for label, uri in _views(orig_path, out_path, mask))

    rows = ""
    for name, c in (checks or {}).items():
        cls = "ok" if c["ok"] else "bad"
        rows += (f'<tr><td>{html.escape(name)}</td>'
                 f'<td class="{cls}">{"✅" if c["ok"] else "❌"} {html.escape(str(c["value"]))}</td>'
                 f'<td style="color:#5c6473">{html.escape(c["want"])}</td></tr>')

    verdict = ""
    if judge:
        dims = " · ".join(f"{k} {v}" for k, v in (judge.get("dimension_scores") or {}).items())
        verdict = (f'<div class="verdict"><b>Domaren: {judge.get("score")} '
                   f'({html.escape(str(judge.get("verdict")))})</b><br>{html.escape(dims)}<br>'
                   f'{html.escape((judge.get("reasoning") or "")[:400])}</div>')

    return (f'<div class="card"><h3>{html.escape(logo)}</h3><div class="cols">{cols}</div>'
            f'<table class="checks">{rows}</table>{verdict}</div>')


def _settings_box() -> str:
    chain = "".join(f'<tr><td>{n}</td><td>{html.escape(name)}</td>'
                    f'<td style="color:#8b93a1">{html.escape(impl)}</td>'
                    f'<td style="color:#5c6473">{html.escape(note)}</td></tr>'
                    for n, name, impl, note in NODE_CHAIN)
    params = ""
    for node, ps in PARAM_SURFACE.items():
        vals = ", ".join(
            f'{k}=<span class="null">null</span>' if v is None else f"{k}={html.escape(str(v))}"
            for k, v in ps.items())
        params += f'<tr><td>{html.escape(node)}</td><td>{vals}</td></tr>'
    return (f'<div class="settings"><h2>Vad som kördes</h2>'
            f'<table>{chain}</table>'
            f'<h2>Hela parameterytan — <span class="null">null</span> = API:ets default, alltså otrimmad</h2>'
            f'<table>{params}</table>'
            f'<table><tr><td>upplösningskrav</td><td>{MIN_PIXELS:,} px</td></tr>'
            f'<tr><td>golv, instängd bakgrund</td><td>max({TRAPPED_FLOOR_PX:,} px, '
            f'{TRAPPED_FLOOR_FRAC:.4%} av motivet)</td></tr></table>'
            f'<details><summary>Nano Banana Pro · prompt (ordagrant)</summary>'
            f'<pre>{html.escape(NB_PRO_PROMPT)}</pre></details></div>')


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "run"


def save_tab(runs: list, title: str) -> list:
    """Freeze this run as a new tab — outputs copied into out/tabs/<slug>/ so a later run cannot
    overwrite them. A new method is ALWAYS a new tab; never overwrite an old one."""
    evals = json.loads(EVALS_JSON.read_text()) if EVALS_JSON.exists() else []
    slug = f"{len(evals) + 1:02d}-{_slug(title)}"
    tabdir = TABS_DIR / slug
    tabdir.mkdir(parents=True, exist_ok=True)
    items = []
    for r in runs:
        src = OUT_DIR / r["output"]
        if src.exists():
            shutil.copy2(src, tabdir / r["output"])
            items.append({**r, "output": f"tabs/{slug}/{r['output']}"})
    evals.append({"title": title, "slug": slug, "prompt": NB_PRO_PROMPT, "items": items})
    EVALS_JSON.write_text(json.dumps(evals, indent=2, ensure_ascii=False))
    return evals


def build_report() -> Path:
    evals = json.loads(EVALS_JSON.read_text()) if EVALS_JSON.exists() else []
    tabs, sections = [], []
    for i, ev in enumerate(reversed(evals)):
        sid, active = f"sec-{ev['slug']}", (" active" if i == 0 else "")
        tabs.append(f'<button class="tab{active}" data-sec="{sid}">{html.escape(ev["title"])}</button>')
        cards = "".join(_card(it["logo"], it["output"], it.get("checks"), it.get("judge"))
                        for it in ev["items"])
        sections.append(f'<section class="tabsec" id="{sid}"{"" if i == 0 else " hidden"}>'
                        f'{_settings_box()}<div class="grid">{cards}</div></section>')
    out = OUT_DIR / "report.html"
    out.write_text(_REPORT_HTML.replace("%TABS%", "".join(tabs)).replace("%SECTIONS%", "".join(sections)),
                   encoding="utf-8")
    return out


def _heartbeat(state: dict, total: int, stop: threading.Event) -> None:
    """A run whose calls stall still has to show a signal, or a hang is only noticed hours later."""
    while not stop.wait(300):
        done, elapsed = state["done"], time.time() - state["t0"]
        eta = (elapsed / done * (total - done)) if done else 0
        print(f"  ♥ {done}/{total} klara · {elapsed/60:.0f} min · ETA {eta/60:.0f} min", flush=True)


def summarise(items: list) -> None:
    print("\n" + "=" * 72)
    print(f"DETERMINISTISKA KONTROLLER — {len(items)} loggor")
    print("=" * 72)
    names = ["resolution", "transparency", "seam"]
    def glyph(v):
        return "…" if v is None else ("✅" if v else "❌")
    for it in items:
        c = it.get("checks") or {}
        flags = " ".join(f"{n[:4]}{glyph(c.get(n, {}).get('ok'))}" for n in names)
        print(f"  {it['logo'][:34]:34s} {flags}   {it.get('latency_s', '?')}s")
    print("\n  … = mätt men inte dömt, kräver ögon")
    for n in names:
        vals = [(it["logo"], (it.get("checks") or {}).get(n, {}).get("ok", True)) for it in items]
        if all(v is None for _, v in vals):
            flagged = [l for l, _ in vals if (dict(vals)[l] is None)]
            print(f"\n  {n}: inte dömt — se rapporten")
            continue
        bad = [l for l, v in vals if v is False]
        print(f"\n  {n}: {sum(1 for _, v in vals if v)}/{len(items)} godkända"
              + (f" — faller: {', '.join(b[:24] for b in bad)}" if bad else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="run only the first N logos")
    ap.add_argument("--report-only", action="store_true", help="rebuild the report from frozen runs")
    ap.add_argument("--dry-run", action="store_true", help="list the set, spend nothing")
    ap.add_argument("--fresh", action="store_true", help="ignore cached outputs and re-run")
    ap.add_argument("--profile-id", type=int, default=0, help="also pull scores from this eval profile")
    ap.add_argument("--only", default="", help="run only logos whose filename contains this")
    ap.add_argument("--tab", default="", help="tab label for this run (default: a timestamp)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.report_only:
        print(f"HTML-rapport: {build_report()}")
        return

    logos = load_set(args.limit, args.only)
    print(f"Testset: {LOGO_DIR}\n{len(logos)} bilder:")
    for p in logos:
        print(f"  {p.name}")
    if args.dry_run:
        print("\n--dry-run: inget kördes, inget kostade.")
        return

    key = api_key()
    cached = {}
    if RUNS_JSON.exists() and not args.fresh:
        cached = {r["logo"]: r for r in json.loads(RUNS_JSON.read_text())}

    print(f"\nKör {len(logos)} bilder genom {PIPELINE_SLUG}…")
    state, stop = {"done": 0, "t0": time.time()}, threading.Event()
    threading.Thread(target=_heartbeat, args=(state, len(logos), stop), daemon=True).start()

    runs = []
    for i, path in enumerate(logos, 1):
        prev = cached.get(path.name)
        if prev and (OUT_DIR / prev.get("output", "")).exists():
            print(f"  [{i}/{len(logos)}] {path.name[:34]:34s} — hoppar (redan klar)", flush=True)
            runs.append(prev)
            state["done"] += 1
            continue
        try:
            run = run_pipeline(path, key)
            runs.append(run)
            state["done"] += 1
            elapsed = time.time() - state["t0"]
            eta = elapsed / state["done"] * (len(logos) - state["done"])
            print(f"  [{i}/{len(logos)}] {path.name[:34]:34s} {run['latency_s']:>6.1f}s "
                  f"· ETA {eta/60:.1f} min", flush=True)
        except Exception as e:
            print(f"  [{i}/{len(logos)}] {path.name[:34]:34s} ✗ {e}", flush=True)
    stop.set()
    RUNS_JSON.write_text(json.dumps(runs, indent=2, ensure_ascii=False))

    for r in runs:
        out_path = OUT_DIR / r["output"]
        if out_path.exists():
            r["checks"] = inspect(LOGO_DIR / r["logo"], out_path)["checks"]

    if args.profile_id:
        ids = {r["request_id"] for r in runs if r.get("request_id")}
        print(f"\nHämtar domarens poäng för {len(ids)} körningar (profil {args.profile_id})…")
        judged = poll_for(ids, key, args.profile_id)
        for r in runs:
            if r.get("request_id") in judged:
                r["judge"] = judged[r["request_id"]]

    summarise(runs)
    cost = sum(r.get("cost", 0) for r in runs)
    print(f"\nPipeline-kostnad ~${cost:.2f} · total tid {(time.time()-state['t0'])/60:.1f} min")

    save_tab(runs, args.tab or time.strftime("%Y-%m-%d %H:%M"))
    print(f"\nHTML-rapport: {build_report()}\n  → öppna i webbläsaren (bilder inbäddade, klicka för zoom).")


if __name__ == "__main__":
    main()
