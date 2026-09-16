# Session Memory — apiai

Senast uppdaterad: 2026-09-15

## Aktuellt fokus

**remove_solid_background — beslut väntar**

Två versioner:
1. **Vår lokala** (`scripts/remove_solid_background.py`) — enkel flood-fill från kanter
2. **apiai.me version** — har `detections` (Grounding DINO) + `remove_holes_threshold`

### Problemet

| Logo | Vår lokala | apiai.me (holes=2) | apiai.me (holes=0) |
|------|-----------|-------------------|-------------------|
| Warner | ✅ Vit cirkel bevarad | ❌ Vit borttagen | ✅ Fixat |
| Trollbäcken | ❌ Hål i små bokstäver | ✅ Hål fyllda | ❌ Vita fläckar |

### Beslut att fatta

- `remove_holes_threshold` fyller hål i samma färg — användbart för text
- `detections` använder Grounding DINO — men DINO är nere på Replicate
- Tanken: detektor skyddar objekt (ex "logo"), men text kan uppfattas som logo → skyddar fel

**Alternativ:**
1. Ladda upp vårt enklare script (utan holes/detections)
2. Behåll apiai.me version, hitta rätt threshold
3. Förbättra vårt script med holes-funktionalitet (utan DINO)

---

## correct_colors.py — KLAR

- `auto_crop_reference=true` som default
- Croppar referensbilden internt via Florence-2
- Testat lokalt: fungerar på leopards
- Commit: `44d413a`
- **Nästa:** Ladda upp till apiai.me

---

## Sessionen (2026-09-15)

### Vad vi gjorde

1. **detect_and_crop fix** — `min_padding=5` (inte 50)
2. **correct_colors.py** — la till `auto_crop_reference` + `crop_query`
3. **remove_solid_background** — upptäckte skillnad mellan lokal/apiai.me version

### Dokumentation uppdaterad

- `APIAI_SETUP.md` — nya params för correct_colors + remove_solid_background
- `WINNER.md` — uppdaterade parametrar

### Commits

- `44d413a` Add auto_crop_reference to correct_colors.py

---

## Nästa session

1. Besluta om remove_solid_background (ladda upp vår eller justera apiai.me)
2. Ladda upp correct_colors.py till apiai.me
3. Testa hela pipelinen på apiai.me

---

## Scratch-filer

```
customers/heja/pipeline/scratch/
├── test_apiai_all_logos.py       # Testar alla 5 mot apiai.me API
├── test_apiai_correct_colors.py  # Testar en logga mot apiai.me API
└── (äldre testfiler...)
```

## Lokala testbilder

```
customers/heja/pipeline/out/
├── Warner-v2-gradient-4b-removebg.png      # Warner lokal — vit bevarad ✅
├── Warner-v2-gradient-7-final.png
├── Trollbäckens GK-v2-gradient-4b-removebg.png  # Trollbäcken lokal — hål i text
├── Trollbäckens GK-v2-gradient-7-final.png
└── leopards_autocrop_test.png              # Color correction test ✅
```
