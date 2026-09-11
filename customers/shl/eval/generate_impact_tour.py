#!/usr/bin/env python3
"""
SHL Impact Tour — per-club marketing graphic generator.

Renders one PNG per SHL club for the seasonal Impact Tour campaign from
ONE master Photoshop file plus per-club photo and config.

Architecture:
  1. Open master PSD via psd-tools (a single source of truth)
  2. Hide Brynäs-specific reference layers (the worked example)
  3. Render the base — everything shared across clubs
  4. Composite per-club elements on top:
     - Tinted photo (photo*0.25 + color*0.75 within the Rectangle mask)
     - Highlight ring (Ellipse 1 recolored, positioned at club's pin)
     - Club name + date text (Anton font, white, fixed position)

Usage:
    python3 generate_impact_tour.py --club brynäs
    python3 generate_impact_tour.py --all
"""

import argparse
import json
import os
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from psd_tools import PSDImage

# ── Paths ──
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_FONT_PATH = SCRIPT_DIR / "fonts" / "Anton-Regular.ttf"
DEFAULT_CONTENT_ROOT = (
    "/Users/andreasquensel/Library/CloudStorage/"
    "GoogleDrive-andreas@zebrolabs.com/Shared drives/"
    "Apiai.me/Customers/SHL/Content"
)
# Per-club photos live INSIDE the Content folder by default — keeps
# everything for SHL in one place.
DEFAULT_CLUBS_ROOT = f"{DEFAULT_CONTENT_ROOT}/Clubs"

# ── Composit-tuning ──
TEXT_POSITION = (83, 428)     # Brynäs IF text bbox top-left in PSD
TEXT_SIZE = 38                # tuned to match Brynäs IF render (50px tall bbox)
TEXT_COLOR = (255, 255, 255)  # white
PHOTO_WEIGHT = 0.25
COLOR_WEIGHT = 1.0 - PHOTO_WEIGHT   # derived so the two always sum to 1
# Uniform sizing for non-chosen clubs (every non-chosen club fits in this box)
NORMAL_LOGO_BOX_PX = 65       # max dimension; aspect preserved
NORMAL_DATE_HEIGHT_PX = 16    # date label height; aspect preserved
# Enlarged sizing for the chosen club
CHOSEN_LOGO_BOX_PX = 105      # ~1.6x normal
CHOSEN_DATE_HEIGHT_PX = 26    # ~1.6x normal

# ── PSD layer naming convention ──
# These names MUST match the layer names in the master PSD. See
# SHL/Content/README.md for the full convention and where to update.

# Top-level single layers
LAYER_TEXTURE         = "texture"          # grunge background
LAYER_TEAM_RECTANGLE  = "team_rectangle"   # jagged tint-zone shape (alpha mask)
LAYER_ROAD            = "road"             # dotted road line
LAYER_SHL_LOGO        = "shl_logo"         # SHL Impact Tour wordmark

# Per-club placeholder layers — hidden by the script and replaced with
# the chosen club's content (color, photo, heading text). These remain
# named after Brynäs's example in the worked PSD, but the script does
# not depend on their content — only their existence by name.
PLACEHOLDER_LAYERS = {
    "team_color",        # Color Fill — placeholder tint colour
    "team_photo",        # Smart object — placeholder publikbild
    "team_heading",      # Type layer — placeholder club name + date heading
}

# Highlight ring — drawn programmatically (no PSD layer needed). Filled
# circle in the chosen club's color at 50% opacity, positioned over the
# chosen pin. 120 px matches the original PSD's Ellipse 1 (119x120).
HIGHLIGHT_DIAMETER_PX = 120
HIGHLIGHT_OPACITY     = 0.5

# Top-level groups (rendered above the tint zone)
GROUP_MAP        = "map"            # contains sweden + highlight + clubs
GROUP_SWEDEN     = "sweden"         # nested in map; sweden silhouette + white fill
GROUP_CLUBS      = "clubs"          # nested in map; all 14 per-club groups
GROUP_TEXT       = "text"           # season text + 14 NEDSLAG + heading

