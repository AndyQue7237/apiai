# Heja Team Logo Pipeline — apiai.me Setup Instructions

Steg-för-steg instruktion för att sätta upp pipelinen på apiai.me.

---

## Pipeline Overview

```
┌─────────────┐    ┌───────────────┐    ┌───────────────────┐
│ 1. Detect   │───▶│ 2. Check      │───▶│ 3. Check          │
│    & Crop   │    │    Quality    │    │    Transparency   │
└─────────────┘    └───────────────┘    └───────────────────┘
                                                  │
                          ┌───────────────────────┴───────────────────────┐
                          │                                               │
                          ▼                                               ▼
                   has_high_quality=false                        transparent + has_high_quality
                          │                                               │
                          ▼                                               │
                 ┌─────────────────┐                                      │
                 │ 4. GPT Image 2  │                                      │
                 └─────────────────┘                                      │
                          │                                               │
                          ▼                                               │
                 ┌─────────────────┐                                      │
                 │ 5. Color        │                                      │
                 │    Correction   │                                      │
                 └─────────────────┘                                      │
                          │                                               │
                          └───────────────────────┬───────────────────────┘
                                                  │
                                                  ▼
                                         ┌───────────────┐
                                         │ 6. Check      │
                                         │    Resolution │
                                         └───────────────┘
                                                  │
                          ┌───────────────────────┴───────────────────────┐
                          │                                               │
                          ▼                                               ▼
                    < 5 MP                                           ≥ 5 MP
                          │                                               │
                          ▼                                               │
                 ┌─────────────────┐                                      │
                 │ 7. Upscale 4x   │                                      │
                 └─────────────────┘                                      │
                          │                                               │
                          ▼                                               │
                 ┌───────────────┐                                        │
                 │ 8. Check      │                                        │
                 │    Resolution │                                        │
                 └───────────────┘                                        │
                          │                                               │
                          ▼                                               │
                    < 5 MP ───▶ ┌─────────────────┐                       │
                                │ 9. Upscale 2x   │                       │
                                └─────────────────┘                       │
                                         │                                │
                                         └────────────────┬───────────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │ 10. Transparent │
                                                 │     Crop        │
                                                 └─────────────────┘
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

**Skip:** Aldrig (alltid första steget)

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

**Output field:**
- `has_high_quality` — true om kvalitet är hög, false om den behöver enhancement

**Används för routing i steg 3**

---

### 3. Check Transparency

**Script:** `check_transparency.py`
**Purpose:** Kolla om bilden redan har transparent bakgrund

| Parameter | Value |
|-----------|-------|
| `sample_percent` | `5` |
| `threshold` | `250` |

**Output fields:**
- `is_transparent` — true om redan transparent

**Routing logic:**
- Om `is_transparent=true` AND `has_high_quality=true` → **SKIP till steg 6**
- Annars → fortsätt till steg 4

---

### 4. GPT Image 2

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

**Skip condition:** `is_transparent=true` AND `has_high_quality=true`

---

### 5. Color Correction

**Script:** `correct_colors.py`
**Purpose:** Korrigera färgdrift från GPT-2

| Parameter | Value |
|-----------|-------|
| `image_reference` | **From Original** (originalbilden) |
| `min_coverage` | `5` |
| `min_delta_e` | `10` |
| `n_clusters` | `12` |

**Skip condition:** Samma som steg 4 (`is_transparent=true` AND `has_high_quality=true`)

> **Viktigt:** `image_reference` måste peka på originalbilden, inte föregående steg!

---

### 6. Check Resolution (första)

**Script:** `check_resolution.py`
**Purpose:** Kolla om bilden når 5 MP

| Parameter | Value |
|-----------|-------|
| `max_pixels` | `5000000` |
| `field` | `is_high_resolution` |

**Output:** `is_high_resolution` — true om ≥ 5 MP

---

### 7. Upscale 4x

**Server:** Replicate (Real-ESRGAN)
**Purpose:** Första uppskalningen

| Parameter | Value |
|-----------|-------|
| `scale` | `4` |
| `face_enhance` | `false` |

**Skip condition:** `is_high_resolution=true`

---

### 8. Check Resolution (andra)

**Script:** `check_resolution.py`
**Purpose:** Kolla om 4x räckte

| Parameter | Value |
|-----------|-------|
| `max_pixels` | `5000000` |
| `field` | `is_high_resolution` |

**Skip condition:** `is_high_resolution=true` (från steg 6)

---

### 9. Upscale 2x

**Server:** Replicate (Real-ESRGAN)
**Purpose:** Andra uppskalningen om 4x inte räckte

| Parameter | Value |
|-----------|-------|
| `scale` | `2` |
| `face_enhance` | `false` |

**Skip condition:** `is_high_resolution=true` (från steg 6 eller 8)

---

### 10. Transparent Crop

**Script:** `crop_transparent.py`
**Purpose:** Slutlig croppning till 1:1 med marginal

| Parameter | Value |
|-----------|-------|
| `format` | `1:1` |
| `margin` | `10` |
| `alpha_threshold` | `10` |

**Skip:** Aldrig (alltid sista steget)

---

## Skip Logic Summary

| Steg | Skip om |
|------|---------|
| 4. GPT Image 2 | `is_transparent=true` AND `has_high_quality=true` |
| 5. Color Correction | `is_transparent=true` AND `has_high_quality=true` |
| 7. Upscale 4x | `is_high_resolution=true` |
| 8. Check Resolution 2 | `is_high_resolution=true` (från steg 6) |
| 9. Upscale 2x | `is_high_resolution=true` (från steg 6 eller 8) |

---

## Scripts Required

### Nya scripts att ladda upp

| Script | Fil | Requirements |
|--------|-----|--------------|
| check_quality | `scripts/check_quality.py` | `Pillow`, `numpy` |
| correct_colors | `scripts/correct_colors.py` | `Pillow`, `numpy`, `scipy`, `scikit-image` |

**check_quality — API Description:**
> Analyzes image quality and outputs boolean flags for pipeline routing. Checks resolution (megapixels), color flatness, and edge gradients. Use this to decide if an image needs AI enhancement or can skip processing.

**correct_colors — API Description:**
> Corrects color drift between a generated image and a reference. Compares dominant colors using ΔE in CIELAB color space and replaces colors that have drifted beyond a threshold. Use this after AI image generation to restore original colors.

### Befintliga scripts på apiai.me

| Script | Requirements |
|--------|--------------|
| detect_and_crop | `Pillow`, `replicate` |
| check_transparency | `Pillow` |
| check_resolution | `Pillow` |
| crop_transparent | `Pillow` |

---

## External APIs

| Service | Usage |
|---------|-------|
| OpenAI GPT Image 2 | Steg 4 |
| Replicate Real-ESRGAN | Steg 7, 9 |

---

## Test Checklist

1. [ ] Ladda upp alla scripts
2. [ ] Skapa APIs för varje script
3. [ ] Sätt upp pipeline med routing
4. [ ] Testa med en enkel logga (redan transparent, hög kvalitet)
5. [ ] Testa med en komplex logga (behöver GPT-2 + color correction)
6. [ ] Testa med en liten logga (behöver dubbel upscale)
7. [ ] Kör hela eval set (10 loggor)
