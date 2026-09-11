# AZ Design - Chair Variant Evaluation

## Customer
Furniture manufacturer generating product variants for their catalog.

## Use Case
Generate chair variants with different wood stains (bets) and fabrics.

**Scale:** 2 chairs x 10 bets x 9 fabrics = **180 variants**

## Pipelines

See **`prompts.yaml`** for full prompts and evaluation criteria.

### 1. Bets (Wood Stain)
Changes the wood color/stain of the chair.

**Input:** Base chair + Wood stain sample
**Script:** `eval_bets.py`

### 2. Fabric (Upholstery)
Changes the seat cushion and backrest fabric.

**Input:** Base chair + Fabric sample
**Script:** `eval_fabric.py`

## Test Data

```
/Documents/APIAIme/AZ Design/
├── Chairs/
│   ├── solid_chair.jpg      # Base chair 1
│   └── black_chair.jpg      # Base chair 2
├── Bets/                    # 10 wood stain samples
│   ├── bets_blackstain.jpeg
│   ├── bets_burgundy.jpeg
│   ├── bets_yellowstain.jpeg
│   └── ...
└── Fabric/                  # 9 fabric samples
    ├── fabcric_dolaro18.jpeg
    ├── fabcric_lars27.jpeg
    └── ...
```

## Evaluation Status

| Test | Status | Success Rate | Avg Rating |
|------|--------|--------------|------------|
| Bets (10 colors) | Done | 10/10 (100%) | TBD |
| Fabric (9 types) | Pending | - | - |

## Notes

- **API issue discovered:** apiai.me pipeline only reads first image
- **Workaround:** Direct Gemini API call with two images works
- **Model:** nano-banana-pro-preview (Gemini 2.0)
- **Output:** 1024x1024 images