TOP_GROUPS       = {GROUP_MAP, GROUP_TEXT, LAYER_SHL_LOGO}
SWEDEN_LAYERS    = {GROUP_SWEDEN, "sweden_shape", "sweden_fill"}

# Klubb-grupp-namn i PSD:n hämtas från clubs_*.json — single source of truth.
# Auto-populeras i load_config() istället för att vara hårdkodat här.


# ─────────────────────────── helpers ───────────────────────────

def _find_club_photo(clubs_root, club_id):
    """Find a club's photo at the strict path: Clubs/{id}/photo.{jpg,png,jpeg}.
    Folder match is case-insensitive AND Unicode-normalized (macOS HFS+
    returns NFD form for Swedish chars while JSON strings are NFC, so we
    normalize both sides before compare). Filename must be 'photo' verbatim."""
    if not clubs_root.exists():
        return None
    target = unicodedata.normalize("NFC", club_id).lower()
    for entry in clubs_root.iterdir():
        if not entry.is_dir():
            continue
        name_nfc = unicodedata.normalize("NFC", entry.name).lower()
        if name_nfc != target:
            continue
        for ext in (".jpg", ".jpeg", ".png"):
            p = entry / f"photo{ext}"
            if p.exists():
                return p
    return None


def hex_to_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))


