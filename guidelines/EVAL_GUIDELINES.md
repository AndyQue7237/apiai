# Eval Guidelines — apiai.me eval profiles

How the apiai.me **eval** system works: an AI judge scores a pipeline's output against a
**Profile** (rubric + weighted dimensions) and returns a score + verdict you can pull via
API. Sibling to `../apiai-tools/SCRIPT_GUIDELINES.md` (which covers the pipeline nodes). The
per-customer eval config (the actual rubric/dimensions) lives with that customer's harness in
`customers/<name>/`, **not** here — keep this file general.

**Always keep the running Profile as a text file** in `customers/<name>/` (e.g.
`<name>_eval_profile.md`) that mirrors the platform Profile fields — threshold, input slots,
goals, rubric, weighted dimensions, watches. The eval itself lives on eval.apiai.me, so this
file is the **version-controlled, copy-pasteable source of truth**: author/update it here, then
paste it into the tool. Never leave a profile only on the platform.

## What a Profile is (the setup)

A **Profile** is an eval config attached to one or more pipelines. Fields:

- **Profile name** + an **Enabled** toggle.
- **Pass threshold** (0–100 %): `score ≥ threshold → pass`; below → review / fail.
- **Input slots** — the watched pipeline's inputs; each gets a token (`{image_1}`, `{image_2}`, …).
  - **Original** = the output is judged *against* this input (a comparison anchor).
  - **context** = visible to the judge but not an anchor.
- **Rubric** — prose scoring rules that reference the input tokens. This is where you steer the
  judge (what to reward, what to penalise). **The most important field.**
- **Goals** (required) — one paragraph on what the eval measures.
- **Scoring dimensions** — named axes, each scored 0–100, each with a **weight**. The weighted
  average = the final `score`. (We skip the separate **Good/Bad criteria** fields — the rubric +
  dimensions already carry the spec; adding them just duplicates it.)
- **Watches** — the pipeline slug(s) this profile auto-scores. Empty = manual scoring only.

### Proposing a profile — deliver the WHOLE form, never just the parameters

When proposing an eval profile, hand over everything the form asks for, ready to paste:
**input slots** (which token is `Original`), **Goals**, the **Rubric prose**, and the **scoring
dimensions with a description AND a weight each**, plus the **pass threshold** and the arithmetic
that makes the decisive dimension decisive.

The named parameters — the `{image_1}`-style tokens — are what the rubric refers to, so they only
mean something *together with* the prose. A list of dimensions and weights without a rubric is not
a profile: the weights say how much each axis counts, the rubric is the only place that says what
a good and a bad output actually look like, and the judge reads the rubric, not the weights.
Half a proposal costs the user the hard half of the work (Andreas, 2026-08-31).

Say explicitly which parts are **calibration guesses** to revisit after the first run against real
outputs — normally the threshold and the rubric's exception clauses.

### Design lessons

- **Build the eval around the *actual failure mode*.** Weight the make-or-break dimension
  heavily and name the specific failure in the rubric, so a bad output can't pass on looks.
  (Car studio: weight `Car fidelity` ~0.5 and tell the judge *not to reward a changed/
  hallucinated vehicle*.)
- **Split a high-stakes *binary* check into its own dimension** — exact text (a license
  plate, a code), "is the logo present", etc. A blended "fidelity" score would only dent
  slightly for a wrong value and still pass; a separate dimension makes it **decisive** *and*
  **transparent** (you see *which* thing failed). Tune its weight + the pass threshold
  together so a failure on it drops below the bar (e.g. a 0.2-weight plate dimension + a 90 %
  threshold → a wrong plate scored 0 caps the total at 80 → fail).
