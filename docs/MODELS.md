<!-- MODELS — vilka modeller apiai.me hade inkopplade, hur de användes och vad vi lärt oss. Skriven 2026-09-29 ur admin-data; detaljer per API i models/CATALOG.md (genererad). -->

# Modeller på apiai.me

Vilka modeller plattformen hade inkopplade 2026-09-29, vilka som faktiskt användes och vad
det lär oss inför en ny produkt.

- **Detaljer per API** (modell-ID, pris, konfiguration, alla parametrar, AI context):
  [`models/CATALOG.md`](models/CATALOG.md), genererad med `docs/tools/build_models_catalog.py`.
- **Hur man väljer modell:** `guidelines/MODEL_SELECTION_GUIDELINES.md` (typ först, ranking
  sen, eget eval avgör).
- **Hur en modell kopplas in i admin:** `ADMIN.md` avsnitt 4–5.

---

## 1. Providers

| Provider | Anslutning | API:er | Används till |
|---|---|---|---|
| **Replicate** | `api_key`, katalogsök + *Fetch Schema* | 24 | Bakgrundsborttagning, uppskalning, vektorisering, segmentering, video, bildgenerering |
| **Gemini** | `…/v1beta` | 11 | Nano Banana-familjen (bild), Veo (video), Flash Lite (vision → text) |
| **OpenAI** | `…/v1` | 7 | GPT Image 1.5 / 2 (bildredigering), GPT-4o-familjen (vision → text) |
| **xAI** | `…/v1` | 1 | Grok 3 mini (text) |
| **Python (lokal)** | — | 44 | Egna script. Några anropar modeller själva (se 3). |

Replicate är bredden: nästan allt som inte är Gemini eller OpenAI går dit, och en ny modell
kopplas in utan kod (sök → *Fetch Schema* → parametrarna mappas automatiskt).

---

## 2. Vad som faktiskt användes

Anrop 2026-08-31 till 2026-09-29. Bara modell-API:er; pipelines räknas separat.

| API | Modell | Anrop | Pris/anrop |
|---|---|---|---|
| Nano Banana 2 | `gemini-3.1-flash-image-preview` | **4 896** | $0.05 |
| Gemini 3.1 Flash Lite Preview | `gemini-3.1-flash-lite-preview` | **1 180** | $0.04 |
| Real Esrgan Upscaler | `nightmareai/real-esrgan` | 81 | $0.0022 |
| OpenAI GPT Image 2 | `gpt-image-2` | 48 | $0.04 |
| Bria Remove Background | `bria/remove-background` | 18 | $0.02 |
| Nano Banana Pro | `gemini-3-pro-image-preview` | 14 | $0.15 |

**Slutsats:** två modeller stod för nästan all trafik: Nano Banana 2 (bild) och Gemini Flash
Lite (vision → text). Av 43 modell-API:er hade **23 inga anrop alls** under perioden. Katalogen
är bred för att visa upp plattformen; den faktiska användningen är smal.

---

## 3. Modeller i de viktiga flödena

### Heja Team Emblem

| Steg | Modell | Via |
|---|---|---|
| Hitta och croppa loggan | `lucataco/florence-2-large` | Scriptet `detect_and_crop` (Replicate-biblioteket) |
| Ta bort bakgrund, förbättra | `gpt-image-2` (quality medium, background transparent) | API `openai-gpt-image-2` |
| Croppa referensen för färgkorrigering | `lucataco/florence-2-large` | Scriptet `correct_colors` |
| Uppskalning | `nightmareai/real-esrgan` (4× och 2×) | API `real-esrgan` |

Allt annat i flödet är egna script utan modell. Se `flows/HEJA.md`.

### AZ Design

| Flöde | Modell | Via |
|---|---|---|
| AZ Change Fabric - Mask | `gemini-3-pro-image-preview` | API `nano-banana-pro-inpainting` (scriptet `nb_pro_inpaint`, anropar Gemini direkt) |
| AZ Change Colour of Chair (med/utan tyg), Change Colour of Fabric | `gemini-3-pro-image-preview` | API `nano-banana-pro` |
| AZ Smooth mask … (Sam3), Smooth Mask Creator Fabric | `mattsays/sam3-image` → scriptet `smooth_mask` (→ `mask_checker`) | API `sam3-image` |

AZ-flödena dokumenteras i detalj när Andreas manuella export finns.

### Modeller som script anropar direkt

Dessa syns inte som modell-API:er, eftersom anropet sker inne i scriptet:

| Script | Modell |
|---|---|
| `detect_and_crop`, `correct_colors` | `lucataco/florence-2-large` (Replicate, fast version-hash) |
| `Detect and Remove Background` | `adirik/grounding-dino` (Replicate, fast version-hash) |
| `nb_pro_inpaint`, `nb_pro_reference_image` | `gemini-3-pro-image-preview` (Gemini direkt, `GEMINI_API_KEY`) |

Ett script som anropar en modell själv kan göra saker ett API inte kan: skicka mask och
referensbild i samma anrop, välja modellversion via hash, eller ha fallback-logik.
**Nackdel:** modellen syns inte i katalogen, och kostnaden bokförs inte per modell.

---

## 4. Lärdomar

1. **Prompten hör hemma i flödet, inte i modellen.** Ingen modell-API har en inbakad prompt;
   alla prompts sitter som *Fixed*-parameter på noden i pipelinen. Samma modell-API återanvänds
   då av många flöden. Undantag: kundspecifika API:er som `Nano Banana pro - repholstring`.
2. **Providerkostnaden registrerades aldrig** (0 av 87 API:er). Priset till kund sattes per
   API, men marginalen är okänd. En ny produkt bör logga providerns faktiska kostnad per anrop
   från start.
3. **AI context är värdefull men opålitlig.** Texterna (44 API:er) innehåller verkliga
   lärdomar om parametrar och egenheter, men är ofta AI-genererade och innehåller fel. Exempel:
   för GPT Image 2 står det "$0.22 flat rate", men priset är $0.04. Använd dem som ledtrådar.
4. **Hälsokontrollen täcker under hälften av modell-API:erna.** 16 av 43 verifierade, 3 failed
   (Flux Fill Pro, runwayml gen-4.5, Grounding Dino), 22 aldrig testade, 2 inaktiva. Inget
   video-API testades; en probe med riktig inferens är dyr för video **(tolkning)**.
5. **Fasta modellversioner i script.** Scripten pekar på exakta Replicate-versionshashar. Det
   gör resultaten reproducerbara, men uppgraderingar måste göras för hand.
6. **Konfigurationsfel överlever.** `sam3-image` och `check-resolution` har
   `response_type: video` fast de returnerar bilder, och `real-esrgan` har två parametrar som
   hör till ett annat verktyg. Plattformen tålde det, men en ny produkt bör validera
   I/O-typer mot modellens schema.
7. **Replicate för bredd, direktanrop för det viktiga.** Heja anropar GPT Image 2 och
   Real-ESRGAN direkt i den lokala versionen för att slippa apiai.me:s kö
   (CLAUDE.md, lärdom 5). Plattformens samtidighetsgräns (8 totalt / 4 per användare) är
   flaskhalsen, inte providerna.
