# Pipeline Guidelines — building an apiai.me pipeline node-by-node

How we **build and prove a whole pipeline** (a multi-step apiai.me flow). Sibling to
`../apiai-tools/SCRIPT_GUIDELINES.md` (a single node) and `../evaluator/EVAL_GUIDELINES.md`
(the scoring). This file is the **process** — the reusable method for taking a pipeline from
idea to a productionised flow on apiai.me.

**Why this exists:** a pipeline is a DAG of nodes. The old mistake was to build the *whole*
pipeline and then eval the end result — when it's wrong you can't tell *which* node failed.
The rule now: **prove one node at a time.**

---

## The three layers (don't mix them)

| Layer | What it is | Where it lives |
|-------|-----------|----------------|
| **A node** | one generic, reusable, resellable step | `apiai-tools/scripts/` (+ SCRIPT_GUIDELINES) |
| **The eval** | the per-use-case judge rubric + harness | `evaluator/customers/<name>/` (+ EVAL_GUIDELINES) |
| **A pipeline** | the use-case assembly of nodes | `pipelines/<name>/` (this file) |

A single node is generic (no customer/use-case refs — see SCRIPT_GUIDELINES). A **pipeline is
use-case specific** — it chains generic nodes for a concrete outcome. Keep them apart.

## Creating or modifying scripts during pipeline work

When fixing a pipeline bug or adding a feature, you may need to **create a new script** or
**modify an existing one**. This is where mistakes happen — you're focused on the pipeline
and skip the script workflow.

**Rule: Always follow SCRIPT_GUIDELINES, even in "pipeline mode".**

Before deploying a new or modified script:
1. **Description** — write the apiai.me description (what it does, in English)
2. **Packages** — list required Python packages for the platform
3. **Local test** — run on test data, verify it works
4. **Claude review** — upload to apiai.me and get Claude review feedback
5. **Live test** — test as API on the site

Don't skip steps because "it's just a quick fix". Quick fixes that skip review cause regressions.

## Any report a pipeline produces self-documents its settings

A step-by-step run report is evidence, and evidence you cannot reproduce from is worthless six
weeks later. The rules live in `../evaluator/EVAL_GUIDELINES.md` and apply here too: render a
settings box on every tab showing **the full parameter surface** — including the knobs left at
their API default, printed as `null`, so it is obvious which ones are still untuned — plus the
**verbatim prompts**, collapsible. Reference: `heja-team-logo/run_all.py`.

## Folder layout for a pipeline

```
pipelines/
  PIPELINE_GUIDELINES.md        ← this method
  <name>/                       ← one pipeline (e.g. carpx-studio)
    PLAN.md                     ← the node map (the DAG) + live status
    nodes/                      ← per-node prototype scripts (local dev)
    out/                        ← saved intermediate outputs (node N → node N+1)
```

## Step −1: read the RIGHT guidelines — and the customer's EXISTING method

Before anything else, read the three method docs — this file, `PROMPT_GUIDELINES.md`,
`MODEL_SELECTION_GUIDELINES.md` — **and `../evaluator/EVAL_GUIDELINES.md`**. Reading half of
them produces work that looks right and violates the method.

**Then read what that customer already has.** A customer with a proven pipeline has a proven
*method* too: `evaluator/customers/<name>/` holds their eval harness, their `eval_set.json`
(facit shape), and their `<name>_eval_profile.md` (rubric + weights). **Mirror it — don't invent
a second convention next to it.** A new pipeline for an existing customer reuses their harness
shape, their report layout, their facit format and their folder names; only the *content*
changes. Two half-conventions in one customer folder is worse than either one alone.

## Step 0: the eval set comes FIRST

Before building any node, the human curates an **eval set** — a small, representative set of
inputs (covering the real variety: angles, colours, edge cases) plus a **facit** (expected
outcome / metadata) and the **pass bar**. This is the *approval contract*: it's how you know a
node is done, objectively, instead of eyeballing one lucky sample.

- Every node is run on the **whole eval set**; "done" = it clears the bar on the set. One image
  passing ≠ a proven node.
- **Per-node eval differs by node:** intermediate nodes (segment, mask cleanup) → visual approval
  or an autocheck node; the final node → the AI-judge rubric.
- The eval set + facit live with the eval harness in `evaluator/customers/<name>/` (reuse an
  existing one where the inputs are the same).

## The core rule: build node-by-node, save between nodes

