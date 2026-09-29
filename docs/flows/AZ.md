<!-- AZ — AZ Design's four pipelines on apiai.me as they stood on 2026-09-29: nodes, bindings and prompts verbatim. From flow_config (admin API). -->

# AZ Design: pipelines on apiai.me

AZ Design is a furniture manufacturer that produces product variants of chairs for its catalog:
a new stain (wood color) or new fabric on the same chair. Customer context and eval are in
`customers/az-design/eval/README.md`.

This document reproduces AZ's **four pipelines exactly as they stood on apiai.me on 2026-09-29**
(last changed 22–23 June 2026). The prompts are verbatim from `flow_config` and are the
**production versions**. They differ clearly from the drafts in
`customers/az-design/eval/prompts.yaml`.

## Overview

| Pipeline | Slug | Does | Model | Calls 30 d |
|---|---|---|---|---|
| AZ Smooth mask fabric creator with check (Sam3) | `az-smooth-mask-fabric-creator-with-check-sam3` | Creates a mask for the chair's fabric and checks it | SAM 3 + own scripts | 0 |
| AZ Change Fabric - Mask | `az-change-fabric-mask` | Swaps fabric, only inside the mask | Nano Banana Pro via the script `nb_pro_inpaint` | **31** (0 errors) |
| AZ Change Colour of Chair | `az-change-colour-of-chair` | Changes the stain on the wooden parts, fabric untouched | Nano Banana Pro | 0 |
| AZ Change Colour of Chair without Fabric | `az-change-colour-of-chair-without-fabric` | Changes material/color on the whole chair | Nano Banana Pro | 0 |

*Calls 30 d* = 2026-08-31 to 2026-09-29. The fabric swap is called as `pipeline:az-change-fabric-mask`
in the usage log. **So the inpainting flow is the one in use.** The other three had no calls during the period.

All four are free (`price_per_request: 0`) and neither template nor global: they are reached via
team/user access (`ADMIN.md` section 2).

## Fabric swap: two pipelines in sequence

The fabric swap is done in two steps, and the mask is reused for every fabric:

```
chair photo ──▶ [Smooth mask … (Sam3)] ──▶ mask (+ check)
                                             │
chair photo + mask + fabric sample ──▶ [AZ Change Fabric - Mask] ──▶ chair with new fabric
```

The chain is stated in `nb_pro_inpaint`'s docstring: *chair → SAM-3 → smooth_mask → nb_pro_inpaint →
final*. The mask is created once per chair and then used for all fabrics (9 fabrics × 2 chairs
according to the eval README). The caller sends the mask and the fabric sample as parameters
(`image_mask`, `image_reference`).

---

## 1. AZ Smooth mask fabric creator with check (Sam3)

`az-smooth-mask-fabric-creator-with-check-sam3` · *"Finds an object and creates a smooth
mask."* · 3 nodes · `output_node = node_3`

| Node | API | Bindings |
|---|---|---|
| 1 | `sam3-image` (Replicate `mattsays/sam3-image`) | `image` **Expose** · `prompt` = `fabric` · `mask_only` = `true` · `threshold` = `0.3` · `return_zip` = `false` · others Default |
| 2 | `smooth-mask` (script `smooth_mask`) | `image` ← node 1 · `mode` = `adaptive` · `expand_px` = `1` · `fill_holes` = `true` · `min_region_size` = `50` · `smooth_strength` = `0.5` · `transparent_edge_px` = `0.5` · `target_format` = `original` |
| 3 | `mask-checker` (script `check_mask`), **`stop_after: true`** | `image` ← **Original** · `image_mask` ← node 2 · `output_mode` = `zip` · `max_drift_px` = `7` · `color`, `opacity` Default |

- **SAM 3** segments everything matching the text prompt `fabric` and returns only the mask.
- **`smooth_mask`** in `adaptive` mode smooths out SAM's staircase edges. Thin details
  are preserved while large areas are rounded. Holes are filled and specks under 50 px are removed.
- **`check_mask`** measures how far the mask's edge deviates from real edges in the original photo.
  Above 7 px means fail. `zip` returns mask + overlay + JSON report. The verdict always
  travels along as an extra field.

## 2. AZ Change Fabric - Mask

`az-change-fabric-mask` · 1 node · `output_node = node_1`

**API:** `nano-banana-pro-inpainting`, which runs the script `nb_pro_inpaint` → Gemini
`gemini-3-pro-image-preview` directly. The AI's result is blended in **only inside the mask**:
`final = ai · (mask · blend) + subject · (1 − mask · blend)`. Outside the mask the chair is
pixel-identical to the original.

| Parameter | Binding |
|---|---|
| `image` | **Expose** `image` (the chair photo) |
| `image_mask` | **Expose** `image_mask` (from pipeline 1) |
| `image_reference` | **Expose** `image_reference` (the fabric sample) |
| `temperature` | `0.3` |
| `top_k` / `top_p` | `45` / `0.9` |
| `image_size` / `aspect_ratio` | `1K` / `1:1` |
| `blend_strength` | `1` |
| `safety_filter_level` | `BLOCK_ONLY_HIGH` |
| `negative_prompt`, `max_output_tokens` | Omit |

