# Session Memory — apiai

Senast uppdaterad: 2026-09-29

> **NYTT FOKUS 2026-09-29: dokumentera apiai inför en ny produkt.** Läs
> **[`docs/HANDOVER.md`](docs/HANDOVER.md)** först. Sessionen 2026-09-18 längre ner är historik.

## Aktuellt fokus (2026-09-29): apiai-dokumentation — källorna är insamlade

Enbart dokumentation (ingen Feature Brief för bygge än). Källorna är på plats och sanerade;
nästa steg är att **skriva** dokumenten.

### Vad vi gjorde (2026-09-29)

1. **Export** (`docs/export/`): admin-exporten innehöll 5 live API-nycklar i klartext
   (Replicate, Gemini, xAI, OpenAI). Råfilen är gitignorerad; bara
   `*.sanitized.json` committas (`docs/tools/sanitize_export.py`). Överväg att rotera nycklarna.
   Exporten saknar flödesparametrar (`step_config` tomma).
2. **JSON-inspelning av admin** (`docs/tools/record_admin.py`, output `docs/crawl/admin/`,
   gitignorerad): fångar all JSON admin laddar. Gav **`flow_config` med hela nodgrafen** för
   26 flöden (Heja: 22 noder, prompts, villkor, `from_node`), 87 APIs med
   `provider_cost_per_request`/`markup_pct`/`ai_context`, allowed-packages, available-env,
   capacity, monitor. Kunddata (users, admins, usage per user, login) rensad till schema.
3. **HTML-sparning av admin** (Andreas, `docs/html/*.html`, gitignorerad: PII + admin-JS) →
   `docs/tools/extract_admin_html.py` → sanerad markdown per flik/modal i
   `docs/html/extracted/` (formulär, fält, hjälptexter; ingen kod, ingen PII).

### Beslut

- **Viktiga flikar:** APIs, Pipelines, Scripts, Servers, Users, **Access Control (superviktigt)**,
  Usage & Billing, Monitor. **Hoppa över:** Pricing (subs, ej lanserat), Blog, Landing Pages.
- **Viktiga pipelines:** bara **Heja** och **AZ Design**. Publika mallar har lågt värde.
  AZ exporterar Andreas manuellt senare (senaste versionen).
- Ingen kunddata och inga nycklar i docs, någonsin.
- **Scripten får sparas ordagrant med full kod** (Andreas byggt dem själv, se HANDOVER.md).
- **All dokumentation på engelska**, konversation på svenska (projektregel i CLAUDE.md +
  `.claude/rules/00-project-conventions.md`). `docs/` översatt 2026-09-29.

### Nästa steg

1. ✅ **`docs/ADMIN.md`** skriven (utkast): datamodell + alla viktiga flikar. Andreas granskar.
   Källor: `docs/html/extracted/*.md` (hur) + `docs/crawl/admin/api/*.json` (vad).
2. ✅ `docs/flows/HEJA.md` (bara skillnader), ✅ `docs/MODELS.md` + `models/CATALOG.md`, ✅ `docs/NODE_CONTRACT.md` + `scripts/` (46 script ordagrant). Kvar:
   ✅ `docs/flows/AZ.md` (fyra pipelines, prompts ordagrant ur crawlen; ingen manuell export behövs).
3. ✅ Pipeline-byggaren dokumenterad, admin (`ADMIN.md` 7.3) och user (`USER.md` 5.1).
4. ✅ User-delen: `docs/USER.md` (crawl `docs/crawl/user/`, gitignorerad, PII rensad).

**Steg 1 (dokumentation) är klart.** Kvar:
- Andreas roterar providernycklarna (Replicate, Gemini, xAI, OpenAI).
- Andreas lägger in `autoMode.allow`-regeln i `.claude/settings.local.json` (se konversation).
- **Steg 2: planera den nya produkten**, med `docs/` som underlag (börja i Explore-fasen).

### Scratch (gitignorerat, `docs/scratch/`)

`inspect_export.py`, `gap_analysis.py`, `review_crawl.py`, `scrub_crawl_pii.py`,
`inspect_saved_html.py` — analys-/rensningsverktyg från denna session.

---

## Tidigare fokus (2026-09-18, heja)

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