- **Calibrate the rubric against real outputs.** The judge can over-penalise things that are
  actually fine. When you disagree with the judge, encode the exception explicitly in the
  rubric; iterate on disagreements, not in a vacuum. Two real examples from the carpx run:
  it flagged a *realistic car reflection* as a "duplicate" (→ "a realistic reflection is
  expected, reward it"), and it failed a *side-profile* car for a "missing" plate that the
  angle simply doesn't show (→ "if the angle shows no plate, that's fine; only penalise a
  fabricated or altered one"). Rule of thumb: **don't penalise a legitimately-absent element.**

## How scoring works

The judge (an image model, e.g. `gemini-2.5-flash-lite`) scores each **dimension** 0–100 from
the rubric + goals, comparing the output against the **Original** inputs. Weighted average →
`score` → `verdict` (pass / review / fail) vs the threshold. It's fast + cheap (~2–3 s,
~$0.02 per eval), so running it over a whole test set is fine.

## The API

Auth: header `X-API-Key: <APIAI_API_KEY>` (the normal apiai.me key — same as the pipelines).

`GET https://eval.apiai.me/v1/eval/results?limit=<N>&profile_id=<ID>` → recent scored results
for that profile:

```json
{ "count": N, "total": N, "results": [ /* result objects */ ] }
```

A **result** object:

| field | meaning |
|---|---|
| `id` | eval result id |
| `profile_id`, `profile_name` | which profile scored it |
| `workflow_slug` | the pipeline that produced the output |
| `score` | final weighted score, 0–100 |
| `dimension_scores` | `{ "<dimension>": 0–100, … }` — per-axis breakdown |
| `verdict` | `pass` / `review` / `fail` |
| `reasoning` | the judge's prose explanation (why this score) |
| `improvement_hints` | `[ "…", … ]` — actionable suggestions (great for tuning the pipeline) |
| `output_image_path` | the generated output (`/eval-uploads/…`) |
| `input_image_paths`, `input_slots` | the inputs (`{token, source_name, is_original, path, mime, …}`) |
| `evaluator`, `latency_ms`, `cost` | judge model + perf |
| `signals` | extra structured signals (may be empty) |
| `request_id`, `created_at` | use these to match a run to its result |

**Auto-scoring flow (watched pipelines):** run a generation through the pipeline, then poll
`/v1/eval/results?profile_id=<ID>` for the new result and match it on `request_id` /
`created_at`. A test harness = run each test input → poll → aggregate (pass-rate, mean per
dimension, flag fails, collect `improvement_hints`) → report.

## Local eval reports = tabs (one tab per method) — CONVENTION

When comparing pipeline methods/variants locally (not the apiai profile scoring), the report is
a single self-contained tabbed HTML — **one tab per eval/method**, tab = the filter you click.
Each tab shows Original | that method's output for every test image (before/after).

