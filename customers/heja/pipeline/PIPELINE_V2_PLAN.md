# Heja Pipeline v2 — Smart Routing

**Datum:** 2026-09-04
**Status:** Plan (väntar på godkännande)

## Mål

Uppdatera pipelinen med intelligent routing baserat på:
1. **Kvalitet** (MP + hårda kanter) → avgör om GPT2 behövs
2. **Transparens** → avgör om bg removal behövs
3. **Bakgrundsfärg** → avgör script vs GPT2 för bg removal

## Nya noder att bygga

| Nod | Input | Output | Syfte |
|-----|-------|--------|-------|
| `check_quality` | Bild | `needs_gpt2: bool` | MP + hårda kanter → routing |
| `has_solid_background` | Bild | `is_solid: bool`, `bg_color: RGB` | Hörn-färger → routing |

**Befintliga noder (oförändrade):**
- `detect_and_crop` — beskär till logga
- `check_transparency` — redan transparent?
- `check_resolution` — behöver upscale?
- `real-esrgan` — upscaler
- `crop_transparent` — final crop

## Pipeline-flöde

```
┌─────────────────┐
│ 1. Detect/Crop  │
└────────┬────────┘
         ▼
┌─────────────────┐
│ 2. check_quality│ ──► needs_gpt2: true/false
└────────┬────────┘
         ▼
┌─────────────────┐
│ 3. is_transparent│ ──► is_transparent: true/false
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
 [transparent] [not transparent]
    │              │
    │         ┌────┴────┐
    │         ▼         ▼
    │    [needs_gpt2]  [good quality]
    │         │              │
    │         ▼              ▼
    │    ┌─────────┐   ┌──────────────────┐
    │    │ 4. GPT2 │   │ 5. has_solid_bg  │
    │    │(+bg rem)│   └────────┬─────────┘
    │    └────┬────┘       ┌────┴────┐
    │         │            ▼         ▼
    │         │       [solid]    [multi-color]
    │         │            │         │
    │         │            ▼         ▼
    │         │     ┌──────────┐  [edge case]
    │         │     │ 6. Script│  [skip/warn]
    │         │     │ bg_remove│
    │         │     └────┬─────┘
    │         │          │
    └─────────┴──────────┴──────────┐
                                    ▼
                          ┌─────────────────┐
                          │ 7. check_res    │
                          └────────┬────────┘
                                   │
                              ┌────┴────┐
                              ▼         ▼
                         [high_res]  [low_res]
                              │         │
                              │         ▼
                              │   ┌──────────┐
                              │   │ 8. ESRGAN│
                              │   └────┬─────┘
                              │        │
                              └────────┴───────┐
                                               ▼
                                    ┌─────────────────┐
                                    │ 9. final_crop   │
                                    └─────────────────┘
```

## Nod-specifikationer

### `check_quality.py` (NY)

```python
# Input: bild (efter detect_and_crop)
# Output: needs_gpt2 (bool), mp (float), hard_edges_pct (float)

# Logik:
# 1. Beräkna MP = (width * height) / 1_000_000
# 2. Beräkna hårda kanter % (Sobel edge detection → threshold)
# 3. Routing:
#    - MP > 1.0 → needs_gpt2 = False
#    - MP < 0.09 → needs_gpt2 = True
#    - MP 0.09-1.0 AND hard_edges > 20% → needs_gpt2 = True
#    - else → needs_gpt2 = False
```

### `has_solid_background.py` (NY)

```python
# Input: bild (icke-transparent)
# Output: is_solid (bool), bg_color (RGB), corner_distance (float)

# Logik:
# 1. Sampla 10x10 px från varje hörn
# 2. Beräkna RGB-medel per hörn
# 3. Beräkna max distance mellan hörn-färger
# 4. is_solid = (distance < 50)
# 5. bg_color = medel av alla hörn (om solid)
```

### `remove_solid_background.py` (NY eller befintlig)

```python
# Input: bild + bg_color
# Output: bild med transparent bakgrund

# Logik:
# 1. Flood-fill från hörn med bg_color (tolerance ~15-30)
# 2. Skapa alpha-kanal där flood-fill träffade
# 3. Return RGBA
```

## Filer att skapa/ändra

**Nya scripts:**
- `apiai-tools/scripts/check_quality.py`
- `apiai-tools/scripts/has_solid_background.py`
- `apiai-tools/scripts/remove_solid_background.py` (om inte befintlig räcker)

**Ändra:**
- `pipelines/heja-team-logo/run_pipeline.py` — ny routing-logik

## Evaluation Strategy

1. Kör på hela eval-setet (10 loggor)
2. Verifiera routing-beslut matchar förväntad tabell
3. Verifiera output-kvalitet visuellt
4. Jämför med nuvarande pipeline (kostnad, latens, kvalitet)

**Förväntade routing-beslut:**

| Logo | needs_gpt2 | is_transparent | is_solid | Path |
|------|------------|----------------|----------|------|
| Kumla | False | True | — | Skip→Upscale |
| Hammarby | False | True | — | Skip→Upscale |
| Tyresö | False | True | — | Skip→Upscale |
| Trollbäckens | False | False | True | Script→Upscale |
| Warner | False | False | True | Script→Upscale |
| team_usa | False | False | False | Edge case |
| Chicago Blues | True | False | — | GPT2→Upscale |
| leopards | True | False | — | GPT2→Upscale |
| special_knivstais | True | False | — | GPT2→Upscale |
| Cantagalo | ??? | ??? | ??? | ??? |

## Definition of Done

1. ✅ Alla 10 loggor routas korrekt enligt tabell
2. ✅ Output-kvalitet minst lika bra som nuvarande pipeline
3. ✅ Kostnadsreduktion för loggor som skippar GPT2
4. ✅ Noder fungerar lokalt via stdin/stdout-kontrakt
5. ✅ Dokumentation uppdaterad

## Approach

1. **Lokal implementation** — bygg noder + uppdatera `run_pipeline.py`
2. **Kör eval** — testa på hela setet, verifiera routing
3. **Iterera** — justera tröskelvärden om nödvändigt
4. **Andreas implementerar på apiai.me** — nya scripts + uppdaterad pipeline

---

**Väntar på godkännande innan Build-fas.**
