# Heja Team Logo Pipeline — apiai.me Setup Instructions

Steg-för-steg instruktion för att sätta upp pipelinen på apiai.me.

---

## Pipeline Overview

Pipelinen har **två flöden** baserat på kvalitet och **19 noder** (inklusive condition-noder):

- **Låg kvalitet (nod 1-9):** GPT2 → Color Correction → Upscale → Crop [END]
- **Hög kvalitet (nod 10-19):** Transparency check → ev. Remove Solid BG → Upscale → Crop

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           LÅG KVALITET FLÖDE (nod 1-9)                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  1. Detect    2. Check    3. Cond    4. GPT2    5. Correct   6. Check   7. Cond│
│     & Crop ──▶ Quality ──▶ skip 6 ──▶        ──▶  Colors  ──▶  Res   ──▶ skip 1│
│                              │                                             │    │
│                              │ if high_quality=true                        │    │
│                              ▼ (till nod 10)                               ▼    │
│                                                                                 │
│                                           8. Upscale 4x ──▶ 9. Crop [END]      │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                           HÖG KVALITET FLÖDE (nod 10-19)                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  10. Check      11. Cond    12. Remove     13. Check    14. Cond               │
│      Transp  ──▶  skip 1  ──▶  Solid BG  ──▶   Res   ──▶  skip 4              │
│                     │                                       │                   │
│                     │ if transparent=true                   │ if high_res=true  │
│                     ▼ (till nod 13)                         ▼ (till nod 19)     │
│                                                                                 │
│  15. Upscale 4x ──▶ 16. Check Res ──▶ 17. Cond ──▶ 18. Upscale 2x ──▶ 19. Crop │
│                                          │                                      │
│                                          │ if high_res=true                     │
│                                          ▼ (till nod 19)                        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Node-by-Node Setup (19 noder)

### 1. Detect and Crop

**Script:** `detect_and_crop.py`
**Purpose:** Hitta och croppa loggan från bakgrunden (använder Florence-2 via Replicate)

| Parameter | Value |
|-----------|-------|
| `query` | `"complete logo with text, full team logo with text, entire emblem, club logo"` |
| `min_padding` | `5` |

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

---

### 3. Condition (Quality routing)

**Type:** Condition
**Purpose:** Hoppa över GPT2-flödet om bilden redan har hög kvalitet

| Parameter | Value |
|-----------|-------|
| Skip next | `6` |
| When field | `has_high_quality` |
| Is value | `true` |

> Hoppar till nod 10 (Check Transparency)

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

---

### 5. Correct Colors

**Script:** `correct_colors.py`
**Purpose:** Korrigera färgdrift från GPT-2 + lägg till border vid vita kanter

| Parameter | Value |
|-----------|-------|
| `image_reference` | **From Original** (originalbilden) |
| `min_coverage` | `5` |
| `min_delta_e` | `10` |
| `n_clusters` | `12` |
| `cluster_merge_threshold` | `8` |
| `auto_crop_reference` | `true` |
| `crop_query` | `"complete logo with text, full team logo with text, entire emblem, club logo"` |
| `add_edge_border` | `true` |
| `border_width` | `10` |
| `border_color` | `auto` |
| `white_edge_threshold` | `240` |
| `white_edge_percent` | `20` |

> Med `auto_crop_reference=true` kan originalfilen användas direkt — scriptet croppar internt via Florence-2.
>
> Med `add_edge_border=true` läggs en mörk border till om >20% av objektets kant är vit (t.ex. Leopards). Färgen väljs automatiskt (mörkaste med >5% coverage).

---

### 6. Check Resolution

**Script:** `check_resolution.py`
**Purpose:** Kolla om GPT2-output når tillräcklig upplösning

| Parameter | Value |
|-----------|-------|
| `min_pixels` | `5000000` |

**Output field:** `is_high_resolution`

---

### 7. Condition (Resolution skip)

**Type:** Condition
**Purpose:** Hoppa över Upscale om redan hög upplösning

| Parameter | Value |
|-----------|-------|
| Skip next | `1` |
| When field | `is_high_resolution` |
| Is value | `true` |

> Hoppar till nod 9 (Transparent Crop)

---

### 8. Upscale 4x

**Server:** Replicate (Real-ESRGAN)
**Purpose:** Skala upp GPT2-output

| Parameter | Value |
|-----------|-------|
| `scale` | `4` |
| `face_enhance` | `false` |

---

### 9. Transparent Crop [END PIPELINE]

**Script:** `crop_transparent.py`
**Purpose:** Slutlig croppning för GPT2-flödet

| Parameter | Value |
|-----------|-------|
| `format` | `1:1` |
| `margin` | `10` |
| `alpha_threshold` | `10` |

**Pipeline setting:** `end_pipeline: true`

> Bilder som når denna nod avslutar här — de fortsätter INTE till nod 10+.

---

### 10. Check Transparency

**Script:** `check_transparency.py`
**Purpose:** Kolla om bilden redan har transparent bakgrund

| Parameter | Value |
|-----------|-------|
| `sample_percent` | `5` |
| `threshold` | `250` |

**Output field:** `has_transparency`

---

### 11. Condition (Transparency skip)

**Type:** Condition
**Purpose:** Hoppa över Remove Solid Background om redan transparent

