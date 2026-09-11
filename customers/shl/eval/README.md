# SHL - Impact Tour Marketing Graphics

## Customer
Swedish Hockey League (SHL). Generates per-club marketing graphics for the seasonal Impact Tour campaign.

## Use Case
Render one marketing PNG per SHL club from ONE master Photoshop file + per-club photo + JSON config.

**Scale:** 14 clubs × 1 format (currently) = **14 outputs per season**. Plan to add 2 more formats (medium vertical + square) = 42 total.

## Pipeline

```
PSD (designer's master) ─┐
clubs_{year}.json        ├─► generate_impact_tour.py ─► one PNG per club
photo per club           ─┘
```

Architecture: opens PSD via `psd-tools`, composites z-ordered layers programmatically, replaces per-club placeholders (color, photo, heading text) with the chosen club's content. Highlight ring drawn in code (no PSD layer needed).

See **`generate_impact_tour.py`** docstring + the designer-facing **`SHL/Content/README.md`** (Google Drive) for the layer-naming convention.

## Files

```
evaluator/customers/shl/
├── generate_impact_tour.py   # main batch generator (psd-tools based)
├── clubs_2526.json           # per-season club data (name, color, dates)
├── fonts/Anton-Regular.ttf   # Google Fonts; for heading text
└── README.md                 # this file
```

Assets live on Google Drive (`Apiai.me/Customers/SHL/Content/`):
- `Original All Clubs.psd` — master template (one per season)
- `Clubs/{id}/photo.{jpg,png}` — one publikbild per club

## Usage

```bash
# Single club
python3 evaluator/customers/shl/generate_impact_tour.py --club brynäs

# All clubs in the config
python3 evaluator/customers/shl/generate_impact_tour.py --all
```

Output lands in `SHL/Evals/{today}_{season}/{club_id}.png`.

If a club's photo is missing, that club is skipped with a clear message (the path it tried) — no silent fallback.

## Per-season workflow

1. Open master PSD → update club groups (add Björklöven, remove Leksand for 26/27)
2. Update 14 date labels in PSD if tour schedule changed
3. Update `SÄSONGEN 25/26` text in PSD to the new season
4. Update `clubs_{year}.json` with new colors / dates / names
5. Drop new club photos into `SHL/Clubs/{id}/photo.{jpg,png}`
6. Run `--all`

## Demo status

| Test | Status | Notes |
|------|--------|-------|
| Brynäs (yellow) | ✓ | Reference example baked into PSD |
| Malmö (red) | ✓ | Color swap + photo + highlight ring verified |
| Luleå (red, after AVIF→JPG conversion) | ✓ | Format conversion needed; JPG/PNG only |
| HV71 (yellow) | ✓ | Photo bleed-through visible |
| Other 10 clubs | Pending | Need photos uploaded to Clubs/{id}/ |

## Dependencies

`pip install psd-tools aggdraw Pillow numpy`

The Anton font (Google Fonts, free) is bundled in `fonts/`.
