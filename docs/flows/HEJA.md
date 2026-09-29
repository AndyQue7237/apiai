<!-- HEJA — skillnader mellan den lokala Heja-dokumentationen och flödet som faktiskt körde på apiai.me 2026-09-29. Ur flow_config (admin-API) och exporterade script. -->

# Heja Team Emblem: apiai.me jämfört med lokalt

Heja-flödet är redan dokumenterat lokalt, och det är **huvudkällan**:

- `customers/heja/pipeline/APIAI_SETUP.md` — alla 22 noder, parametrar och villkor
- `customers/heja/pipeline/WINNER.md` — varför det ser ut så, evalresultat och lärdomar
- `customers/heja/pipeline/run_pipeline_v2.py` — den lokala körbara versionen

Det här dokumentet tar **bara upp det som skiljer** mellan den lokala dokumentationen och
flödet `heja-team-emblem` som det låg på apiai.me 2026-09-29, avläst ur `flow_config`.
Strukturen stämmer: 22 noder, samma ordning, samma fem villkor med samma `skip_count`,
`output_node = node_22`.

## Skillnader

| # | Nod | Lokalt (`APIAI_SETUP.md`) | På apiai.me | Betydelse |
|---|---|---|---|---|
| 1 | 10, 22 (slutcrop) | Script `crop_transparent`, `format: 1:1` | API **`smart-crop`**, `format: square`, `background: transparent`, `subject_scale` omitted | **Samma kod, annat namn:** lokala `scripts/crop_transparent.py` är identisk med scriptet `smart_crop` på sajten. `square` och `1:1` betyder samma sak. (Lokala `scripts/smart_crop.py` är ett äldre, annat script.) |
| 2 | 10 (slut på lågkvalitetsgrenen) | `end_pipeline: true` | **`stop_after: true`** på noden | Samma funktion, annat namn. |
| 3 | 6, 14, 18 (check resolution) | `min_pixels: 5000000` | **`max_pixels: 5000000`** + `field: is_high_resolution` | Parametern heter `max_pixels` även lokalt, trots att den är ett golv. `APIAI_SETUP.md` har fel namn. |
| 4 | 1 (detect and crop) | `query`, `min_padding` | + **`safety_margin: 30`**, **`padding_percent: 5`** | Två parametrar till på sajten. |
| 5 | 4 (GPT Image 2) | — | + **`moderation: low`** | Sänkt moderering, så att logotyper inte blockeras i onödan **(tolkning)**. |
| 6 | 9, 17, 21 (Real-ESRGAN) | `scale`, `face_enhance` | + `threshold` och `sample_percent` **Omit** | API:t `real-esrgan` har två felaktiga parametrar (kopierade från `check-transparency`). Omit hindrar att de skickas till Replicate. |
| 7 | 11 (check transparency) | `sample_percent`, `threshold` | + `field: has_transparency` | Fältnamnet sätts explicit. |

## Skip: kod lokalt, condition-noder på apiai

Lokalt (`run_pipeline_v2.py`) ligger routingen och hoppen i Python-koden som `if/else`.
Routes: `gpt2_enhancement`, `transparent_skip`, `script_bg_removal`, `gpt2_edge_case`.
På apiai finns ingen kod mellan noderna, så samma beslut görs med **condition-noder**, där
`skip_count` hoppar över de N följande noderna. Därför blir flödet 22 noder, med två
separata grenar efter varandra: nod 1–10 för låg kvalitet, som slutar med `stop_after`, och
nod 11–22 för hög kvalitet.

Två följder av det:
- **Samma steg upprepas.** Check resolution, downscale och upscale finns i båda grenarna,
  eftersom en condition bara kan hoppa framåt, inte förgrena sig och gå ihop igen.
- **`run_pipeline_v2.py` är en äldre version än apiai-flödet.** Det saknar
  färgkorrigering och andra uppskalningen, och har kvar routen `gpt2_edge_case`
  (flerfärgad bakgrund → GPT). På apiai skickas den bilden i stället vidare oförändrad
  (`passthrough_on_mismatch: true` på nod 13). `APIAI_SETUP.md` beskriver apiai-versionen.

## Hur kopplingen fungerar på apiai

Varje nod tar bilden från föregående nod (`from_node`), **även från condition-noder och från
noder som hoppas över**. Exempel: nod 11 läser från nod 10, men i högkvalitetsgrenen körs
nod 4–10 aldrig. Plattformen skickar alltså vidare senaste faktiska resultat genom hoppade
noder **(tolkning:** det är det enda sätt flödet kan fungera på).

Enda undantaget är nod 5 (`correct-colors`): `image_reference` binds till **Original**
(`use_original`), alltså pipelinens inbild. Så jämförs GPT-bilden mot originalets färger.

Pipelinens publika input är bara `image` (Expose på nod 1). Alla andra parametrar är fasta.

## Scriptversioner

Två script skiljer sig i koden mellan `scripts/` och sajten, och ett har bytt namn:

| Script | Skillnad |
|---|---|
| `check_resolution` | Sajten använder `PARAM_DEFS` + `script_io`, returnerar bara boolen. Samma logik. |
| `check_transparency` | Sajten kräver `script_io` (lokalt finns fallback utan). Samma logik. |
| `smart_crop` | Sajtens `smart_crop` = lokala `crop_transparent.py`, identisk kod. Lokala `smart_crop.py` är en äldre variant. |

Sajtens versioner finns ordagrant i `docs/export/*.sanitized.json` (`scripts[].source_code`).

## Småsaker

- API:t `check-resolution` har `response_type: "video"` i sin konfiguration, trots att det
  returnerar en bild. Det verkar inte påverka flödet, men det är fel.
- `WINNER.md` (2026-09-21): nod 20 står på `max_pixels: 2000000`, vilket stämmer med sajten.
