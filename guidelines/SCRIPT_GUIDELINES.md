# Script Guidelines — apiai.me pipeline nodes

The **rules** for writing a good apiai.me script (a pipeline node). This is the checklist
to follow every time. For the deep mechanics (Servers / APIs / Scripts / Flows, deployment,
patterns) see **`README.md`** — this file is the *what-good-looks-like*, not the manual.

**Reference implementation:** `scripts/nb_pro_inpaint.py` — live, proven, written to these
rules. Model new scripts on it.

---

## 1. Generic & reusable — no customer or use-case specifics

apiai.me **productizes and resells** these nodes, so a node must be usable by *any*
customer for *any* fitting use case. **Zero references** to a specific customer (e.g.
carpx) or use case (e.g. "car", "studio") in the code, the **script name**, the
**parameter descriptions**, or the **default prompt**. The specific use is supplied by the
**caller at runtime** (params, prompt text, pipeline wiring).

- **Name it simply + self-descriptively** — a user should understand what the node does
  from its **name alone**. Generic (no use-case), and ideally the **same name used on the
  site** (you *can* name it anything in the backoffice, but matching avoids confusion).
  E.g. `nb_pro_reference_image` (NB Pro + a reference-image input), not `nb_pro_studio`.
- Params/prompts talk about "subject" / "reference", not "car" / "background".
- **All user-facing text in English.** The script **name**, every **param description**, and
  the **API description** are shown to international customers — write them in **English**,
  never Swedish. (Code, comments and docstrings are already English per project conventions.)

## 2. Expose knobs as PARAMETERS, not fixed values

Anything a caller might reasonably want to change is a **parameter with a sensible
default**, never a hardcoded constant. Aspect ratio, size, temperature, prompt, model —
all params. Default to the common case; let the caller override.

## 3. The single-input rule (why extra images are params)

A node receives **one** body image — either from the previous pipeline step **or** as user
input, **never both**. If your node needs more than one image (e.g. a subject *and* a
reference), the extra image(s) come in as **base64 string parameters**, not as a second
body input. (This is exactly why `nb_pro_inpaint` takes its mask + reference as params, and
why a compose node takes its reference as a param.)

## 4. The runtime contract (`script_io`)

Scripts talk to the apiai.me runtime over stdin/stdout JSON via the `script_io` helper:

```
stdin:  {"image": "<base64>", "content_type": "image/png", "params": {...}}
stdout: {"image": "<base64>", "content_type": "image/png", ...extra root fields}
```

```python
from script_io import read_input, write_output, write_error   # provided by the runtime

body_bytes, content_type, params = read_input()   # the one body image + params
# ... work ...
write_output(png_bytes, "image/png")               # success
write_error("clear, user-facing message")          # failure
```

`script_io` isn't in this repo (the runtime provides it). Import it with a try/except
fallback so the script still runs locally (see rule 9).

## 5. Parameters — `PARAM_DEFS` spec (+ the golden rule)

Declare every param in a module-level `PARAM_DEFS` list; the admin "Scan Script" reads it.

```python
PARAM_DEFS = [
    {"name": "image_reference", "description": "...", "default_value": "", "required": True},
    {"name": "temperature",     "description": "0 = deterministic, max 1.", "default_value": "0.3"},
]
```

**🥇 Golden rule — `default_value` must be a plain string literal.** The scanner parses
`PARAM_DEFS` **statically** (it does *not* run the module), so it can only read literal
strings. A variable, function call, or f-string is **skipped — and often drops that
entry's `description` with it**.

```python
# ❌ won't scan (drops description too)
"default_value": DEFAULT_TEMP,          # variable
"default_value": str(DEFAULT_TEMP),     # function call
"default_value": f"{DEFAULT_TEMP}",     # f-string

# ✅ scans
"default_value": "0.3",
```