1. **A pipeline = an ordered DAG of nodes.** Write the map first in `PLAN.md`: for each node —
   purpose, model/lib, **input**, **output**, and its **eval criterion** (how you know it's good).
2. **Each node's output is saved to `out/` and becomes the next node's input.** Every stage is
   then inspectable and the chain is resumable — you never re-run a proven node to test the next.
3. **Prove each node before moving on — and the HUMAN approves it before the next starts.**
   Run the node on the eval set, look at its output against its criterion, iterate *that node*
   until it's solid, then **present it and WAIT for the human's approval**. Do not chain ahead
   or start the next node until they say go. A weak node poisons everything downstream — catch
   it (and get a human sign-off) here, not at the end.
4. **Only when every node chains cleanly** do you run the **full-pipeline eval** (the existing
   `evaluator/customers/<name>/` harness) end-to-end.

## Prototype locally, productionise on apiai.me

- **Claude prototypes each node locally** (calls the model/library directly — e.g. Replicate,
  Gemini — via API access the human provides) and assembles the chain in `pipelines/<name>/`.
  Fast to iterate, everything version-controlled, nothing touches production.
- **The human productionises** the *proven* flow in the apiai.me backoffice (wires the Servers/
  Scripts/Flow) once the local chain works. Build only what's proven.
- When a node's prototype script is **generic + proven**, promote it to `apiai-tools/scripts/`
  (following SCRIPT_GUIDELINES) so it becomes a reusable, resellable node. The version in
  `pipelines/<name>/nodes/` is the prototyping stage; the promoted one is the product.

## The loop, per pipeline

1. **Curate the eval set** (Step 0) — representative inputs + facit + pass bar.
2. Agree the node map in `PLAN.md`.
3. For each node, in order: prototype → save output to `out/` → eval the node **on the eval set**
   → bounce it → advance only when solid.
4. Chain all nodes end-to-end → run the full eval.
5. Productionise on apiai.me; promote generic nodes to `apiai-tools/scripts/`.
6. Keep `PLAN.md` live — mark each node's status as it's proven.

## Definition of a "done" node

- Runs on a real sample and meets its **eval criterion** in `PLAN.md`.
- Its output is saved in `out/` in the exact shape the next node consumes.
- If generic: written to SCRIPT_GUIDELINES standard and promotable to `apiai-tools/scripts/`.

---

## How apiai.me pipelines work

**CRITICAL:** apiai.me pipelines are **strictly linear** — not DAGs. Understanding this is
essential for designing pipelines correctly.

### Core constraints

1. **Linear execution** — nodes run in order: 1 → 2 → 3 → ... → N
2. **Condition is a separate node** — skip logic is NOT embedded in check nodes
3. **One check per decision** — you can't combine two check nodes (only the last one's output is available)
4. **End pipeline setting** — a node can terminate the pipeline early with `end_pipeline: true`

### Condition nodes

Skip logic is handled by **Condition nodes** which are separate from check nodes. A condition node
has 3 parameters:

| Parameter | Description |
|-----------|-------------|
| `Skip next` | Number of nodes to skip (X) |
| `When field` | The field to check (Y) |
| `Is value` | The value to match (Z) — `true` or `false` |

**Condition nodes count towards total node count!** A 14-node pipeline becomes 19 nodes when you
add 5 condition nodes.

```
Node 2: Check Quality        ← outputs has_high_quality
Node 3: Condition            ← skip 6 when has_high_quality = true
Node 4: GPT Image 2
...
```

The skip count is **relative** — "skip 6" means skip the next 6 nodes from current position.

### Designing multi-flow pipelines

Since pipelines are linear, multiple "flows" must be laid out sequentially:

```
FLOW A (low quality):     1 → 2 → 3 → 4 → 5 → 6 → 7 [END]
FLOW B (high quality):    1 → 2 → [skip to 8] → 8 → 9 → ... → 14
```

**Pattern: Use `end_pipeline` to terminate Flow A early, so Flow B nodes don't run.**

### Check node limitations

**You cannot chain check nodes and combine their outputs.** Each check node outputs a field,
but only the MOST RECENT check's field is available for skip logic.

**Wrong:**
```
2. Check Quality (outputs has_high_quality)
3. Check Transparency (outputs has_transparency)
   Skip if: has_high_quality AND has_transparency  ← WON'T WORK
```

**Right:** Build a combined check script if you need multiple conditions:
```
2. Check Quality + Transparency (outputs should_skip_gpt2)
   Skip if: should_skip_gpt2 = true
```

Or design the flow so each check handles its own skip independently.

### Common patterns

| Pattern | Implementation |
|---------|----------------|
| Two-flow pipeline | Flow A ends with `end_pipeline: true`, Flow B continues after |
| Quality routing | Check Quality → skip N nodes if high quality |
| Resolution loop | Check Res → Upscale 4x → Check Res → Upscale 2x (with skips) |
| Edge case handling | Check Transparency → skip Remove Solid BG if already transparent |

