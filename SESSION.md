# Session Memory — apiai

Senast uppdaterad: 2026-09-11

## Aktuellt fokus

**Explore: GPT-2 färgdrift och color-correction**

Undersöker om GPT-2 ändrar färger på loggor och om vi kan korrigera det automatiskt.

## Senaste sessionen (2026-09-11)

### Vad vi gjorde

1. **Skapade apiai-repot** — flyttade all apiai-kod från tools-repot hit
   - Scripts, guidelines, customers/heja|az-design|shl
   - Workflow rules (.claude/rules/)
   - Städade tools-repot

2. **Explore: Color drift-analys**
   - Hypotes: GPT-2 konverterar till RGB → färger kan shifta → fixa genom att mappa tillbaka
   - Testade på alla loggor i v2-gradient-körningen

### Resultat: Color drift (v2-gradient run)

**5 loggor genom GPT-2:**

| Logo | Max ΔE | Status | Huvudproblem |
|------|--------|--------|--------------|
| team_usa | 40.0 | ❌ BAD | Röd #960012 → #f60418 (mycket ljusare!) |
| Chicago Blues FC | 38.9 | ❌ BAD | Svart → mörkblå, röd shifted |
| Cantagalo Logo | 27.0 | ❌ BAD | Guld → mer gul, brun shifted |
| special_knivstais | 7.4 | ⚠️ DRIFT | Grå → blågrå |
| leopards | 4.5 | ✅ OK | Minimal drift |

**5 loggor transparent_skip (inget GPT-2):**
- Hammarby IF, Kumla_Hockey, Trollbäckens GK, Tyresö FF, Warner

### Slutsats från explore

- ✅ **Hypotesen bekräftad** — 4/5 GPT-2-loggor har märkbar färgdrift
- ✅ **3/5 har allvarlig drift** (ΔE > 15) — synligt fel
- ✅ **Driften är mätbar** — vi kan detektera och potentiellt korrigera
- ✅ **transparent_skip funkar** — de som inte behöver GPT-2 slipper problemet

## Nästa steg

1. **Besluta**: Ska vi bygga color-correction?
   - Option A: `check_colours` gatekeeper + `correct_colours` script
   - Option B: Acceptera driften för nu

2. **Om ja till color-correction**:
   - Skriv `check_colours.py` — avgör om logga är lämplig (platt? få färger?)
   - Skriv `correct_colours.py` — mappar driftade färger tillbaka
   - Testa på Cantagalo som proof-of-concept

## Scratch-filer (för denna explore)

```
customers/heja/pipeline/scratch/
├── test_color_drift.py          # Enkel test på Cantagalo
├── test_color_drift_all.py      # Alla loggor (med fel routing)
└── test_color_drift_gpt2.py     # Endast GPT-2-loggor (korrekt)
```

## ΔE-tolkning (för referens)

- 0-1: Ej synbart
- 1-2: Synbart vid noggrann jämförelse
- 2-10: Synbart direkt
- 11-49: Tydligt annorlunda
- 50+: Helt olika färger