**Prompt** (Fixed, verbatim):

```text
Professional product photography of the chair from Image 1, demanding absolute, form-deviation-free geometric and material preservation of the entire non-cushioned structure. All components not listed as upholstered, including the legs and frame, must retain their exact original material integrity, color, and finish as seen in Image 1. This is a surgical inpainting task: Identify all existing upholstered, cushioned, or padded surfaces and perform a material replacement on all of these specific identified areas using the exact texture, color, and pattern strictly from Image 2. Crucially, maintain absolute chromatic fidelity; the material's hue, saturation, and color temperature must remain identical to the source sample in Image 2, strictly preventing any color shift, tinting, or contamination from the ambient lighting or original colors of Image 1. The surface of the new material must remain perfectly taut, pristine, and smooth, strictly mirroring the precise spand and even surface tension of the original components in Image 1, with zero added wrinkles, creases, folds, or indentations. Isolated on a solid #FFFFFF pure white background, high-key lighting, minimal soft contact shadows under the object, no grey tones. Strictly forbid any texture bleed, environmental mapping, or background pattern from Image 2.
```

## 3. AZ Change Colour of Chair (stain)

`az-change-colour-of-chair` · *"Changes colour of chair (bets)"* · 1 node

**API:** `nano-banana-pro` (Gemini `gemini-3-pro-image-preview`, directly, **without a mask**).
Image 1 = the chair, Image 2 = the stain sample. Both are sent as files to the same exposed
`image` input: the API has `max_images: 4`, so the primary input takes several images, and
the order determines which one is "Image 1" **(interpretation)**.

| Parameter | Binding |
|---|---|
| `image` | **Expose** `image` |
| `temperature` | `0.1` |
| `top_k` / `top_p` | `40` / `0.85` |
| `image_size` / `aspect_ratio` | `1K` / `1:1` |
| `safety_filter_level` | Default |
| `negative_prompt`, `max_output_tokens` | Omit |

**Prompt** (Fixed, verbatim):

```text
A photorealistic product photograph of the specific chair from Image 1, demanding absolute, form-deviation-free geometric and structural lock. Crucially, strictly maintain the exact spatial relationship between wood and fabric; do not add, remove, or hallucinate any new wooden borders, frames, or panels that change the existing upholstery edge-work. If fabric extends fully to the edge in Image 1, it must remain fabric-to-edge in the output. Perform a surgical, procedural material replacement exclusively on the entire existing wooden surface area. This new stained wood finish must be procedurally derived from the specific color, texture, and grain characteristics strictly from Image 2. Maintain an absolute and literal chromatic lock, where the wood's specific hue, saturation, value, and precise color temperature must be procedurally replicated from the sample in Image 2. The upholstery must remain completely unchanged from Image 1. The new finish must wrap naturally around the chair's form with appropriate volumetric lighting and shadows. Isolated on a solid #FFFFFF pure white background, high-key lighting, minimal soft contact shadows under the object, no grey tones.
```

## 4. AZ Change Colour of Chair without Fabric

`az-change-colour-of-chair-without-fabric` · 1 node

Same setup as 3, but for chairs **without fabric**: the material is changed on the whole chair, not
just on the wooden parts. The only difference in the parameters: `safety_filter_level` is **Expose**
(default `BLOCK_ONLY_HIGH`), so the caller can change it.

**Prompt** (Fixed, verbatim):

```text
A photorealistic product photograph of the specific chair from Image 1, demanding absolute, form-deviation-free geometric and structural lock. Perform a surgical, procedural material replacement across the entire surface area and structure of the chair. This new finish must be procedurally derived from the specific color, texture, glossiness, and material characteristics (such as grain, sheen, or metallic finish) strictly from the sample in Image 2. Maintain an absolute and literal chromatic lock, where the material's specific hue, saturation, value, and precise color temperature must be procedurally replicated from the reference in Image 2. The new material must wrap naturally around the chair's three-dimensional form with appropriate volumetric lighting, specular highlights, and shadows that match the chair's geometry. Isolated on a solid #FFFFFF pure white background, high-key lighting, minimal soft contact shadows under the object, no grey tones.
```

---

## Learnings

1. **Mask + inpainting for fabric, free editing for stain.** The fabric is swapped in a bounded area, and
   the mask guarantees that wood and legs are not touched. The stain covers all the wood, so there a
   prompt that locks the fabric is enough ("The upholstery must remain completely unchanged").
2. **The prompt style is "lock everything, change one thing".** All three prompts start with a strong
   geometry lock (*form-deviation-free geometric … lock*), define exactly what is to be changed,
   demand a *chromatic lock* against the sample and end with the same studio background (#FFFFFF,
   high-key). The stain prompt also has a rule against invented wooden edges, an observed failure source.
3. **Low temperature** (0.1–0.3) for reproduction. Creativity is not the goal.
4. **The mask as its own flow with a quality check.** Splitting into two pipelines means a
   mask can be reviewed (`check_mask`, max 7 px drift) and reused for many fabrics.
5. **The production prompts exist only here.** According to Andreas (2026-09-29) the site's prompts are the
   current ones. `customers/az-design/eval/prompts.yaml` was more work in progress and has not been
   synced.
