# Heja Team Logo Pipeline — apiai.me Setup Instructions

Steg-för-steg instruktion för att sätta upp pipelinen på apiai.me.

---

## Pipeline Overview

Pipelinen har **två flöden** baserat på kvalitet:

- **Låg kvalitet:** GPT2 → Color Correction → Upscale → Crop [END]
- **Hög kvalitet:** Transparency check → ev. Remove Solid BG → Upscale → Crop

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LÅG KVALITET FLÖDE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. Detect    2. Check      3. GPT2    4. Correct   5. Check   6. Upscale  │
│     & Crop  ──▶  Quality  ──▶        ──▶  Colors  ──▶  Res   ──▶   4x     │
│                    │                                    │                   │
│                    │ has_high_quality=false             │ skip if high      │
│                    ▼                                    ▼                   │
│                                                                             │
│                                               7. Transparent Crop [END]     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           HÖG KVALITET FLÖDE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  2. Check Quality                                                           │
│        │                                                                    │
│        │ has_high_quality=true (skip 5 noder till nod 8)                    │
│        ▼                                                                    │
│  8. Check         9. Remove        10. Check    11. Upscale                │
│     Transparency ──▶ Solid BG    ──▶   Res    ──▶    4x                    │
│        │               │               │                                    │
│        │ skip if       │               │ skip if high                       │
│        │ transparent   │               ▼                                    │
│        ▼               ▼        12. Check    13. Upscale                   │
│                                    Res     ──▶    2x                       │
│                                     │                                       │
│                                     │ skip if high                          │
│                                     ▼                                       │
│                              14. Transparent Crop                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Node-by-Node Setup

### 1. Detect and Crop

**Script:** `detect_and_crop.py`
**Purpose:** Hitta och croppa loggan från bakgrunden

| Parameter | Value |
|-----------|-------|
| `query` | `"complete logo with text and all design elements, full emblem"` |
| `min_padding` | `5` |
| `model` | `"florence-2"` |

---

### 2. Check Quality

**Script:** `check_quality.py`
**Purpose:** Avgör om bilden behöver AI-enhancement

| Parameter | Value |
|-----------|-------|
| `mp_high_threshold` | `1.0` |
| `mp_low_threshold` | `0.09` |
| `flatness_threshold` | `80` |
| `gradient_threshold` | `50` |

**Output field:** `has_high_quality`
- `true` = hög kvalitet → skip till nod 8 (5 skips)
- `false` = låg kvalitet → fortsätt till GPT2

**Skip config:**
- Field: `has_high_quality`
- Value: `true`
- Skip: `5` (till nod 8)

---

### 3. GPT Image 2

**Server:** OpenAI (direkt, inte via apiai.me script)
**Purpose:** Ta bort bakgrund och förbättra loggan

| Parameter | Value |
|-----------|-------|
| `model` | `gpt-image-2` |
| `background` | `transparent` |
| `output_format` | `png` |
| `quality` | `medium` |
| `size` | `auto` |

**Prompt:**
```
Remove background outside the team emblem. Important keep the logo identical with shape and colours. The colours must match the original exactly.
```

---

### 4. Correct Colors

**Script:** `correct_colors.py`
**Purpose:** Korrigera färgdrift från GPT-2

| Parameter | Value |
|-----------|-------|
| `image_reference` | **From step 1** (originalbilden efter crop) |
| `min_coverage` | `5` |
| `min_delta_e` | `10` |
| `n_clusters` | `12` |

> **VIKTIGT:** `image_reference` måste peka på output från **steg 1**, inte föregående steg!

---

### 5. Check Resolution (GPT2 flow)

**Script:** `check_resolution.py`
**Purpose:** Kolla om GPT2-output når tillräcklig upplösning

| Parameter | Value |
|-----------|-------|
| `min_pixels` | `5000000` |
| `field` | `is_high_resolution` |

**Skip config:**
- Field: `is_high_resolution`
- Value: `true`
- Skip: `1` (till nod 7)

---

### 6. Upscale 4x (GPT2 flow)

**Server:** Replicate (Real-ESRGAN)
**Purpose:** Skala upp GPT2-output

| Parameter | Value |
|-----------|-------|
| `scale` | `4` |
| `face_enhance` | `false` |

---

### 7. Transparent Crop (GPT2 flow) [END PIPELINE]

**Script:** `crop_transparent.py`
**Purpose:** Slutlig croppning för GPT2-flödet

| Parameter | Value |
|-----------|-------|
| `format` | `1:1` |
| `margin` | `10` |
| `alpha_threshold` | `10` |

**Pipeline setting:** `end_pipeline: true`

> Bilder som når denna nod avslutar här — de fortsätter INTE till nod 8+.

---

### 8. Check Transparency

**Script:** `check_transparency.py`
**Purpose:** Kolla om bilden redan har transparent bakgrund

| Parameter | Value |
|-----------|-------|
| `sample_percent` | `5` |
| `threshold` | `250` |
| `field` | `is_transparent` |

