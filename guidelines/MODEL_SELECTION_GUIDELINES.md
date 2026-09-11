# Model selection guidelines

How to choose the generative model for a task. Generic — applies to any pipeline node that calls a
model. Keep it short.

## The process

1. **Think about model TYPE first — highest leverage.** Match the *class* of model to the task's
   dominant constraint before looking at any ranking. The wrong type loses regardless of how highly
   it ranks. Common classes for image work:
   - **generate** (text→image, image-conditioned) — remakes the whole frame; maximal creativity,
     but rewrites fine detail (small text, exact geometry). Use when the subject may change.
   - **subject/identity-preserving edit** (instruction edit) — keeps the subject, changes what you
     ask. Use when the subject must stay exact (text, badges, geometry, finish).
   - **targeted inpaint** (mask-scoped) — changes only inside a mask, leaves the rest pixel-exact.
     Use when the edit region is well-defined and everything else must be untouched.

2. **Research the current best models — every time.** The catalog churns monthly; last month's pick
   may be superseded. Use leaderboards (e.g. an image-edit arena) to **source candidates**, but note
   they rank *general preference*, not your task-specific need — so **they source, they don't decide.**
   Top-of-leaderboard models are often the "change-more" class and can fail a preservation task.

3. **Eval the candidates against each other** on your own **stress-test inputs** (pick cases that
   exercise the known failure modes) + a scoring **rubric**. **Quick-test on Replicate** if a model
   isn't on the target platform. Run each model **multiple times per input** to also measure
   run-to-run **variance**, not just best-case quality. Include one "change-more" reference model so
   you *know* rather than assume that the preserving class wins. **Record price/run + latency
   alongside quality** — cost and speed are decision axes too; capture both so the quality × price ×
   time trade-off is visible. Also surface each model's *full* parameter schema (unused = null) so a
   tunable knob is easy to spot.

4. **Implement the winner** on the target platform if it isn't already there. Pin it (`WINNER.md`)
   with its full config; a later candidate is a challenger measured against it.

## Notes

- **Type-first, ranking-second, task-eval-decides.** In that order.
- A model that "changes less" is usually right for preservation-critical tasks — but it must still
  transform enough to do the job; verify both sides on real inputs.

See also: [PROMPT_GUIDELINES.md](PROMPT_GUIDELINES.md),
[../evaluator/EVAL_GUIDELINES.md](../evaluator/EVAL_GUIDELINES.md) (rubric + tabbed reports + the
one-canonical-winner convention).
