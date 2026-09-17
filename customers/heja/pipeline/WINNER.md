# WINNER — GPT Image 2 ersätter Nano Banana Pro + bakgrundsnoden

**Beslutat av Andreas 2026-08-31** efter ögonbedömning av hela setet: *"NY WINNER! Den satte
samtliga!"* Byts bara på ett nytt uttryckligt beslut — aldrig av en omkörning.

## Evalset

```
/Users/andreasquensel/Library/CloudStorage/GoogleDrive-andreas@zebrolabs.com/
  Shared drives/Apiai.me/Customers/Heja/Content/Team Logos/
```

10 loggor i setet. Kör `run_all.py --method v2` för hela batchen, eller `run_pipeline_v2.py` på
en enskild fil.

## Konfiguration (19 noder)

Pipelinen har två flöden: **låg kvalitet** (GPT2) och **hög kvalitet** (skip GPT2).
Condition-noder räknas som egna steg.

### Låg kvalitet-flöde (nod 1-9, END)

| # | Nod | Parametrar |
|---|-----|------------|
| 1 | Detect and Crop | `query="complete logo..."` · `min_padding=5` |
| 2 | Check Quality | `mp_high=1.0` · `mp_low=0.09` · `flatness=80` · `gradient=50` |
| 3 | **Condition** | skip 6 when `has_high_quality`=`true` → nod 10 |
| 4 | **GPT Image 2** | `background=transparent` · `output_format=png` · `quality=medium` · `size=auto` |
| 5 | **Correct Colors** | `image_reference=original` · `auto_crop_reference=true` · `min_coverage=5` · `min_delta_e=10` · `cluster_merge_threshold=8` · `add_edge_border=true` · `border_width=20` |
| 6 | Check Resolution | `min_pixels=5000000` |
| 7 | **Condition** | skip 1 when `is_high_resolution`=`true` → nod 9 |
| 8 | Upscale 4x | `scale=4` · `face_enhance=false` |
| 9 | Transparent Crop | `format=1:1` · `margin=10` · `alpha_threshold=10` · **END PIPELINE** |

### Hög kvalitet-flöde (nod 10-19)

| # | Nod | Parametrar |
|---|-----|------------|
| 10 | Check Transparency | `sample_percent=5` · `threshold=250` |
| 11 | **Condition** | skip 1 when `has_transparency`=`true` → nod 13 |
| 12 | Remove Solid BG | `bg_color=auto` · `tolerance=20` · `feather=1` · `detections=false` · `remove_holes_threshold=0` |
| 13 | Check Resolution | `min_pixels=5000000` |
| 14 | **Condition** | skip 4 when `is_high_resolution`=`true` → nod 19 |
| 15 | Upscale 4x | `scale=4` · `face_enhance=false` |
| 16 | Check Resolution | `min_pixels=5000000` |
| 17 | **Condition** | skip 1 when `is_high_resolution`=`true` → nod 19 |
| 18 | Upscale 2x | `scale=2` · `face_enhance=false` |
| 19 | Transparent Crop | `format=1:1` · `margin=10` · `alpha_threshold=10` |

### Prompt (ordagrant)

> Remove background outside the team emblem. Important keep the logo identical with shape and
> colours. The colours must match the original exactly.

Andreas egna ord. Tre enkla meningar slår NB Pros sex numrerade regelblock: **enklare promptar vinner.**

## Tests run

| Datum | Tag | Set | Resultat | Anteckningar |
|-------|-----|-----|----------|--------------|
| 2026-08-31 | gpt2a | 9 loggor | 9/9 | Första GPT-2-testet, Andreas: "NY WINNER!" |
| 2026-09-04 | v2 | 10 loggor | 10/10 | Med kvalitetsrouting (buggig) |
| 2026-09-04 | v2-fix | 9 loggor | 9/9 | Fixad routing (kvalitet före transparens) |
| 2026-09-08 | v2-gradient | 10 loggor | 10/10 | Gradient-fix + GPT-2 transparens + Replicate ESRGAN |

Rapport: `out/steps.html` (en flik per tag).
Human eval av föregående mästare: `../../evaluator/customers/heja/HUMAN_EVAL.md`.

## Varför den vann

**Den löser båda bakgrundsfelen genom att ta bort noden som orsakade dem.** GKT:s ficka mellan K
och T är genomskinlig, Knivstas över-borttagning är borta. `detect_and_remove_bg` var en geometrisk
fyllning utan begrepp om var designen slutade; en modell som just ritat loggan vet det.

**Den ritar Chicago Blues FC.** NB Pro vägrar den konsekvent (`finishReason=IMAGE_RECITATION`,
Geminis upphovsrättsspärr) → Seedream 4 som fallback → det enda färgfelet. GPT Image 2 klarar den.
**Kedjan går från tre modeller till en.**

**`size=auto` var rätt val, mätt.** Att tvinga fram en kvadrat lade 59 % av Trollbäckens pixlar på
vit utfyllnad. Auto ger 1,57 MP oavsett format — loggan får hela budgeten.

## Known issues

