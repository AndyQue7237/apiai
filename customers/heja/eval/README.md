# Heja - Team Logo Processing

## Customer
Sports team management app requiring logo processing for merchandise.

## Use Case
Process team logos to be print-ready for merchandise (socks, shirts, etc).

**Scale:** Thousands of teams, continuous flow

## Pipeline

### team-logo-nb-pro
Full logo processing pipeline with intelligent fallback.

**Steps:**
1. Remove background (transparent PNG)
2. Smart crop (tight to content + margin)
3. Upscale with Gemini (native image generation)
4. Fallback to Flux-2-max if Gemini fails

**Input:** Team logo (any format, any background)
**Output:** 1280x1280 PNG, transparent background, centered

## Test Data

**Eval set (source of truth):**
```
/Users/andreasquensel/Library/CloudStorage/GoogleDrive-andreas@zebrolabs.com/Shared drives/Apiai.me/Customers/Heja/Content/Team Logos/
├── Cantagalo Logo.png
├── Chicago Blues FC.png
├── Hammarby IF.png
├── Kumla_Hockey_logo.svg.png
├── Trollbäckens GK.jpg
├── Tyresö FF.png
├── Warner.png
├── leopards.jpg
├── special_knivstais-hockey.jpg
├── team_usa.jpeg
└── manifest.json
```

Legacy location (may be stale):
```
/Documents/Happy Art Gallery/Team Merch/Team logos/
```

## Evaluation History

| Date | Pipeline | Success Rate | Avg Rating |
|------|----------|--------------|------------|
| 2024-03 | team-logo | 8/9 (89%) | 4.2 |
| 2024-03 | team-logo-nb-pro | 9/9 (100%) | 4.8 |
| 2024-03 | team-logo-vectorize | 9/9 (100%) | TBD |

## Key Learnings

1. **Ghost pixels:** Images from remove-bg have semi-transparent pixels (alpha 1-10) at edges. Fixed with alpha threshold in smart_crop.
2. **Gemini fallback:** Chicago Blues FC consistently fails with Gemini, works with Flux-2-max fallback.
3. **Aspect ratios:** smart_crop now supports multiple formats (square, 16:9, 4:5, etc).
4. **Quality routing — when GPT2 vs direct upscale (2026-09-04):**
   MP (megapixels) is the primary quality measure; hard edges (%) catches artifacts MP misses.
   - **MP > 1.0** → Upscale directly (high quality; hard edges = intentional vector graphics)
   - **MP < 0.09** → GPT2 (too small, needs reconstruction)
   - **MP 0.09–1.0 + hard edges > 20%** → GPT2 (borderline + artifacts)
   - **MP 0.09–1.0 + hard edges ≤ 20%** → Upscale directly (borderline but clean)

   Validated 10/10 on eval set. Technical implementation in `pipelines/heja-team-logo/PLAN.md`.

5. **BG removal routing — when script vs GPT2 (2026-09-04):**
   - **Already transparent?** → Skip bg removal entirely
   - **Different corner colors?** (distance > 50) → GPT2 (multi-color bg, e.g. esports templates)
   - **Same corner color?** → Script (flood-fill from edges)

   Edge case accepted: connected monogram letters (e.g. Trollbäckens GKT) may leave ~0.2%
   enclosed pixels. Deemed acceptable — wait for real customer feedback before adding
   complexity (e.g. Gemini Flash detection). YAGNI.

## Scripts

Eval runs with standard batch_evaluate.py:
```bash
python evaluator/batch_evaluate.py \
  --manifest /path/to/manifest.json \
  --api team-logo-nb-pro \
  --output ./results
```