Want one source of truth for a constant? Keep the literal in `PARAM_DEFS`, and convert at
runtime: `float(params.get("temperature") or "0.3")`.

**Descriptions:** short (≤ ~200 chars), say *what it does* + *allowed values* (e.g.
"Output aspect ratio. Options: 1:1, 3:4, 4:3, 9:16, 16:9."). Plain **English**, user-benefit first, no jargon (never Swedish — see §1) — a user should
get what the knob does without knowing the internals.

**Evolving a live node — keep existing param names + defaults.** A node already in use has
callers and pipelines wired to its current param **names** and **default behaviour**. When you
extend or replace it, keep those names and defaults and add new capability as **optional**
params with safe defaults — renaming a param, dropping an accepted value, or changing a default
silently breaks live pipelines. (New optional params with off-by-default values are safe.)

**Reuse these standard descriptions verbatim** for the recurring NB Pro / Gemini params, so
every node reads the same. (The sampling three are written in plain "how varied/creative"
terms on purpose — avoid "temperature / top-k / nucleus sampling" jargon.)

| Param | default | Description (copy verbatim) |
|---|---|---|
| `temperature` | `0.3` | How creative the model gets — lower stays close to your inputs (consistent, safe), higher is more creative. Range 0-1; 0.3 is a good default. |
| `top_p` | `0.95` | How much variety the model allows in the result — lower is more predictable, higher is more varied. Range 0-1; leave at 0.95 unless you want more or less variation. |
| `top_k` | `64` | How many options the model weighs at each step — higher allows more variety, lower stays more focused. Range 1-64; the default suits most cases. |
| `aspect_ratio` | `1:1` | Output aspect ratio. Options: 1:1, 3:4, 4:3, 9:16, 16:9. |
| `image_size` | `1K` | Output resolution. Options: 1K, 2K, 4K. |
| `negative_prompt` | `` (empty) | Things to exclude. If set, appended to the prompt as an 'Avoid: ...' clause. |
| `safety_filter_level` | `BLOCK_ONLY_HIGH` | BLOCK_LOW_AND_ABOVE, BLOCK_MEDIUM_AND_ABOVE, BLOCK_ONLY_HIGH, BLOCK_NONE. Applied to all safety categories. |
| `max_output_tokens` | `` (empty) | Max output tokens (up to 32768). Leave empty to use the model default. |
| `model` | `gemini-3-pro-image-preview` | Gemini model name. Default is what NB Pro uses. Override to try new image-gen variants. |

## 6. Available libraries (apiai.me runtime)

Pre-installed — `import` freely: **`Pillow` (PIL), `numpy`, `opencv-python-headless`,
`scipy`, `scikit-image`, `cairosvg`, `replicate`** + the stdlib (`os`, `io`, `json`,
`base64`, `logging`, `urllib.request`, `urllib.error`, `ssl`, `argparse`, `tempfile`,
`pathlib`, …).

**⚠️ `requests` is NOT available.** Use `urllib.request` for HTTP (see how
`nb_pro_inpaint.py` calls Gemini with stdlib only). Anything outside the list must be
replaced with a stdlib equivalent or added by a developer.

**Server env vars:** `GEMINI_API_KEY`, `REPLICATE_API_TOKEN` (read via `os.environ`; never
hardcode a key).

**Always state a script's Requirements when you deliver it** — the pip packages to tick in
the site's script settings. That's every import that is **not** stdlib, **not** runtime-
provided (`script_io`), and **not** local-only (`dotenv`, used only by the CLI). Flag an
optional import wrapped in try/except (e.g. `certifi`) as "optional — safe to skip". Example
— a node that uses `PIL` + `urllib` (stdlib) for a Gemini call → **Requirements: `Pillow`**.

## 7. Output format (required for pipelines)

- Return the image on the **root**: `{"image": <b64>, "content_type": "image/png", ...}`.
- **Convert to RGBA before output** (`img.convert("RGBA")`).
- Put any extra fields (incl. **booleans for condition nodes**) **on the root** — **never**
  a nested `"metadata": {...}` object.

