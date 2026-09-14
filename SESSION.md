# Session Memory — apiai

Senast uppdaterad: 2026-09-14

## Aktuellt fokus

**Color correction — apiai.me node KLAR**

Scriptet `correct_colors.py` är skapat och testat. Redo att laddas upp till apiai.me.

## Senaste sessionen (2026-09-14)

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

1. **Ladda upp till apiai.me** — `scripts/correct_colors.py`
2. **Koppla in i pipeline** — efter GPT-2 steget, med original som reference
3. **Heja testar i produktion** — logga in, logga ut, ingen text

## Scratch-filer

```
customers/heja/pipeline/scratch/
├── color_analysis_table.py       # Färganalys per logga
├── color_analysis_output.txt     # Senaste analysresultat
├── run_color_correction_eval.py  # Kör korrigering + HTML-rapport
├── test_color_correction.py      # Första test (Cantagalo)
└── test_color_drift_gpt2.py      # Drift-analys (äldre)
```

## ΔE-tolkning (för referens)

- 0-5: OK (knappt synbart)
- 5-10: Drift (synbart vid jämförelse)
- 10-15: Tydlig drift (bör korrigeras)
- 15+: Allvarligt (måste korrigeras)
