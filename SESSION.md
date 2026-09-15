# Session Memory — apiai

Senast uppdaterad: 2026-09-15

## Aktuellt fokus

**Fix av correct_colors.py efter apiai.me review**

- `correct_colors.py` — fixad efter att apiai.me-review bröt Knivsta-loggan
- Alla 5 testloggor passerar igen (5/5 PASS)
- **Nästa:** Committa fix, ladda upp till apiai.me

## Senaste sessionen (2026-09-15)

### Vad som hände

1. **Script fungerade lokalt** (2026-09-14)
2. **Laddades upp till apiai.me** → Claude-in-apiai.me granskade
3. **Review-ändringar pajade scriptet** — speciellt Knivsta-loggan
4. **Identifierade problemet** — jämförde commit `42df044` (fungerade) med `e0311b7` (trasig)

### Problemet (apiai.me review ändrade fel)

| Ändring | Före (fungerade) | Efter (trasig) |
|---------|------------------|----------------|
| BW_GRAYSCALE_TOLERANCE | 30 | 20 |
| MAX_CLUSTER_DIM | — | 200 (ny, för liten) |
| K-means | sklearn (n_init=10) | scipy kmeans2 (instabil) |

### Fixen (ocommittade ändringar)

```python
BW_GRAYSCALE_TOLERANCE = 30       # Återställd
MAX_CLUSTER_DIM = 400             # Ökad för bättre färgdetektering
KMEANS_N_INIT = 5                 # Ny: kör 5x, välj bästa
NEAR_WHITE_THRESHOLD = 220        # Ny: exkludera highlights
```

### Testresultat (5/5 PASS)

| Logga | Byten | Status |
|-------|-------|--------|
| Cantagalo | 2 (guld) | ✅ PASS |
| Chicago Blues | 2 (blå, röd) | ✅ PASS |
| leopards | 2 (orange, gul) | ✅ PASS |
| **special_knivstais** | 1 (guld) | ✅ PASS |
| team_usa | 1 (röd) | ✅ PASS |

Rapport: `out/color_correction_test.html`

---

## Session (2026-09-14)

### Vad vi gjorde

1. **Skapade apiai.me node** — `scripts/correct_colors.py`
   - Tar emot genererad bild (body) + original (image_reference param)
   - Parametrar: min_coverage (5%), min_delta_e (10), n_clusters (12)
   - Testad lokalt på Cantagalo, Chicago, leopards — alla fungerar

2. **Byggde color correction** — automatisk färgkorrigering för GPT-2 loggor
   - Prototyp: `scratch/run_color_correction_eval.py`
   - HTML-rapport: `out/color_correction_steps.html`

3. **Analysverktyg** — detaljerad färganalys per logga
   - Script: `scratch/color_analysis_table.py`
   - Output: `scratch/color_analysis_output.txt`

4. **Testade på 5 GPT-2 loggor** — alla fungerar efter fix

### Metoden

```
1. Extrahera färger från genererad bild (12 kluster, exkludera svart/vit)
2. För varje färg >5% med ΔE >10 från original → byt färg
3. Smart tolerans (ΔE/2) → undviker att byta liknande-men-olika färger
```

### Resultat

| Logga | Byten | Resultat |
|-------|-------|----------|
| Cantagalo | 1 (guld) | ✅ Bra |
| Chicago Blues | 2 (blå, röd) | ✅ Bra (efter fix för två blå nyanser) |
| leopards | 2 (orange, gul) | ✅ Bra |
| special_knivstais | 1 (guld) | ✅ Bra |
| team_usa | 1 (röd) | ✅ Bra |

### Lärdomar

- **Svart/vit driftar aldrig** → exkluderas från analys
- **Röda färger driftar mest** → blir fluorescerande
- **Guld/orange plattas** → nyanser slås ihop
- **Smart tolerans krävs** → Chicago hade två blå, naiv metod bytte fel

### Risker

- **Låg risk** för enkla loggor (2-4 distinkta färger)
- **Medel risk** för loggor med flera nyanser av samma färg
- **Användaren godkänner alltid** → säkerhetsnät

## Nästa steg

1. ~~Verifiera HTML-rapporten visuellt~~ ✅
2. ~~Committa fixen~~ ✅ `d6d8b46`
3. ~~Ladda upp till apiai.me~~ ✅
4. ~~Testa live på apiai.me~~ ✅ 5/5 PASS

**Klart!** Scriptet fungerar. Nästa: använd i pipeline.

## Scratch-filer

```
customers/heja/pipeline/scratch/
├── test_apiai_all_logos.py       # Testar alla 5 mot apiai.me API
├── test_apiai_correct_colors.py  # Testar en logga mot apiai.me API
├── test_fixed_correct_colors.py  # Testar lokalt mot scripts/correct_colors.py
├── color_analysis_table.py       # Färganalys per logga
├── run_color_correction_eval.py  # Kör korrigering + HTML-rapport (egen kopia)
└── (äldre testfiler...)
```

## ΔE-tolkning (för referens)

- 0-5: OK (knappt synbart)
- 5-10: Drift (synbart vid jämförelse)
- 10-15: Tydlig drift (bör korrigeras)
- 15+: Allvarligt (måste korrigeras)
