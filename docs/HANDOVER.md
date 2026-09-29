<!-- HANDOVER — handover from a carpx session on 2026-09-29: why docs/ exists, what was found and where the work stands. Read first. -->

# Handover: documenting apiai ahead of a new product

**Written 2026-09-29** from a session that was accidentally run in the carpx folder (session
`275ff0b0`, 11:15–11:28). None of the below was saved anywhere else.

## The assignment (Andreas, verbatim in substance)

Andreas and the developer are parting ways. **The developer keeps the code and the IP**; Andreas
is building a new product, different and more tailored for content, but on the same principle:
chaining models and scripts. The backend will be missing.

- **Step 1:** document as much as possible of the scripts, models and admin.
- **Step 2:** plan the new product. It does not exist yet.

The work starts with **Explore** here in the apiai repo.

**The boundary we drew:** document **principles, decisions and measurements** (model choices and why,
rejected approaches with evidence, prompt strategies, costs, the logic of the chains). That is both
unproblematic and more valuable for a new product with a different layout than a transcript of his
implementation. If anything is unclear: check with him first.

**Exception: the scripts (decision by Andreas 2026-09-29).** Most of the Python scripts/nodes
were built by Andreas himself, locally in this repo before they were published on the site. **All** scripts
in the export may be saved **verbatim with full source code**, not just as principles. What
the developer keeps is **the platform code in his git repo** (backend, admin, the site), which
Andreas does not have access to. The boundary above applies to that code, not to the scripts.

## Andreas' answers to four questions

1. **When does access to apiai.me end?** No date set, but do the work now anyway.
2. **Is there an export?** Yes, of tools and scripts, just exported. Placed in
   **`docs/export/`**. There is also public documentation at https://apiai.me/docs, which
   is summarized in [`public-docs-summary.md`](public-docs-summary.md).
3. **Where is the crawler?** In `~/projects/tools/mockups/` (see below). **The logged-in
   admin part matters most.**
4. **What is the new product?** It does not exist yet.

**Unanswered when the session ended:** *"Finns två inloggade delar. 1 som vanlig user.
2 apiai/admin (separat inlogg)."* ("There are two logged-in parts. 1 as a regular user.
2 apiai/admin (separate login).") So both need to be crawled, each with its own login.

## What already exists

| Repo | Contents |
|---|---|
| **`apiai/`** (this one) | `guidelines/`: 1,002 lines in five documents (SCRIPT, PIPELINE, PROMPT, MODEL_SELECTION, EVAL) · `customers/` az-design, heja, shl · 21 Python nodes in `scripts/` |
| **`tools/`** | `evaluator/` (batch eval), `image-tools/`, three carpx pipelines, `mockups/apiai/` with a dashboard mockup |
| **`carpx/`** | `APIAI_FLOWS.md` (361 lines), `STUDIO_PIPELINE.md`, WINNER files, eval harnesses |

All three are on Andreas' account (`AndyQue7237`). What disappears is **the platform behind
apiai.me**, not the repos.

**The task is therefore mainly to consolidate and make things portable, not to write from scratch.**
`carpx/APIAI_FLOWS.md` is the template: *"written from the running code, not from memory"*, with
the prompts verbatim and the parameters exact.

**The crawler:** `tools/mockups/apiai/download.py`, written by Andreas. It has `--login` for
authenticated pages, sanitizes API keys and removes auth redirects so the page works
locally. It is the tool for the admin part. `dashboard-mockup/` is an earlier download,
and it was not established whether it is the admin or the public page.

## Prioritization: by what disappears, not by importance

What lives in the repos can be documented at any time. What exists only **inside the
platform** goes first:

1. **The flow definitions**: nodes, order, parameters. `APIAI_FLOWS.md` covers carpx's four
   flows. **Az-design, heja and shl have no equivalent.**
2. **Which models are connected** and under which names.
3. **The node contract**: how a script becomes a node.
4. **Actual costs** per model (came in the `X-Cost` header).
5. **Admin**: how a flow is actually built. Both the user part and `apiai/admin`.

## Next steps

1. Andreas places the export in `docs/export/`. **Check that it contains no keys before committing.**
2. Read the export and `public-docs-summary.md`, and compare with `guidelines/` and `scripts/`:
   what is already covered, what is missing?
3. Crawl both logged-in parts with `download.py --login`.
4. Propose a structure for `docs/` and write a Feature Brief for the documentation work.