def load_config(path):
    try:
        with open(path) as f:
            config = json.load(f)
    except FileNotFoundError:
        sys.exit(f"Config not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"Config {path} has invalid JSON: {e}")
    if "clubs" not in config:
        sys.exit(f"Config {path} missing 'clubs' field.")
    # Build the club-id lookup set (used to recognise PSD groups). All
    # ids are NFC-normalised + lowercased for consistent matching.
    config["_club_ids"] = {
        unicodedata.normalize("NFC", c["id"]).lower() for c in config["clubs"]
    }
    return config


def extract_psd_assets(psd, club_ids):
    """Pull out the bits we need from the master PSD as PIL images / data.

    Raises SystemExit if a required layer is missing — better to fail loud
    here than render a silently-broken image."""
    assets = {}
    for layer in psd.descendants():
        # The team_rectangle smartobject — its alpha channel is the
        # tint-zone shape.
        if layer.name.strip() == LAYER_TEAM_RECTANGLE and layer.kind == "smartobject":
            rect_img = layer.composite()
            assets["rectangle_image"] = rect_img
            assets["rectangle_bbox"] = layer.bbox

    if "rectangle_image" not in assets:
        sys.exit(
            f"PSD missing required smart-object layer {LAYER_TEAM_RECTANGLE!r}. "
            f"This is the jagged tint-zone shape. Check PSD layer naming."
        )

    # Pin positions per club = the smart object (logo) bbox center within
    # each club's group.
    pin_positions = {}
    for _, group in _iter_club_groups(psd, club_ids):
        key = unicodedata.normalize("NFC", group.name).strip().lower()
        for child in group.descendants():
            if child.kind in ("smartobject", "pixel") and child.bbox != (0, 0, 0, 0):
                x1, y1, x2, y2 = child.bbox
                pin_positions[key] = ((x1 + x2) // 2, (y1 + y2) // 2)
                break
    assets["pin_positions"] = pin_positions
    return assets


# Z-ordering. PSD layer stack (bottom → top):
#   texture, team_rectangle, team_color, team_photo, road, map (sweden +
#   highlight_circle + clubs), text, shl_logo
# We render in passes that mirror this.
ALL_NON_BOTTOM_LAYERS = TOP_GROUPS | {LAYER_ROAD}


def _set_visibility(psd, hide_names):
    """Set layer visibility per name set, return list of (layer, prev_state)
    so we can restore later. Matches names with NFC normalisation +
    .strip() + .lower() so accidental trailing spaces or NFD-vs-NFC
    Unicode forms don't cause silent matching failures."""
    targets = {unicodedata.normalize("NFC", n).strip().lower() for n in hide_names}
    saved = []
    for layer in psd.descendants():
        name = unicodedata.normalize("NFC", layer.name).strip().lower()
        if name in targets:
            saved.append((layer, layer.visible))
            layer.visible = False
    return saved


def _restore_visibility(saved):
    for layer, prev in saved:
        layer.visible = prev


def render_bottom(psd):
    """Render texture + team_rectangle only — everything above the tint
    zone (road, sweden, map, text, logo) is hidden, plus the team_color
    + team_photo placeholders (we replace those with our recoloured tint)."""
    saved = _set_visibility(psd, ALL_NON_BOTTOM_LAYERS | PLACEHOLDER_LAYERS)
    try:
        bottom = psd.composite().convert("RGBA")
    finally:
        _restore_visibility(saved)
    return bottom


def render_road(psd):
    """Render just the road layer at canvas size as a transparent overlay."""
    for layer in psd.descendants():
        if layer.name == LAYER_ROAD:
            return layer.composite(viewport=psd.viewbox).convert("RGBA")
    return Image.new("RGBA", (psd.width, psd.height), (0, 0, 0, 0))


def render_sweden(psd):
    """Render the sweden group (silhouette + white fill) as a transparent
    overlay. Goes UNDER the highlight ring in z-order."""
    for layer in psd.descendants():
        if layer.name == GROUP_SWEDEN and layer.kind == "group":
            return layer.composite(viewport=psd.viewbox).convert("RGBA")
    return Image.new("RGBA", (psd.width, psd.height), (0, 0, 0, 0))


def render_clubs_text_logo(psd):
    """Render the FOREGROUND: club logos on map + date labels + heading
    text + 14 NEDSLAG + SHL Impact Tour logo. All placeholder layers
    (team_color, team_photo, team_heading, highlight_circle) are hidden,
    as are all the bottom layers we've already composed manually."""
    saved = _set_visibility(psd, PLACEHOLDER_LAYERS)
    foreground_blockers = {
        LAYER_TEXTURE, LAYER_ROAD, LAYER_TEAM_RECTANGLE,
    } | SWEDEN_LAYERS
    saved2 = _set_visibility(psd, foreground_blockers)
    try:
        top = psd.composite().convert("RGBA")
    finally:
        _restore_visibility(saved2)
        _restore_visibility(saved)
    return top


def composite_tinted_photo(base, photo_pil, color_rgb, rectangle_img, rectangle_bbox):
    """Paste a club-color-tinted photo into the tint zone defined by Rectangle's alpha.

    Formula: final = photo * 0.25 + color * 0.75 within the mask.
    """
    canvas_w, canvas_h = base.size

    # The Rectangle smartobject sits at bbox (x_left, ...) on canvas.
    # Crop its alpha to the canvas-visible portion.
    rect_x_left, rect_y_top, rect_x_right, rect_y_bottom = rectangle_bbox
    rect_arr = np.asarray(rectangle_img)            # shape (H, W, 4)
    rect_alpha = rect_arr[..., 3]                   # the shape mask

    # We need a canvas-sized alpha mask. Start with zeros, paste Rectangle's
    # alpha at its bbox.
    canvas_mask = np.zeros((canvas_h, canvas_w), dtype=np.uint8)
    # Clip the rect alpha to canvas dims
    src_h, src_w = rect_alpha.shape
    paste_x = rect_x_left
    paste_y = rect_y_top
    crop_w = min(src_w, canvas_w - paste_x)
    crop_h = min(src_h, canvas_h - paste_y)
    if crop_w > 0 and crop_h > 0:
        canvas_mask[paste_y:paste_y + crop_h, paste_x:paste_x + crop_w] = \
            rect_alpha[:crop_h, :crop_w]

    # Crop the photo horizontally to match the canvas aspect ratio,
    # then scale to canvas size. The right portion of the photo
    # naturally lands in the tint zone (canvas right half) when the
    # photo is laid full-canvas. Matches how the PSD's smart object
    # positions its content: photo bleeds across the canvas, mask
    # picks the visible portion.
    photo_canvas_img = _fit_photo_to_canvas(photo_pil, canvas_w, canvas_h)
    photo_arr = np.asarray(photo_canvas_img.convert("RGB"), dtype=np.float32)

    color_layer = np.full_like(photo_arr, color_rgb, dtype=np.float32)
    tinted = photo_arr * PHOTO_WEIGHT + color_layer * COLOR_WEIGHT  # (H, W, 3)

    # Apply the canvas-sized alpha mask
    alpha = canvas_mask.astype(np.float32) / 255.0
    out = np.asarray(base, dtype=np.float32).copy()
    for c in range(3):
        out[..., c] = out[..., c] * (1 - alpha) + tinted[..., c] * alpha
    # Keep base's alpha
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGBA")


def _cover_fit(img, w, h):
    """Resize img to cover (w, h) preserving aspect, then center-crop."""
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    new_w, new_h = int(round(iw * scale)), int(round(ih * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    # Center-crop
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _fit_photo_to_canvas(img, w, h):
    """Cover-fit a club photo to the final canvas size.

    Behavior: scale the photo so it COVERS the canvas in both dimensions
    (whichever is the larger required scale wins), then center-crop equal
    amounts off both sides. The right portion of the resulting full-canvas
    image is what shows through the tint mask on the right half — natural
    framing for typical horizontal stadium / crowd shots, and never gets
    stretched.

    - Wider photo than canvas aspect: crop sides
    - Taller photo than canvas aspect: crop top + bottom
    - Narrower photo: scaled up to match width, then top/bottom cropped
    """
    return _cover_fit(img, w, h)


def composite_highlight(base, pin_position, color_rgb,
                        diameter=HIGHLIGHT_DIAMETER_PX,
                        opacity=HIGHLIGHT_OPACITY):
    """Draw a translucent filled circle in the chosen club's color, centred
    on the pin. Replaces what used to be the Ellipse 1 PSD layer — same
    visual result, no PSD dependency."""
    pin_x, pin_y = pin_position
    r = diameter // 2
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    alpha = int(round(255 * opacity))
    fill = (color_rgb[0], color_rgb[1], color_rgb[2], alpha)
    draw.ellipse([pin_x - r, pin_y - r, pin_x + r, pin_y + r], fill=fill)
    out = base.copy()
    out.alpha_composite(layer)
    return out


_font_cache = {}


def _get_font(path, size):
    """Cache ImageFont objects — small win, but no point re-reading the
    TTF file for every render in batch mode."""
    key = (str(path), size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(path), size=size)
    return _font_cache[key]


def composite_text(base, text, font_path, size=TEXT_SIZE, position=TEXT_POSITION,
                   color=TEXT_COLOR):
    """Render text in Anton and paste at the fixed PSD-derived position."""
    font = _get_font(font_path, size)
    out = base.copy()
    draw = ImageDraw.Draw(out)
    draw.text(position, text, font=font, fill=color)
    return out


# ───────────────────────── render pipeline ─────────────────────────

def _iter_club_groups(psd, club_ids):
    """Yield (normalized_lowercase_name, group_layer) for each per-club group
    in the PSD whose name matches one of the club ids in the config.
    Skips empty groups (e.g. a club still in the PSD but not in season)."""
    for layer in psd.descendants():
        if layer.kind != "group" or layer.bbox == (0, 0, 0, 0):
            continue
        key = unicodedata.normalize("NFC", layer.name).strip().lower()
        if key in club_ids:
            yield key, layer


def _find_logo_in_group(group):
    for child in group.descendants():
        if child.kind in ("smartobject", "pixel") and child.bbox != (0, 0, 0, 0):
            return child
    return None


def _find_date_in_group(group):
    for child in group.descendants():
        if child.kind == "type" and child.bbox != (0, 0, 0, 0):
            return child
    return None


def _fit_layer_within_box(canvas, layer, box_dim_px, anchor="center"):
    """Render `layer`, scale so its largest dimension == box_dim_px while
    preserving aspect, composite at original bbox center (or top-left).
    Sets layer.visible = False to suppress double-render. Returns
    (layer, prev_visible) for later restore, or None on failure."""
    if layer is None:
        return None
    img = layer.composite()
    if img is None:
        return None
    img = img.convert("RGBA")
    w, h = img.size
    if w <= 0 or h <= 0:
        return None
    scale = box_dim_px / max(w, h)
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    scaled = img.resize((new_w, new_h), Image.LANCZOS)
    x1, y1, x2, y2 = layer.bbox
    if anchor == "topleft":
        paste_x, paste_y = x1, y1
    else:
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        paste_x = cx - new_w // 2
        paste_y = cy - new_h // 2
    canvas.alpha_composite(scaled, (paste_x, paste_y))
    prev = layer.visible
    layer.visible = False
    return (layer, prev)


def _fit_layer_to_height(canvas, layer, target_h_px, anchor="topleft"):
    """Render `layer`, scale so height == target_h_px (preserve aspect),
    composite at original bbox top-left (so text stays anchored at its
    designed position). Used for date labels."""
    if layer is None:
        return None
    img = layer.composite()
    if img is None:
        return None
    img = img.convert("RGBA")
    w, h = img.size
    if h <= 0:
        return None
    scale = target_h_px / h
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    scaled = img.resize((new_w, new_h), Image.LANCZOS)
    x1, y1, x2, y2 = layer.bbox
    if anchor == "topleft":
        paste_x, paste_y = x1, y1
    else:
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        paste_x = cx - new_w // 2
        paste_y = cy - new_h // 2
    canvas.alpha_composite(scaled, (paste_x, paste_y))
    prev = layer.visible
    layer.visible = False
    return (layer, prev)


def render_club(psd, assets, club_data, photo_path, font_path, club_ids):
    """Z-ordered render — mirrors the PSD's own layer hierarchy:
        1. Texture + Rectangle (no road)
        2. Recolored tint zone (photo*0.25 + color*0.75 inside Rectangle mask)
        3. Road (over tint, under Sverige)
        4. Sverige silhouette (white)
        5. Recolored highlight ring at chosen club's pin
        6. Chosen club's ENLARGED logo at its pin (over the ring)
        7. Foreground: clubs group (with chosen club's normal logo hidden) +
           Text + SHL Logo
        8. Club name + date heading text (Anton)
    """
    color_rgb = hex_to_rgb(club_data["color"])
    photo = Image.open(photo_path).convert("RGB")

    bottom = render_bottom(psd)
    canvas = composite_tinted_photo(
        bottom, photo, color_rgb,
        assets["rectangle_image"], assets["rectangle_bbox"]
    )

    road = render_road(psd)
    canvas.alpha_composite(road)

    sweden = render_sweden(psd)
    canvas.alpha_composite(sweden)

    pin_pos = assets["pin_positions"].get(club_data["id"].lower())
    if pin_pos is None:
        print(f"  ⚠ pin position not found for {club_data['id']}, skipping highlight")
    else:
        canvas = composite_highlight(canvas, pin_pos, color_rgb)

    # Normalize ALL clubs to uniform size. Each non-chosen club gets
    # NORMAL_LOGO_BOX_PX (logo) + NORMAL_DATE_HEIGHT_PX (date). The chosen
    # club gets the larger CHOSEN_* sizes. Hides the PSD's native-size
    # versions so they don't double-render in the foreground pass.
    chosen_id = club_data["id"].lower()
    saved_layers = []
    for club_id, group in _iter_club_groups(psd, club_ids):
        if club_id == chosen_id:
            logo_dim, date_h = CHOSEN_LOGO_BOX_PX, CHOSEN_DATE_HEIGHT_PX
        else:
            logo_dim, date_h = NORMAL_LOGO_BOX_PX, NORMAL_DATE_HEIGHT_PX
        logo = _find_logo_in_group(group)
        date = _find_date_in_group(group)
        if logo is not None:
            s = _fit_layer_within_box(canvas, logo, logo_dim, anchor="center")
            if s: saved_layers.append(s)
        if date is not None:
            s = _fit_layer_to_height(canvas, date, date_h, anchor="topleft")
            if s: saved_layers.append(s)

    try:
        foreground = render_clubs_text_logo(psd)
        canvas.alpha_composite(foreground)
    finally:
        for layer, prev in saved_layers:
            layer.visible = prev

    text = f"{club_data['name']} {club_data['date_text']}"
    canvas = composite_text(canvas, text, font_path)
    return canvas


# ─────────────────────────── CLI / main ───────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--club", help="Club id to render. Omit for --all.")
    p.add_argument("--all",  action="store_true", help="Render every club in the config.")
    p.add_argument("--config", default=str(SCRIPT_DIR / "clubs_2526.json"))
    p.add_argument("--content-root",
                   default=os.environ.get("SHL_CONTENT_ROOT", DEFAULT_CONTENT_ROOT))
    p.add_argument("--clubs-root",
                   default=os.environ.get("SHL_CLUBS_ROOT", DEFAULT_CLUBS_ROOT),
                   help="Folder containing per-club photo subfolders.")
    p.add_argument("--font", default=str(DEFAULT_FONT_PATH))
    p.add_argument("--out-dir", help="Output dir (default: SHL/Evals/{today}_{season}).")
    args = p.parse_args()

    if not args.club and not args.all:
        sys.exit("Specify --club <id> or --all.")

    config = load_config(args.config)
    psd_path = Path(args.content_root) / config["psd_filename"]
    if not psd_path.exists():
        sys.exit(f"PSD not found: {psd_path}")

    out_dir = (Path(args.out_dir) if args.out_dir
               else Path(args.content_root).parent / "Evals" /
                    f"{date.today().isoformat()}_{config['season'].replace('/', '-')}")
    out_dir.mkdir(parents=True, exist_ok=True)

    clubs = ([c for c in config["clubs"] if c["id"] == args.club]
             if args.club else config["clubs"])
    if args.club and not clubs:
        sys.exit(f"Club {args.club!r} not in config. Available: "
                 + ", ".join(c["id"] for c in config["clubs"]))

    print(f"PSD:    {psd_path.name}")
    print(f"Season: {config['season']}")
    print(f"Output: {out_dir}")
    print(f"Clubs:  {len(clubs)}\n")

    t0 = time.time()
    print(f"[load] opening PSD...", end=" ", flush=True)
    psd = PSDImage.open(psd_path)
    print(f"done ({time.time()-t0:.1f}s, canvas {psd.width}x{psd.height})")

    t0 = time.time()
    print(f"[load] extracting assets...", end=" ", flush=True)
    assets = extract_psd_assets(psd, config["_club_ids"])
    print(f"done ({time.time()-t0:.1f}s, {len(assets['pin_positions'])} pin positions)")

    for club in clubs:
        photo_path = _find_club_photo(Path(args.clubs_root), club["id"])
        if photo_path is None:
            print(f"[render] {club['id']:20} → SKIPPED: no photo at "
                  f"{args.clubs_root}/{club['id']}/photo.{{jpg,png}}")
            continue
        out_path = out_dir / f"{club['id']}.png"
        t0 = time.time()
        print(f"[render] {club['id']:20} → {out_path.name} ...", end=" ", flush=True)
        try:
            img = render_club(psd, assets, club, photo_path, args.font,
                              config["_club_ids"])
            img.convert("RGB").save(out_path, optimize=True)
            print(f"done ({time.time()-t0:.1f}s, {out_path.stat().st_size:,} bytes)")
        except Exception as e:
            print(f"FAILED: {type(e).__name__}: {e}")

    print(f"\nDone. {out_dir}")


if __name__ == "__main__":
    main()
