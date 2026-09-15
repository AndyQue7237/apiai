# Session Memory — apiai

Senast uppdaterad: 2026-09-15

## Aktuellt fokus

**Pipeline redo för apiai.me setup**

- `correct_colors.py` — klar och testad
- `APIAI_SETUP.md` — komplett instruktion för att sätta upp pipelinen
- 5 MP minimum resolution med dubbel upscale (4x + 2x vid behov)

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

1. **Ladda upp scripts till apiai.me** — se `APIAI_SETUP.md` för lista
2. **Sätt upp pipeline** — följ `APIAI_SETUP.md` steg-för-steg
3. **Testa med eval set** — 10 loggor, verifiera 5 MP output
4. **Heja testar i produktion**

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