**Convention: a new eval / new method is ALWAYS a new tab — append it, never overwrite.**
Old tabs (and their frozen output images) stay so we can keep comparing methods over time; we
add tabs continuously as we try new ideas. This beats side-by-side columns (they get too wide
past 2–3 variants) and beats overwriting (you lose the earlier method's evidence).

Reference implementations: `pipelines/carpx-studio-depth/run_ab_studio.py` (A/B/C studio methods,
tabbed) and `carpx/eval/eval_exterior_studio.py` (that repo) (tab per run, prompt frozen per
tab). Freeze each method's outputs (copy to `*-<tag>.png`) so a later run can't clobber them, and
skip-if-done (reuse an existing frozen output) so re-runs only fill the gaps.

**Show the pipeline STEP BY STEP, not just before→after.** Each card should show the key
intermediate node outputs in sequence (e.g. original → cutout → studio → composite = the
model's input → final output), so a defect is traceable to the NODE that caused it: a wall
corner is the studio node; a missing roof rack is the mask node; a rewritten badge or a
matte-vs-gloss flip is the final generative (NB Pro) pass. Before→after alone tells you
something is wrong but not WHERE — step-by-step tells you which node to fix.

**Isolate ONE variable per eval.** Hold everything constant except the single thing under test,
so any difference in the output is caused by that thing alone. If a tab changes two things at
once (e.g. a different studio AND a different shadow), a win is un-attributable. Reference:
`pipelines/carpx-studio-depth/run_shadow_eval.py` (fixed studio + polish, only the shadow varies).

**Every tab self-documents its settings + prompt.** Render a small settings box at the top of
each tab showing exactly what was run — the constant settings, the variable under test, and the
full prompt(s) (collapsible). A tab you can't reproduce from is evidence you can't trust later.

**List ALL possible parameters, not just the ones you set.** In the settings box, show the model's
*entire* parameter schema (pull it from the authoritative source — the provider's model schema/API,
or the platform's curl example). Parameters you leave at the API default show as `null`. This turns
the box into the full knob-space, so it's obvious at a glance which single parameter is still
untuned and worth laborating with. Reference: `pipelines/carpx-studio-depth/run_model_test.py`.

**Consciously choose every parameter before running — never blind-run the defaults.** Read what each
parameter *does* (fetch its description/range/enum from the schema) and decide its value on purpose,
because a default can directly hurt the very thing under test (e.g. a matting `threshold` that
binarises soft alpha, or a `resolution` too low to keep thin structures like mirrors/rails/antennas).
Do this **before** spending the run, not after seeing a bad result. Give each model its **best-shot**
settings for a fair comparison (as with `quality=high` / full-precision toggles), and record the
chosen values in the settings box so the choice is auditable.

**For model-comparison evals, record price/run + latency (time) too.** Quality is not the only
axis a model choice turns on — cost per run and speed are decision parameters in their own right.
Measure wall-clock latency live per call; show price/run per model (from the provider's list price,
labelled approximate if the API doesn't return it). Put both in each model's settings box so the
trade-off (quality × price × time) is visible in one place. See
[../pipelines/MODEL_SELECTION_GUIDELINES.md](../pipelines/MODEL_SELECTION_GUIDELINES.md).

**Keep ONE canonical winner, in one file, that changes only on an explicit decision.** Maintain a
`WINNER.md` in the pipeline folder with the champion's full config (every setting + verbatim
prompts + date + why it won) and links to its **frozen** proof images (`winner-*.png`). Every new
eval is a challenger measured against it. The winner is replaced **only** when the user explicitly
decides a new one — never silently by a re-run — and the old config moves to a *History* section so
a proven setup is never lost. Reference: `pipelines/carpx-studio-depth/WINNER.md`.

**One output per input — N inputs = N rows — and re-runs fill only the gaps.** The default layout
is exactly one result per input per method: N test images → N rows, no duplicates. When a method
**fails or misbehaves on one input** (an error, or a bad output like a flipped subject), re-run
**only that one input, once** — skip-if-done keeps every other frozen result untouched, so you
never get two rows for the same image. (Running each input several times is a *separate*, opt-in
**variance spot-check**, not the default — don't multiply rows for it unless variance is the thing
under test.) Reference: `pipelines/carpx-studio-depth/run_model_test.py` (skip-if-done per frozen
`mt-<stem>-<method>-r0.png`).

**Always verify the eval-set when building a new eval.** Before running, confirm *which* images you
are about to test and how many, and that it's the **intended** set — ideally the **same set prior
methods were tested on**, so results are apples-to-apples and comparable to earlier evals. Print the
set (folder + count) at the start of the run and eyeball it; a silently wrong or truncated set
invalidates the comparison. When in doubt, list the set and confirm with the user before spending
API calls.

**Emit progress + ETA, and a heartbeat (~every 5 min).** A long eval must report how far it is and
how long remains, so a slow or hung run is caught early instead of after hours. Per completed call,
log `[done/total] … · elapsed · ETA` (ETA = elapsed/done × remaining — parallel-aware). Also run a
**heartbeat thread that prints ~every 5 minutes** (`done/total`, elapsed, ETA) so even a run whose
individual calls stall still shows a regular signal. Reference:
`pipelines/carpx-studio-depth/run_bg_test.py`.

**Know each provider's concurrency limit; parallelise per-provider.** API calls are I/O-bound, so a
thread pool parallelises them — but providers differ: some (e.g. Replicate) handle many concurrent
calls, others (e.g. apiai) return 429/503 on parallel requests and must run **serially**. Use a
**per-provider semaphore** (serial where required, parallel where allowed) plus a light retry with
backoff on transient 429/503/timeouts. Capture **actual** cost where the API returns it (apiai:
`x-cost` header; Replicate: `metrics.predict_time`; OpenAI: the `usage` tokens) rather than a
static estimate.