### Example: Heja Team Logo Pipeline (19 nodes)

With condition nodes as separate steps:

```
LOW QUALITY FLOW (nod 1-9):
1. Detect & Crop
2. Check Quality
3. Condition (skip 6 when has_high_quality=true)
4. GPT2
5. Color Correction
6. Check Resolution
7. Condition (skip 1 when is_high_resolution=true)
8. Upscale 4x
9. Transparent Crop [END PIPELINE]

HIGH QUALITY FLOW (nod 10-19):
10. Check Transparency
11. Condition (skip 1 when has_transparency=true)
12. Remove Solid Background
13. Check Resolution
14. Condition (skip 4 when is_high_resolution=true)
15. Upscale 4x
16. Check Resolution
17. Condition (skip 1 when is_high_resolution=true)
18. Upscale 2x
19. Transparent Crop
```

Condition summary:
| Node | Skip | When field | Is value | Destination |
|------|------|------------|----------|-------------|
| 3 | 6 | `has_high_quality` | `true` | Node 10 |
| 7 | 1 | `is_high_resolution` | `true` | Node 9 |
| 9 | — | — | — | END PIPELINE |
| 11 | 1 | `has_transparency` | `true` | Node 13 |
| 14 | 4 | `is_high_resolution` | `true` | Node 19 |
| 17 | 1 | `is_high_resolution` | `true` | Node 19 |

### Pipeline setup file

For complex pipelines, create an `APIAI_SETUP.md` in the pipeline folder with:
- Visual flow diagram (ASCII art showing both flows)
- Node-by-node parameter tables
- Skip conditions with node numbers and counts
- End pipeline flags
- Scripts and requirements list
- Test checklist

See `customers/heja/pipeline/APIAI_SETUP.md` for a complete reference.

---

## Evaluating a pipeline on apiai.me

Pipeline evaluation has **three distinct phases** — don't skip ahead:

### Phase 1: Test each script individually

Before wiring the pipeline, upload and test each script as a standalone API:

1. Upload script to apiai.me
2. Claude-in-apiai.me reviews and gives feedback
3. Create API for the script
4. Test with a few sample images
5. Verify output is correct

**Only proceed when ALL scripts pass individually.**

### Phase 2: Set up the pipeline

Before wiring on apiai.me, **Claude creates an `APIAI_SETUP.md`** in the pipeline folder with:
- Visual flow diagram (ASCII art)
- Node-by-node tables with ALL parameters
- Skip conditions per node
- Scripts and requirements list

Then wire the scripts together in apiai.me:

1. Create the flow with correct node order
2. Configure parameters per node (follow `APIAI_SETUP.md` exactly)
3. Set up skip conditions / routing
4. Wire `image_reference` params to "From Original" where needed

### Phase 3: Run through eval set

Run the complete pipeline on the full eval set:

1. Process all images in the eval set
2. Verify outputs meet criteria (resolution, quality, colors)
3. Check skip logic worked correctly (transparent images skipped GPT-2)
4. Document results in WINNER.md

**The pipeline is only "done" when Phase 3 passes on the full eval set.**

---

## WINNER.md — the canonical record of a proven pipeline

Every pipeline folder gets a **WINNER.md** when a champion is chosen. It is the **single source of
truth** for what runs in production — updated only on an explicit decision to change winners. Use
this structure:

```markdown
# WINNER — <short name of what won>

**Decided by <human> <date>** after <basis for decision>. Changes only on a new explicit decision.

## Evalset

Path to the test data. Number of items. How to run the full set.

## Configuration

| # | Node | Location | Parameters |
|---|------|----------|------------|
| 1 | ... | script/API | key params |

### Prompt (verbatim)

> The exact prompt text, word for word.

## Tests run

| Date | Tag | Set | Result | Notes |
|------|-----|-----|--------|-------|
| 2026-XX-XX | v2-final | 10 logos | 10/10 | First full pass |

What was tested, when, by whom, outcome. Link to report if applicable.

## Why it won

Analysis: what it solved, what it beat, measured differences.

## Known issues

Open problems, edge cases, things that need monitoring.

## Learnings

Generalizable conclusions — rules that apply beyond this specific pipeline:

1. **<Learning>** — explanation
2. ...

## Cost

Per-item cost, how measured, caveats.

## History

Previous winners with their configs (so a proven fallback is never lost).
Rejected approaches with brief reason (so nobody re-proposes them).
```

**Why this structure:**
- **Tests run** answers "what evidence supports this?" — without it a WINNER.md is a claim
- **Learnings** compound across projects — the same mistake shouldn't happen twice
- **History** preserves fallbacks and closed paths — a previous winner may become relevant again
- **Known issues** is honest about what's NOT solved — important for handover and future work