## 8. Backoffice API I/O config

When wiring the node's API: **Accepted Inputs** = Image (+ Text/JSON only if it takes
params); **Output Type** = **Image** (never Text/JSON for an image script — it breaks
pipelines).

**Always provide a user-facing API description on delivery** — the text users see when the
node is added as an API. Keep it **short, concrete, benefit-first**, in **plain English
with no jargon** (never Swedish — see §1; no "subject / compose / inpaint"): say *what it does for the user* + *when
to use this variant*. Example: *"Nano Banana Pro image generation with a reference image. Use
this when you need two image inputs — a main image plus a reference image that guides the
result (e.g. a background, scene, or style to follow)."*

## 9. Robustness & local testing

- **Fail fast, clearly — validate every param in one place:**
  - Parse **numeric** params up front (one parse step) and **clamp** to accepted ranges
    (e.g. `temperature` 0–1). A bad value must surface as a clean `write_error`, **never** an
    unhandled exception deep in the request build.
  - Decode **base64 image** params with a **specific** message per param (`"image_reference
    is not valid base64"`), not a generic "could not decode an image".
- **Preserve input alpha:** `.convert("RGBA")` image inputs so a cut-out (transparent
  subject/reference) stays a cut-out — don't silently flatten transparency unless you
  deliberately need to.
- **Small perf/debug:** skip PNG `optimize=True` on the pipeline path (CPU cost, negligible
  gain); `log.debug(...)` the key inputs/decisions — the prompt on AI-call nodes, and on a
  **deterministic** node the choices it made (e.g. final size, which branch/bound was taken).
  Set up `log = logging.getLogger(__name__)` even on non-AI nodes so production issues are
  traceable — a placement/geometry node that "landed wrong" is far easier to debug with a line.
- **Document intentional edge behaviour** in the docstring — silent clipping, truncation,
  off-canvas overflow, degenerate inputs. If a node deliberately does something surprising,
  say so, or a reviewer (or your future self) will flag it as a bug. State the *why*, not just
  the *what*.
- **Keep helpers at module level, not nested inside `process()`** — a nested closure can't be
  imported or unit-tested, and the smoke test (§10 / 07-verify) should be able to call small
  pure helpers (formatters, geometry, validators) directly.
- **Always ship a local CLI** so the script runs without the apiai.me runtime — the
  `if SCRIPT_IO_AVAILABLE and len(sys.argv) <= 1: main() else run_local_cli()` pattern.
  Load `.env` for local runs; the runtime sets env vars natively.

## 10. Evaluating a node — the default flow

Three gates, in order — the **node**, then the **platform**, then the **site**:

1. **Local test (Claude).** Run the node on its own via the local CLI — the node, **not** a
   pipeline. Verify a correct result, all params work, no crash. Only proceed if it works.
2. **apiai.me review (Claude-in-apiai.me).** Andreas uploads the script to apiai.me and asks
   the platform's Claude (which has all the apiai.me docs) for feedback — a platform-aware
   review. Address what it flags. **This IS the node's code review — skip the lifecycle's
   separate 05-review phase for nodes (no double review).**
   **Fold generalizable feedback back into these guidelines.** When a flag is a *general*
   lesson (a rule any future node should follow), add it to §1–§9 — not just fix this script;
   only the general rule goes in, the script-specific detail stays in the code/commit. Same
   living-document habit as the project conventions. (Ignore the reviewer's self-retracted or
   one-off points — only real, reusable lessons.)
3. **Live test on the site (Andreas).** Andreas tests the new node as a **new API** on the
   real site (e.g. carpx). **This is THE test.**

**The pipeline is separate.** Wiring the node into a multi-step flow (e.g.
`removebg → node → convert`) is verified on its own, *after* the node itself passes.
