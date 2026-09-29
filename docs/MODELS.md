<!-- MODELS — which models apiai.me had connected, how they were used and what we learned. Written 2026-09-29 from admin data; per-API details in models/CATALOG.md (generated). -->

# Models on apiai.me

Which models the platform had connected on 2026-09-29, which were actually used, and what
that teaches us for a new product.

- **Per-API details** (model ID, price, configuration, all parameters, AI context):
  [`models/CATALOG.md`](models/CATALOG.md), generated with `docs/tools/build_models_catalog.py`.
- **How to choose a model:** `guidelines/MODEL_SELECTION_GUIDELINES.md` (type first, ranking
  second, your own eval decides).
- **How a model is connected in the admin:** `ADMIN.md` sections 4–5.

---

## 1. Providers

| Provider | Connection | APIs | Used for |
|---|---|---|---|
| **Replicate** | `api_key`, catalog search + *Fetch Schema* | 24 | Background removal, upscaling, vectorization, segmentation, video, image generation |
| **Gemini** | `…/v1beta` | 11 | The Nano Banana family (image), Veo (video), Flash Lite (vision → text) |
| **OpenAI** | `…/v1` | 7 | GPT Image 1.5 / 2 (image editing), the GPT-4o family (vision → text) |
| **xAI** | `…/v1` | 1 | Grok 3 mini (text) |
| **Python (local)** | — | 44 | Our own scripts. Some call models themselves (see 3). |

Replicate provides the breadth: almost everything that isn't Gemini or OpenAI goes there, and
a new model is connected without code (search → *Fetch Schema* → the parameters are mapped
automatically).

---

## 2. What was actually used

Requests 2026-08-31 to 2026-09-29. Model APIs only; pipelines are counted separately.

| API | Model | Requests | Price/request |
|---|---|---|---|
| Nano Banana 2 | `gemini-3.1-flash-image-preview` | **4 896** | $0.05 |
| Gemini 3.1 Flash Lite Preview | `gemini-3.1-flash-lite-preview` | **1 180** | $0.04 |
| Real Esrgan Upscaler | `nightmareai/real-esrgan` | 81 | $0.0022 |
| OpenAI GPT Image 2 | `gpt-image-2` | 48 | $0.04 |
| Bria Remove Background | `bria/remove-background` | 18 | $0.02 |
| Nano Banana Pro | `gemini-3-pro-image-preview` | 14 | $0.15 |

**Conclusion:** two models accounted for almost all traffic: Nano Banana 2 (image) and Gemini
Flash Lite (vision → text). Of 43 model APIs, **23 had no requests at all** during the period.
The catalog is broad to showcase the platform; actual usage is narrow.

---

## 3. Models in the important flows

### Heja Team Emblem

| Step | Model | Via |
|---|---|---|
| Find and crop the logo | `lucataco/florence-2-large` | The `detect_and_crop` script (the Replicate library) |
| Remove background, enhance | `gpt-image-2` (quality medium, background transparent) | API `openai-gpt-image-2` |
| Crop the reference for color correction | `lucataco/florence-2-large` | The `correct_colors` script |
| Upscaling | `nightmareai/real-esrgan` (4× and 2×) | API `real-esrgan` |

Everything else in the flow is our own scripts without a model. See `flows/HEJA.md`.

### AZ Design

| Flow | Model | Via |
|---|---|---|
| AZ Change Fabric - Mask | `gemini-3-pro-image-preview` | API `nano-banana-pro-inpainting` (the `nb_pro_inpaint` script, calls Gemini directly) |
| AZ Change Colour of Chair (with/without fabric), Change Colour of Fabric | `gemini-3-pro-image-preview` | API `nano-banana-pro` |
| AZ Smooth mask … (Sam3), Smooth Mask Creator Fabric | `mattsays/sam3-image` → the `smooth_mask` script (→ `mask_checker`) | API `sam3-image` |

The AZ flows are documented in detail in `flows/AZ.md`.

### Models that scripts call directly

These don't appear as model APIs, because the call happens inside the script:

| Script | Model |
|---|---|
| `detect_and_crop`, `correct_colors` | `lucataco/florence-2-large` (Replicate, pinned version hash) |
| `Detect and Remove Background` | `adirik/grounding-dino` (Replicate, pinned version hash) |
| `nb_pro_inpaint`, `nb_pro_reference_image` | `gemini-3-pro-image-preview` (Gemini directly, `GEMINI_API_KEY`) |

A script that calls a model itself can do things an API can't: send a mask and a reference
image in the same request, choose the model version via hash, or have fallback logic.
**Downside:** the model doesn't show up in the catalog, and the cost isn't recorded per model.

---

## 4. Learnings

1. **The prompt belongs in the flow, not in the model.** No model API has a baked-in prompt;
   all prompts sit as a *Fixed* parameter on the node in the pipeline. The same model API is
   then reused by many flows. Exception: customer-specific APIs such as `Nano Banana pro - repholstring`.
2. **Provider cost was never recorded** (0 of 87 APIs). The customer price was set per API,
   but the margin is unknown. A new product should log the provider's actual cost per request
   from the start.
3. **AI context is valuable but unreliable.** The texts (44 APIs) contain real learnings
   about parameters and quirks, but are often AI-generated and contain errors. Example: for
   GPT Image 2 it says "$0.22 flat rate", but the price is $0.04. Use them as hints.
4. **The health check covers less than half of the model APIs.** 16 of 43 verified, 3 failed
   (Flux Fill Pro, runwayml gen-4.5, Grounding Dino), 22 never tested, 2 inactive. No video
   API was tested; a probe with real inference is expensive for video **(interpretation)**.
5. **Pinned model versions in scripts.** The scripts point to exact Replicate version hashes.
   That makes results reproducible, but upgrades have to be done by hand.
6. **Configuration errors survive.** `sam3-image` and `check-resolution` have
   `response_type: video` even though they return images, and `real-esrgan` has two
   parameters that belong to another tool. The platform tolerated it, but a new product should
   validate I/O types against the model's schema.
7. **Replicate for breadth, direct calls for what matters.** Heja calls GPT Image 2 and
   Real-ESRGAN directly in the local version to avoid apiai.me's queue
   (CLAUDE.md, learning 5). The platform's concurrency limit (8 total / 4 per user) is the
   bottleneck, not the providers.
