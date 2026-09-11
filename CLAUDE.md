# apiai — project memory (for AI agents)

Scripts, pipelines, and evals for **apiai.me** — the image/vision processing platform.

## Before making changes

1. **Read the guidelines** in `guidelines/`:
   - `SCRIPT_GUIDELINES.md` — building a single node
   - `PIPELINE_GUIDELINES.md` — assembling nodes into a pipeline (includes WINNER.md template)
   - `PROMPT_GUIDELINES.md` — writing model prompts
   - `MODEL_SELECTION_GUIDELINES.md` — choosing which model to use
   - `EVAL_GUIDELINES.md` — measuring if it works

2. **Check the customer folder** if working on a specific customer:
   - `customers/<name>/pipeline/WINNER.md` — what runs in production
   - `customers/<name>/eval/` — the eval harness and test data

## Structure

```
apiai/
├── scripts/                    # Generic, reusable scripts (nodes for apiai.me)
├── guidelines/                 # How to build scripts, pipelines, prompts, evals
└── customers/                  # Per-customer pipelines and evals
    ├── az-design/eval/
    ├── heja/
    │   ├── pipeline/           # Team logo pipeline (WINNER.md here)
    │   └── eval/
    └── shl/eval/
```

## Active context

### Heja team-logo pipeline (2026-09-08)

**Status:** v2 pipeline complete, 10/10 logos passing.

**Key files:**
- `customers/heja/pipeline/WINNER.md` — the champion config + learnings
- `customers/heja/pipeline/run_pipeline_v2.py` — the pipeline
- `customers/heja/pipeline/run_all.py` — batch runner + HTML report

**Recent changes:**
- Gradient-fix in check_quality (Cantagalo now correctly flagged)
- GPT-2 real transparency (background="transparent" + output_format="png")
- Real-ESRGAN via Replicate (avoids apiai.me rate limits)

### AZ Design fabric-swap (2026-06-09)

**Status:** Eval scripts updated for Google Drive structure. Testat Pedrali (87% PASS).

See `customers/az-design/eval/README.md`.

## Learnings (generalizable rules)

These apply to ALL pipelines. Discovered through heja, carpx, az-design work.

1. **AI only when needed** — test first (quality routing). Skip if already good.
2. **Fallbacks always** — models go down (Grounding DINO → Florence-2).
3. **Generative models flatten to RGB** — can't see prior transparency.
4. **Quality needs multiple dimensions** — MP + flatness + gradient.
5. **Direct API calls avoid bottlenecks** — OpenAI/Replicate direct, not via apiai.me.
6. **Simpler prompts win** — three sentences beat six numbered rules.
7. **Best run is no run** — transparent_skip preserves original integrity.

## Language

- **All code** (variables, functions, logs) in **English**
- **All comments** in **English**
- User docs can be Swedish where appropriate
