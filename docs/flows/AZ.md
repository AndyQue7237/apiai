<!-- AZ — AZ Designs fyra pipelines på apiai.me som de låg 2026-09-29: noder, bindningar och prompts ordagrant. Ur flow_config (admin-API). -->

# AZ Design: pipelines på apiai.me

AZ Design är en möbeltillverkare som tar fram produktvarianter av stolar till sin katalog:
ny bets (träfärg) eller nytt tyg på samma stol. Kundkontext och eval finns i
`customers/az-design/eval/README.md`.

Det här dokumentet återger AZ:s **fyra pipelines exakt som de låg på apiai.me 2026-09-29**
(senast ändrade 22–23 juni 2026). Prompterna är ordagranna ur `flow_config` och är
**produktionsversionerna**. De skiljer sig tydligt från utkasten i
`customers/az-design/eval/prompts.yaml`.

## Översikt

| Pipeline | Slug | Gör | Modell | Anrop 30 d |
|---|---|---|---|---|
| AZ Smooth mask fabric creator with check (Sam3) | `az-smooth-mask-fabric-creator-with-check-sam3` | Tar fram en mask för stolens tyg och kontrollerar den | SAM 3 + egna script | 0 |
| AZ Change Fabric - Mask | `az-change-fabric-mask` | Byter tyg, bara innanför masken | Nano Banana Pro via scriptet `nb_pro_inpaint` | **31** (0 fel) |
| AZ Change Colour of Chair | `az-change-colour-of-chair` | Byter bets på trädelarna, tyget orört | Nano Banana Pro | 0 |
| AZ Change Colour of Chair without Fabric | `az-change-colour-of-chair-without-fabric` | Byter material/färg på hela stolen | Nano Banana Pro | 0 |

*Anrop 30 d* = 2026-08-31 till 2026-09-29. Tygbytet anropas som `pipeline:az-change-fabric-mask`
i användningsloggen. **Inpainting-flödet är alltså det som används.** De övriga tre hade inga anrop under perioden.

Alla fyra är gratis (`price_per_request: 0`) och varken template eller global: de nås via
team-/användaråtkomst (`ADMIN.md` avsnitt 2).

## Tygbyte: två pipelines i följd

Tygbytet görs i två steg, och masken återanvänds för varje tyg:

```
stolfoto ──▶ [Smooth mask … (Sam3)] ──▶ mask (+ kontroll)
                                          │
stolfoto + mask + tygprov ──▶ [AZ Change Fabric - Mask] ──▶ stol med nytt tyg
```

Kedjan står i `nb_pro_inpaint`:s docstring: *chair → SAM-3 → smooth_mask → nb_pro_inpaint →
final*. Masken tas fram en gång per stol och används sedan för alla tyger (9 tyger × 2 stolar
enligt eval-README). Uppringaren skickar masken och tygprovet som parametrar
(`image_mask`, `image_reference`).

---

## 1. AZ Smooth mask fabric creator with check (Sam3)

`az-smooth-mask-fabric-creator-with-check-sam3` · *"Finds an object and creates a smooth
mask."* · 3 noder · `output_node = node_3`

| Nod | API | Bindningar |
|---|---|---|
| 1 | `sam3-image` (Replicate `mattsays/sam3-image`) | `image` **Expose** · `prompt` = `fabric` · `mask_only` = `true` · `threshold` = `0.3` · `return_zip` = `false` · övriga Default |
| 2 | `smooth-mask` (script `smooth_mask`) | `image` ← nod 1 · `mode` = `adaptive` · `expand_px` = `1` · `fill_holes` = `true` · `min_region_size` = `50` · `smooth_strength` = `0.5` · `transparent_edge_px` = `0.5` · `target_format` = `original` |
| 3 | `mask-checker` (script `check_mask`), **`stop_after: true`** | `image` ← **Original** · `image_mask` ← nod 2 · `output_mode` = `zip` · `max_drift_px` = `7` · `color`, `opacity` Default |

- **SAM 3** segmenterar allt som matchar textprompten `fabric` och returnerar bara masken.
- **`smooth_mask`** i läget `adaptive` jämnar ut SAM:s trappstegskanter. Tunna detaljer
  bevaras medan stora ytor rundas. Hål fylls och småfläckar under 50 px tas bort.
- **`check_mask`** mäter hur långt maskens kant avviker från verkliga kanter i originalfotot.
  Över 7 px ger underkänt. `zip` returnerar mask + overlay + JSON-rapport. Beslutet följer
  alltid med som extra fält.

## 2. AZ Change Fabric - Mask

`az-change-fabric-mask` · 1 nod · `output_node = node_1`

**API:** `nano-banana-pro-inpainting`, som kör scriptet `nb_pro_inpaint` → Gemini
`gemini-3-pro-image-preview` direkt. AI:ns resultat blandas in **bara innanför masken**:
`final = ai · (mask · blend) + subject · (1 − mask · blend)`. Utanför masken är stolen
pixelidentisk med originalet.

| Parameter | Bindning |
|---|---|
| `image` | **Expose** `image` (stolfotot) |
| `image_mask` | **Expose** `image_mask` (från pipeline 1) |
| `image_reference` | **Expose** `image_reference` (tygprovet) |
| `temperature` | `0.3` |
| `top_k` / `top_p` | `45` / `0.9` |
| `image_size` / `aspect_ratio` | `1K` / `1:1` |
| `blend_strength` | `1` |
| `safety_filter_level` | `BLOCK_ONLY_HIGH` |
| `negative_prompt`, `max_output_tokens` | Omit |

