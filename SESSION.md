# Session Memory — apiai

Senast uppdaterad: 2026-09-18

## Aktuellt fokus

**Chicago color fix verifierad + CUDA OOM-mönster bekräftat**

Pipeline eval 8/10 pass:
- Chicago: Fix verifierad (himmel behåller rätt färg)
- Hammarby/Tyresö: CUDA OOM (loggor <0.15 MP, dubbel upscale)

Fix implementerad i apiai.me (nod 20 → 1.25 MP), väntar på serverkapacitet för test.

---

## Sessionen (2026-09-18)

### Vad vi gjorde

1. **Chicago himmel-fix** — correct_colors.py tar nu bort solid bakgrund från referensbilden innan färgextraktion. Fixar att vita bakgrunder triggade highlight-filter som exkluderade ljusgrå färger.

2. **CUDA OOM bekräftat** — Två loggor under 0.15 MP (Hammarby 0.10, Tyresö 0.15) failar konsekvent. Orsak: dubbel upscale (4x → 2x) utan downscale mellan. Fix: sänk nod 20 till 1.25 MP.

3. **Script cleanup** — Raderade gamla DINO-scripts:
   - `detect_and_remove_bg.py` (DINO funkar inte på Replicate)
   - `remove_bg.py` (gammal version)

4. **WINNER.md uppdaterad** — Chicago fix dokumenterad, CUDA OOM-mönster bekräftat.

### Pipeline eval resultat

| Logo | Status | Output |
|------|--------|--------|
| Cantagalo | OK | 4648×4648 |
| Chicago | OK | 4912×4912 |
| Hammarby | GPU OOM | — |
| Kumla | OK | 5606×5606 |
| leopards | OK | 4651×4651 |
| Knivsta | OK | 4824×4824 |
| team_usa | OK | 2958×2958 |
| Trollbäckens | OK | 2390×2390 |
| Tyresö | GPU OOM | — |
| Warner | OK | 3910×3910 |

### Commits

- `174ac6b` Fix Chicago sky color + cleanup unused bg scripts

---

## Nästa session

1. **Verifiera GPU-fix** — Kör Hammarby + Tyresö när apiai.me har kapacitet
2. **Backlog** — Överväg 1% filter på referensfärger om fler färgproblem uppstår

---

## Key learnings (denna session)

1. **Solid bg påverkar färgextraktion** — Vita bakgrunder i referensbilder kan trigga highlight-filter och exkludera legitima ljusa färger.

2. **CUDA OOM-mönster** — Loggor <0.15 MP → dubbel upscale → GPU OOM. Fix: tvinga downscale mellan 4x och 2x.

3. **Färgkorrigering flöde:**
   - Ta bort solid bg från referens
   - Extrahera färger
   - Matcha genererad → referens
   - Byt pixlar med ΔE/2 tolerans

---

## Scratch-filer

```
customers/heja/pipeline/scratch/
├── eval_pipeline.py              # Pipeline eval script (uppdaterad med delay)
├── trace_gpt2_clusters.py        # Debug: GPT2 färgklustring
└── trace_merge.py                # Debug: Cluster merging
```
