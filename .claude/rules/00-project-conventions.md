# Project Conventions

## Before Making Changes

Before proposing changes or writing code:

1. **Restore context (new session)** — If this is a new conversation and **SESSION.md** exists in the repo root, read it first to restore focus, phase, and next steps. Then read CLAUDE.md "Active Context" if needed.
2. **Review codebase structure** — Understand how the repo is organized (see CLAUDE.md for this project's architecture).
3. **Read relevant READMEs** — At least root `README.md`; read area-specific READMEs when working in those parts of the codebase.

This ensures continuity between sessions and that changes fit existing patterns and conventions.

## Language

- **All code** (variable names, functions, docstrings, log messages) must be in **English**.
- **All comments** must be in **English**.
- User-facing docs (e.g. README) can follow the project (Swedish or English as used in the repo).

## Building scripts / pipeline nodes (apiai.me)

**Before building any apiai.me script, read `guidelines/SCRIPT_GUIDELINES.md`** — the full
checklist (runtime contract, the `PARAM_DEFS` golden rule, available libraries, output
format, local CLI). **For evals, read `guidelines/EVAL_GUIDELINES.md`** (how eval profiles +
the result schema/API work; per-customer eval config lives in `customers/<name>/eval/`).
**For writing/adjusting model prompts, read `guidelines/PROMPT_GUIDELINES.md`; for choosing which
model to use, `guidelines/MODEL_SELECTION_GUIDELINES.md`.** In short:

Scripts/nodes here are **productized and resold by apiai.me** — so build them **generic and
reusable, even by customers.** Zero references to a specific customer (e.g. carpx) or use
case (e.g. "car", "studio") in the code, script **name**, param **descriptions**, or
**default prompt**. The specific use is supplied by the **caller at runtime** (params,
prompt text, pipeline wiring). Generic name (`nb_pro_compose`, not `nb_pro_studio`), generic
params ("subject" / "reference"), neutral defaults. Model on the proven `nb_pro_inpaint.py`.

**Keep `SCRIPT_GUIDELINES.md` a living document.** Whenever a review (e.g. Claude-in-apiai.me),
a live test, or a bug surfaces a *generalizable* lesson, fold it back into the guidelines so
every future node inherits it — the same compounding habit as recording bug lessons. Only
the general rule goes in; the script-specific detail stays in the code/commit.

## Experimental Scripts — Never Inline

**CRITICAL:** When developing or testing scripts, **NEVER run Python inline** in the conversation.
Inline code disappears when context is compressed, making it impossible to reproduce or continue work.

**Always:**
1. **Save to `scratch/` folder** — Each pipeline/project should have a `scratch/` subfolder for
   work-in-progress scripts (e.g., `customers/heja/pipeline/scratch/analyze_quality.py`)
2. **Run from file** — Execute with `python3 scratch/script_name.py` instead of heredocs
3. **Log in SESSION.md** — Document what scratch scripts exist and their purpose
4. **Clean up when done** — Move useful scripts to proper locations, delete obsolete ones

Example structure:
```
customers/heja/pipeline/
├── scratch/
│   ├── analyze_quality.py      # Current: testing flatness metrics
│   └── compare_routing.py      # Current: validating routing logic
├── run_pipeline_v2.py
└── ...
```

This ensures experimental work survives context compression and can be resumed in new sessions.

## Scratch Cleanup

**When to clean the `scratch/` folder:**

| Tillfälle | Åtgärd |
|-----------|--------|
| **After deploy to prod** | Delete scripts for that feature |
| **New session/feature** | Remove old scripts that are no longer needed |
| **>10 scripts** | Clean out the oldest/obsolete ones |

**Clean in the Cleanup phase** (step 8 in workflow):
- Keep scripts that can be reused (e.g., eval scripts, test harnesses)
- Delete one-off tests that didn't work out
- Move generally useful scripts to proper locations

## Large Files — Never Bash Grep

**CRITICAL:** Eval-rapporter (`steps.html`) kan bli **>5 MB** eftersom bilder bäddas in som base64.
Att köra `grep` via Bash på dessa filer **fryser terminalen** — output är för stor.

**Använd istället:**
- `Read`-verktyget med `limit` parameter
- `Grep`-verktyget med `head_limit` parameter

```bash
# FRYSER TERMINALEN
grep -A 30 "pattern" out/steps.html | head -50

# FUNGERAR
Grep tool: pattern="...", path="out/steps.html", head_limit=50
Read tool: file_path="out/steps.html", limit=100
```

**Tumregel:** Alla filer i `out/`-mappar kan vara stora. Använd aldrig bash grep/cat/head på dem
