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
