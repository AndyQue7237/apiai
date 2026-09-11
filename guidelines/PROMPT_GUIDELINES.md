# Prompt guidelines (generative image / edit models)

How to write and adjust prompts for the generative models in our pipelines. Generic — applies to
any subject/task. Keep this doc short too.

## Principles

1. **Short & concise wins.** Complex prompts are harder to diagnose — when the output is wrong you
   can't tell *which* clause caused it or what to adjust. Every added sentence is a new way to
   over-steer. Start minimal; add only what a test proves necessary.

2. **Don't over-tune for the current problem.** Fixing problem X tends to over-weight the fix so it
   solves X but creates Y and Z, and the fix becomes too dominant. The prompt must stay **general
   and balanced**. After any change, ask *"what might this now break?"* and check the general case,
   not just the input you were fixing.

3. **Prefer "preserve what's natural" over specifying the value.** Naming a property in detail makes
   the model exaggerate it. Ask it to *keep the natural look* of an attribute rather than dictating a
   value — e.g. "keep the subject's natural finish/reflectivity", not "make it glossy"; "keep the
   windows' natural appearance", not "tint the windows" (which yields *unnaturally* tinted windows).

4. **Structure for the model, not for prose.** Imperative voice, one idea per line/bullet,
   **priority-ordered** (put the most common failure first). Edit models read the whole prompt at
   once — they don't execute "first X, then Y", so sequencing words add length without effect.

5. **No contradictions.** Don't say "keep the subject 100% unchanged" and then instruct edits to it.
   Scope the "keep" to identity attributes (shape, geometry, text, colour, finish) and state the
   allowed edits separately.

6. **Positive instructions where you can**; explicit "do not change X" is fine — and best — for
   identity attributes you must protect.

## Process

- **Human-eyeball-test every prompt change** on a *spread* of inputs (easy + hard + the known
  failure cases), never only the case you were fixing — cross-effects are non-obvious. Simpler
  usually wins; an eval is necessary but not sufficient (it can miss real regressions).
- **Version prompts.** The current best prompt is pinned with the winning config (`WINNER.md`). A new
  prompt is a **challenger**: test it before it replaces the winner; log what changed and why.

See also: [MODEL_SELECTION_GUIDELINES.md](MODEL_SELECTION_GUIDELINES.md),
[../evaluator/EVAL_GUIDELINES.md](../evaluator/EVAL_GUIDELINES.md).
