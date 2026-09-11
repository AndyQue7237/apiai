# apiai

Scripts, pipelines, and evals for **apiai.me** — the image/vision processing platform.

## Structure

```
apiai/
├── scripts/                    # Generic, reusable scripts (nodes for apiai.me)
├── guidelines/                 # How to build scripts, pipelines, prompts, evals
│   ├── SCRIPT_GUIDELINES.md
│   ├── PIPELINE_GUIDELINES.md
│   ├── PROMPT_GUIDELINES.md
│   ├── MODEL_SELECTION_GUIDELINES.md
│   └── EVAL_GUIDELINES.md
└── customers/                  # Per-customer pipelines and evals
    ├── az-design/
    │   └── eval/
    ├── heja/
    │   ├── pipeline/           # Team logo pipeline
    │   └── eval/
    └── shl/
        └── eval/
```

## Getting started

1. **Read the guidelines** before building anything:
   - `guidelines/SCRIPT_GUIDELINES.md` — building a single node
   - `guidelines/PIPELINE_GUIDELINES.md` — assembling nodes into a pipeline
   - `guidelines/EVAL_GUIDELINES.md` — measuring if it works

2. **Environment**:
   ```bash
   # API keys in .env
   APIAI_API_KEY=...
   OPENAI_API_KEY=...
   REPLICATE_API_TOKEN=...
   ```

3. **Run a pipeline** (example: heja team logos):
   ```bash
   cd customers/heja/pipeline
   python3 run_all.py --method v2 --tag test
   ```

## Principles

1. **AI only when needed** — test first, skip if the input is already good
2. **Fallbacks always** — models go down, have alternatives
3. **Generic scripts** — no customer/use-case refs in script code
4. **WINNER.md per pipeline** — the canonical record of what runs in production