**Prompt** (Fixed, ordagrant):

```text
Professional product photography of the chair from Image 1, demanding absolute, form-deviation-free geometric and material preservation of the entire non-cushioned structure. All components not listed as upholstered, including the legs and frame, must retain their exact original material integrity, color, and finish as seen in Image 1. This is a surgical inpainting task: Identify all existing upholstered, cushioned, or padded surfaces and perform a material replacement on all of these specific identified areas using the exact texture, color, and pattern strictly from Image 2. Crucially, maintain absolute chromatic fidelity; the material's hue, saturation, and color temperature must remain identical to the source sample in Image 2, strictly preventing any color shift, tinting, or contamination from the ambient lighting or original colors of Image 1. The surface of the new material must remain perfectly taut, pristine, and smooth, strictly mirroring the precise spand and even surface tension of the original components in Image 1, with zero added wrinkles, creases, folds, or indentations. Isolated on a solid #FFFFFF pure white background, high-key lighting, minimal soft contact shadows under the object, no grey tones. Strictly forbid any texture bleed, environmental mapping, or background pattern from Image 2.
```

## 3. AZ Change Colour of Chair (bets)

`az-change-colour-of-chair` · *"Changes colour of chair (bets)"* · 1 nod

**API:** `nano-banana-pro` (Gemini `gemini-3-pro-image-preview`, direkt, **utan mask**).
Image 1 = stolen, Image 2 = betsprovet. Båda skickas som filer till samma exponerade
`image`-input: API:t har `max_images: 4`, alltså tar primär-inputen flera bilder, och
ordningen avgör vilken som är "Image 1" **(tolkning)**.

| Parameter | Bindning |
|---|---|
| `image` | **Expose** `image` |
| `temperature` | `0.1` |
| `top_k` / `top_p` | `40` / `0.85` |
| `image_size` / `aspect_ratio` | `1K` / `1:1` |
| `safety_filter_level` | Default |
| `negative_prompt`, `max_output_tokens` | Omit |

**Prompt** (Fixed, ordagrant):

```text
A photorealistic product photograph of the specific chair from Image 1, demanding absolute, form-deviation-free geometric and structural lock. Crucially, strictly maintain the exact spatial relationship between wood and fabric; do not add, remove, or hallucinate any new wooden borders, frames, or panels that change the existing upholstery edge-work. If fabric extends fully to the edge in Image 1, it must remain fabric-to-edge in the output. Perform a surgical, procedural material replacement exclusively on the entire existing wooden surface area. This new stained wood finish must be procedurally derived from the specific color, texture, and grain characteristics strictly from Image 2. Maintain an absolute and literal chromatic lock, where the wood's specific hue, saturation, value, and precise color temperature must be procedurally replicated from the sample in Image 2. The upholstery must remain completely unchanged from Image 1. The new finish must wrap naturally around the chair's form with appropriate volumetric lighting and shadows. Isolated on a solid #FFFFFF pure white background, high-key lighting, minimal soft contact shadows under the object, no grey tones.
```

## 4. AZ Change Colour of Chair without Fabric

`az-change-colour-of-chair-without-fabric` · 1 nod

Samma uppsättning som 3, men för stolar **utan tyg**: materialet byts på hela stolen, inte
bara på trädelarna. Enda skillnaden i parametrarna: `safety_filter_level` är **Expose**
(default `BLOCK_ONLY_HIGH`), så uppringaren kan ändra den.

**Prompt** (Fixed, ordagrant):

```text
A photorealistic product photograph of the specific chair from Image 1, demanding absolute, form-deviation-free geometric and structural lock. Perform a surgical, procedural material replacement across the entire surface area and structure of the chair. This new finish must be procedurally derived from the specific color, texture, glossiness, and material characteristics (such as grain, sheen, or metallic finish) strictly from the sample in Image 2. Maintain an absolute and literal chromatic lock, where the material's specific hue, saturation, value, and precise color temperature must be procedurally replicated from the reference in Image 2. The new material must wrap naturally around the chair's three-dimensional form with appropriate volumetric lighting, specular highlights, and shadows that match the chair's geometry. Isolated on a solid #FFFFFF pure white background, high-key lighting, minimal soft contact shadows under the object, no grey tones.
```

---

## Lärdomar

1. **Mask + inpainting för tyg, fri redigering för bets.** Tyget byts i en avgränsad yta, och
   masken garanterar att trä och ben inte rörs. Betsen täcker all trä, så där räcker en
   prompt som låser tyget ("The upholstery must remain completely unchanged").
2. **Promptstilen är "lås allt, byt en sak".** Alla tre prompts börjar med en stark
   geometrilåsning (*form-deviation-free geometric … lock*), avgränsar exakt vad som ska bytas,
   kräver *chromatic lock* mot provet och slutar med samma studiobakgrund (#FFFFFF,
   high-key). Bets-prompten har dessutom en regel mot påhittade träkanter, en observerad felkälla.
3. **Låg temperatur** (0.1–0.3) för återgivning. Kreativitet är inte målet.
4. **Masken som eget flöde med kvalitetskontroll.** Att dela upp i två pipelines gör att en
   mask kan granskas (`check_mask`, max 7 px drift) och återanvändas för många tyger.
5. **Produktionsprompterna finns bara här.** Enligt Andreas (2026-09-29) är sajtens prompts de
   aktuella. `customers/az-design/eval/prompts.yaml` var mer work in progress och har inte
   synkats.