### leopards årtal oläsligt

Originalet är 224 px och siffrorna är gröt vid 12× förstoring. NB Pro läser `1998`, GPT Image 2
`1988` — ingen av oss kan avgöra vilken som är rätt. Andreas bedömning: dåligt indata, klubben vet
sitt eget grundår.

**Åtgärd:** flagga lågupplösta indata. 224 px går att mäta.

### Uppskalaren kan ge sömmar

GPT Image 2: noll sömmar på alla nio. NB Pro-kedjan: sömmar på två av åtta. Spårat till
`real-esrgan` kakling (tile-gränser vid 2324 och 868 i en 4096-bild).

**Åtgärd:** `tile=0` eller värde större än bilden. Otrimmad parameter.

### Cantagalo-problemet

Transparent bild med dåliga kanter. Modellen kan inte "se" vad som var transparent från början —
den gissar. Lösning: kvalitetsrouting baserad på gradient_pct, inte bara transparens.

## Learnings

**1. AI ska endast användas när det verkligen behövs.** Testa först (kvalitetsrouting). En bild
som redan är bra + transparent ska inte passera en modell. Det är den största lärdomen från
hela projektet.

**2. Modeller kan ligga nere — fallbacks behövs alltid.** Grounding DINO var nere i flera dagar;
Florence-2 tog över. Real-ESRGAN via apiai.me gav 429; Replicate direkt löste det.

**3. Generativa modeller plattar till — kan inte se tidigare transparens.** GPT-2 ser en RGB-bild
och gissar var bakgrunden är. Cantagalo hade redan perfekt transparens men dåliga kanter →
GPT-2 behövdes för kanterna, inte för bakgrunden.

**4. Generativ AI översätter till RGB — färger kan ändras.** Ännu en anledning att inte använda
AI när det inte behövs. leopards årtal är ett exempel på hur modellen gissar när originalet är
för dåligt.

**5. Kvalitetsmätning kräver flera dimensioner.** MP ensamt räcker inte. Cantagalo hade 0.14 MP
(över low threshold) men 0% smooth edges. Alla tre metrics (MP, flatness, gradient) behövs.

**6. Direkt-anrop undviker flaskhalsar.** OpenAI direkt + Replicate direkt istället för via
apiai.me. Både snabbare (parallellt) och undviker rate limits.

**7. Den bästa körningen är ingen körning.** `transparent_skip` är den billigaste och mest
trogna routen. Kvalitetstest först sparar pengar och bevarar originalets integritet.

**8. Enklare promptar vinner.** Tre meningar slog NB Pros sex numrerade regelblock.

**9. Generativa modeller återskapar färger — de läser inte RGB.** Modellen "ser" bilden och ritar
om den, den kopierar inte pixelvärden. Röda, guld och orange driftar mest (blir fluorescerande
eller plattare). Om färgexakthet är viktigt: extrahera dominanta färger, jämför med original
(ΔE i CIELAB), och byt tillbaka de som driftat. Se `correct_colors.py`.

**10. Smart tolerans vid färgbyte.** När två liknande färger finns (t.ex. ljusblå och mörkblå)
måste bytet vara precist. Använd ΔE/2 som tolerans — bara pixlar som ligger mycket nära
målfärgen byts. Annars riskerar man att byta fel nyans.

**11. Testa alltid efter review-ändringar.** Claude-in-apiai.me kan föreslå ändringar som
bryter scriptet (t.ex. justera thresholds, byta bibliotek). Efter implementering av review-
feedback: **kör om lokalt test innan deploy.** Lita aldrig blint på reviewern.

**12. apiai.me pipelines är linjära.** Inte DAGs. Skip fungerar med antal noder att hoppa över.
Två checks efter varandra fungerar inte (bara senaste outputen finns). Använd `end_pipeline`
för att terminera ett flöde tidigt när det finns flera flöden i samma pipeline.

## Cost

| Modell | Per logga (generativ nod) |
|--------|---------------------------|
| Nano Banana Pro | ~$0,13 |
| **GPT Image 2, medium** | **~$0,05** |

~60 % billigare. Bara 6 av 10 passerar modellen (fyra är redan transparenta) → **$0,03 per logga
i snitt**. Vid tusen loggor: ~$30.

⚠️ Siffran är härledd, inte fakturerad. Dynamiskt pris behövs innan den sätts i kundavtal.

---

## Historik

### NB Pro-kedjan — mästare till 2026-08-31

Nod 3 `nano-banana-pro` (`temperature=0.2` · `top_k=15` · `top_p=0.1` · `image_size=1K`) med
"master Art Restorer"-prompten, följd av nod 4 `detect_and_remove_bg`
(`query="emblem or shield or badge"` · `remove_holes_threshold=2`), plus **Seedream 4** som fallback
när Gemini vägrar.

Andreas dom på hela setet: 6/9 rena. Ett färgfel (Chicago — Seedreams, inte NB Pros) och två fel
i nod 4. Alla åtta klubbnamn korrekta. Fullständig genomgång i `HUMAN_EVAL.md`.