| Parameter | Value |
|-----------|-------|
| Skip next | `1` |
| When field | `has_transparency` |
| Is value | `true` |

> Hoppar till nod 13 (Check Resolution)

---

### 12. Remove Solid Background

**Script:** `remove_solid_background.py`
**Purpose:** Ta bort enfärgad bakgrund (för loggor som USA med solid fill)

| Parameter | Value |
|-----------|-------|
| `bg_color` | `auto` |
| `tolerance` | `20` |
| `feather` | `1` |
| `remove_holes_threshold` | `0` |
| `passthrough_on_mismatch` | `true` |

> Körs endast om `has_transparency=false`.
> Med `passthrough_on_mismatch=true` skickas bilden vidare oförändrad om hörnen har olika färger (t.ex. team_usa med gradient).

---

### 13. Check Resolution

**Script:** `check_resolution.py`
**Purpose:** Kolla om bilden når 5 MP

| Parameter | Value |
|-----------|-------|
| `min_pixels` | `5000000` |

**Output field:** `is_high_resolution`

---

### 14. Condition (Resolution skip to final)

**Type:** Condition
**Purpose:** Hoppa direkt till final crop om redan hög upplösning

| Parameter | Value |
|-----------|-------|
| Skip next | `4` |
| When field | `is_high_resolution` |
| Is value | `true` |

> Hoppar till nod 19 (Transparent Crop)

---

### 15. Upscale 4x

**Server:** Replicate (Real-ESRGAN)
**Purpose:** Första uppskalningen

| Parameter | Value |
|-----------|-------|
| `scale` | `4` |
| `face_enhance` | `false` |

---

### 16. Check Resolution

**Script:** `check_resolution.py`
**Purpose:** Kolla om 4x räckte

| Parameter | Value |
|-----------|-------|
| `min_pixels` | `5000000` |

**Output field:** `is_high_resolution`

---

### 17. Condition (Resolution skip 2x)

**Type:** Condition
**Purpose:** Hoppa över 2x upscale om 4x räckte

| Parameter | Value |
|-----------|-------|
| Skip next | `1` |
| When field | `is_high_resolution` |
| Is value | `true` |

> Hoppar till nod 19 (Transparent Crop)

---

### 18. Upscale 2x

**Server:** Replicate (Real-ESRGAN)
**Purpose:** Andra uppskalningen om 4x inte räckte

| Parameter | Value |
|-----------|-------|
| `scale` | `2` |
| `face_enhance` | `false` |

---

### 19. Transparent Crop

**Script:** `crop_transparent.py`
**Purpose:** Slutlig croppning för high quality-flödet

| Parameter | Value |
|-----------|-------|
| `format` | `1:1` |
| `margin` | `10` |
| `alpha_threshold` | `10` |

---

## Condition Summary

| Nod | Skip | When field | Is value | Destination |
|-----|------|------------|----------|-------------|
| 3 | 6 | `has_high_quality` | `true` | Nod 10 |
| 7 | 1 | `is_high_resolution` | `true` | Nod 9 |
| 9 | — | — | — | END PIPELINE |
| 11 | 1 | `has_transparency` | `true` | Nod 13 |
| 14 | 4 | `is_high_resolution` | `true` | Nod 19 |
| 17 | 1 | `is_high_resolution` | `true` | Nod 19 |

---

## Scripts Required

| Script | Fil | Används i nod |
|--------|-----|---------------|
| detect_and_crop | `scripts/detect_and_crop.py` | 1 |
| check_quality | `scripts/check_quality.py` | 2 |
| correct_colors | `scripts/correct_colors.py` | 5 |
| check_resolution | `scripts/check_resolution.py` | 6, 13, 16 |
| crop_transparent | `scripts/crop_transparent.py` | 9, 19 |
| check_transparency | `scripts/check_transparency.py` | 10 |
| remove_solid_background | `scripts/remove_solid_background.py` | 12 |
| downscale_image | `scripts/downscale_image.py` | före 8, 15, 18 |

---

## External APIs

| Service | Noder | Usage |
|---------|-------|-------|
| OpenAI GPT Image 2 | 4 | Bakgrundsborttagning + enhancement |
| Replicate Florence-2 | 1, 5 | Logo-detektion, auto-crop av referensbild |
| Replicate Real-ESRGAN | 8, 15, 18 | Uppskalning (max ~2.1MP input) |

> **OBS:** Real-ESRGAN har GPU-gräns på ~2.1MP. Använd `downscale_image.py` med `max_pixels=2000000`
> före upscaler-noder för att resiza ner bilder som är för stora.
>
> `downscale_image.py` stödjer också `max_bytes` för filstorlek (webb-optimering).

---

## Test Checklist

1. [ ] Ladda upp alla scripts
2. [ ] Skapa APIs för varje script
3. [ ] Sätt upp pipeline med **19 noder** (inkl. 5 condition-noder)
4. [ ] Konfigurera conditions enligt tabell
5. [ ] Sätt `end_pipeline: true` på nod 9
6. [ ] **Test: Hög kvalitet + transparent** — ska hoppa 3→10→11→13, upscale vid behov
7. [ ] **Test: Hög kvalitet + solid background** — ska hoppa 3→10, köra 12, upscale vid behov
8. [ ] **Test: Låg kvalitet** — ska köra 4→5→6→7→8→9 [END]
9. [ ] Kör hela eval set (10 loggor)