**Skip config:**
- Field: `is_transparent`
- Value: `true`
- Skip: `1` (hoppa över Remove Solid Background)

---

### 9. Remove Solid Background

**Script:** `remove_solid_background.py`
**Purpose:** Ta bort enfärgad bakgrund (för loggor som USA med solid fill)

| Parameter | Value |
|-----------|-------|
| `bg_color` | `auto` |
| `tolerance` | `20` |
| `feather` | `1` |

> **OBS:** Körs endast om `is_transparent=false`. Om loggan har olika färger i hörnen (inte solid) går den igenom utan ändring — det är korrekt beteende.

---

### 10. Check Resolution (High quality flow, första)

**Script:** `check_resolution.py`
**Purpose:** Kolla om bilden når 5 MP

| Parameter | Value |
|-----------|-------|
| `min_pixels` | `5000000` |
| `field` | `is_high_resolution` |

**Skip config:**
- Field: `is_high_resolution`
- Value: `true`
- Skip: `3` (till nod 14)

---

### 11. Upscale 4x (High quality flow)

**Server:** Replicate (Real-ESRGAN)
**Purpose:** Första uppskalningen

| Parameter | Value |
|-----------|-------|
| `scale` | `4` |
| `face_enhance` | `false` |

---

### 12. Check Resolution (High quality flow, andra)

**Script:** `check_resolution.py`
**Purpose:** Kolla om 4x räckte

| Parameter | Value |
|-----------|-------|
| `min_pixels` | `5000000` |
| `field` | `is_high_resolution` |

**Skip config:**
- Field: `is_high_resolution`
- Value: `true`
- Skip: `1` (till nod 14)

---

### 13. Upscale 2x (High quality flow)

**Server:** Replicate (Real-ESRGAN)
**Purpose:** Andra uppskalningen om 4x inte räckte

| Parameter | Value |
|-----------|-------|
| `scale` | `2` |
| `face_enhance` | `false` |

---

### 14. Transparent Crop (High quality flow)

**Script:** `crop_transparent.py`
**Purpose:** Slutlig croppning för high quality-flödet

| Parameter | Value |
|-----------|-------|
| `format` | `1:1` |
| `margin` | `10` |
| `alpha_threshold` | `10` |

---

## Skip Logic Summary

| Nod | Field | Value | Skip | Destination |
|-----|-------|-------|------|-------------|
| 2 | `has_high_quality` | `true` | 5 | Nod 8 |
| 5 | `is_high_resolution` | `true` | 1 | Nod 7 |
| 7 | — | — | END | Pipeline slutar |
| 8 | `is_transparent` | `true` | 1 | Nod 10 |
| 10 | `is_high_resolution` | `true` | 3 | Nod 14 |
| 12 | `is_high_resolution` | `true` | 1 | Nod 14 |

---

## Scripts Required

### Scripts att ladda upp

| Script | Fil | Purpose |
|--------|-----|---------|
| detect_and_crop | `scripts/detect_and_crop.py` | Hitta och croppa logga |
| check_quality | `scripts/check_quality.py` | Kvalitetsrouting |
| correct_colors | `scripts/correct_colors.py` | Färgkorrigering efter GPT2 |
| check_transparency | `scripts/check_transparency.py` | Kolla transparens |
| check_resolution | `scripts/check_resolution.py` | Kolla upplösning |
| remove_solid_background | `scripts/remove_solid_background.py` | Ta bort solid bakgrund |
| crop_transparent | `scripts/crop_transparent.py` | Slutlig crop |

### API Descriptions

**check_quality:**
> Analyzes image quality and outputs boolean flags for pipeline routing. Checks resolution (megapixels), color flatness, and edge gradients. Use this to decide if an image needs AI enhancement or can skip processing.

**correct_colors:**
> Corrects color drift between a generated image and a reference. Compares dominant colors using ΔE in CIELAB color space and replaces colors that have drifted beyond a threshold. Use this after AI image generation to restore original colors.

---

## External APIs

| Service | Noder | Usage |
|---------|-------|-------|
| OpenAI GPT Image 2 | 3 | Bakgrundsborttagning + enhancement |
| Replicate Real-ESRGAN | 6, 11, 13 | Uppskalning |

---

## Test Checklist

1. [ ] Ladda upp alla scripts
2. [ ] Skapa APIs för varje script
3. [ ] Sätt upp pipeline med 14 noder
4. [ ] Konfigurera skip-logik enligt tabell
5. [ ] Sätt `end_pipeline: true` på nod 7
6. [ ] **Test: Hög kvalitet + transparent** — ska skippa till nod 8, skippa nod 9, upscale vid behov
7. [ ] **Test: Hög kvalitet + solid background** — ska skippa till nod 8, köra nod 9
8. [ ] **Test: Låg kvalitet** — ska köra GPT2 → Color Correction → Upscale → END vid nod 7
9. [ ] Kör hela eval set (10 loggor)
