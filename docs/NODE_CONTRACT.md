<!-- NODE_CONTRACT — hur ett Python-script blir en nod på apiai.me: runtime-kontraktet, plattformens gränser, och var alla 46 script finns ordagrant. Skriven 2026-09-29. -->

# Nodkontraktet: från script till nod

Hur ett Python-script blir ett anropbart verktyg och en nod i en pipeline på apiai.me.

- **Reglerna för att skriva ett script** (kontraktet i detalj): `guidelines/SCRIPT_GUIDELINES.md`.
  Det här dokumentet upprepar dem inte, utan sammanfattar och lägger till plattformens egna
  fakta ur admin.
- **Alla 46 script ordagrant:** [`scripts/`](scripts/), med katalog i
  [`scripts/CATALOG.md`](scripts/CATALOG.md). Andreas beslut 2026-09-29: scripten sparas
  med full kod (se `HANDOVER.md`).

---

## 1. Kontraktet i korthet

Ett script är ett fristående program som plattformen startar per anrop.

```
stdin:  {"image": "<base64>", "content_type": "image/png", "params": {...}}
stdout: {"image": "<base64>", "content_type": "image/png", ...extra fält på roten}
```

- **I/O går via `script_io`**, som runtime tillhandahåller: `read_input()`,
  `write_output(bytes, content_type, **fält)` och `write_error(meddelande)`. En lokal kopia
  för test finns i `customers/heja/pipeline/script_io.py`.
- **En enda bild i kroppen.** Fler bilder (mask, referens) kommer som base64-strängar i
  `params`. Pipelinens *Original*-bindning (`ADMIN.md` 7.2) skickar pipelinens inbild till en
  sådan bildparameter **(tolkning)**.
- **Parametrar deklareras i `PARAM_DEFS`** i scriptet. Admins *Scan Script* läser dem och
  skapar API:ts parameterlista automatiskt.
- **Extra fält på roten blir metadata** som condition-noder kan läsa (`condition_field`).
  Exempel: `check_quality` skriver `has_high_quality`, `check_resolution` skriver
  `is_high_resolution`. Aldrig i ett nästlat `metadata`-objekt.
- **Utdata är RGBA-PNG** för bildscript.

## 2. Plattformens ramar (ur admin 2026-09-29)

| Ram | Värde |
|---|---|
| Server | "Pyton Scripts", typ `python`, URL `local`. Scripten körs på plattformens egen server. |
| Tillåtna paket | `Pillow`, `replicate`, `numpy`, `opencv-python-headless`, `scikit-image`, `cairosvg`, `scipy`, `pillow-heif` + stdlib. Väljs per script i fältet *Packages*. Inte `requests`, inte `scikit-learn`. |
| Miljövariabler | `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `REPLICATE_API_TOKEN`, `XAI_API_KEY` (via `os.environ`) |
| Timeout | Sätts per API: standard 30 s, max 300 s |
| Utdatatyper | Image (PNG/WebP), Video (MP4), Audio, Text (JSON), ZIP |
| Samtidighet | 8 körningar totalt, 4 per användare (gäller alla API:er, inte bara script) |

## 3. Från script till nod, steg för steg

1. **Scripts → Add Script:** namn (filnamn utan `.py`), beskrivning, paket, källkod.
   Testa med *Test Script* (bild + params som JSON). Det finns också en AI-assistent,
   *Ask Claude* / *Fix it*, som kan skriva scriptet.
2. **APIs → Add API:** server "Pyton Scripts", välj scriptet, sätt timeout och I/O-typer.
   *Scan Script* hämtar parametrarna. Sätt pris (script är ofta gratis) och beskrivning.
   *Test Run* och en kontroll före sparning fångar trasiga API:er.
3. **Access Control:** ge API:t till rätt nivå (global, användare, team). Utan åtkomst kan
   ingen anropa det, och en template får bara använda globala verktyg.
4. **Pipelines → Add Pipeline:** klicka in API:t som nod och bind varje parameter (*Fixed*,
   *Wire*, *Expose*, *Omit*, *Default*; `ADMIN.md` 7.2).

## 4. Läget för scripten

46 script på sajten, jämförda med `scripts/` i detta repo (detaljer i `scripts/CATALOG.md`):

| Läge | Antal | Script |
|---|---|---|
| Identiska | 11 | bl.a. `check_quality`, `correct_colors`, `detect_and_crop`, `nb_pro_inpaint`, `smooth_mask` |
| Identiska, annat namn | 3 | `smart_crop` = `crop_transparent.py` · `remove_solid_bg` = `remove_solid_background.py` · `auto_crop` = `crop_center.py` |
| Skiljer sig | 2 | `check_resolution`, `check_transparency` (sajten kräver `script_io`; samma logik, se `flows/HEJA.md`) |
| Bara på sajten | 30 | Filter, video, text, format m.m. Nu sparade i `docs/scripts/`. |
| Bara i repot | 4 | `compress_video`, `has_solid_background`, `logo_pipeline_complete`, `make_square` |

**Mest använda script-API:er** (anrop 2026-08-31 till 2026-09-29): `flip-mirror` (67),
`correct-colors` (52), `fancy-text-on-images` (29), `format-converter` (21),
`remove-solid-background` (17), `fabric-swap-material-swap` (14).

## 5. Lärdomar för en ny produkt

1. **Stdin/stdout-JSON räcker.** Kontraktet är litet nog att köras var som helst, t.ex. i
   en container eller en serverless-funktion. Scripten går att flytta utan ändring, så länge
   `script_io` följer med.
2. **Metadata på roten är motorn i routingen.** Condition-noder läser fält direkt från
   föregående nods utdata. Håll fältnamnen stabila; de är ett API.
3. **Paketlistan är en säkerhetsgräns.** Allowlist + nycklar via miljövariabler gör att
   kunder och AI-assistenten kan skriva script utan full systemåtkomst.
4. **Namnen glider isär.** Tre script har bytt namn mellan repo och sajt, och två har
   ändrats bara på sajten. En ny produkt bör ha **en** källa för scriptkoden (repot) och
   deploya därifrån, inte redigera i admin.
