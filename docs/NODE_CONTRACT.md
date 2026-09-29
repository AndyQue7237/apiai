<!-- NODE_CONTRACT — how a Python script becomes a node on apiai.me: the runtime contract, the platform's limits, and where all 46 scripts are kept verbatim. Written 2026-09-29. -->

# The node contract: from script to node

How a Python script becomes a callable tool and a node in a pipeline on apiai.me.

- **The rules for writing a script** (the contract in detail): `guidelines/SCRIPT_GUIDELINES.md`.
  This document doesn't repeat them; it summarizes and adds the platform's own facts from the
  admin.
- **All 46 scripts verbatim:** [`scripts/`](scripts/), with a catalog in
  [`scripts/CATALOG.md`](scripts/CATALOG.md). Andreas's decision 2026-09-29: the scripts are
  kept with full code (see `HANDOVER.md`).

---

## 1. The contract in brief

A script is a standalone program that the platform starts per request.

```
stdin:  {"image": "<base64>", "content_type": "image/png", "params": {...}}
stdout: {"image": "<base64>", "content_type": "image/png", ...extra fields on the root}
```

- **I/O goes through `script_io`**, which the runtime provides: `read_input()`,
  `write_output(bytes, content_type, **fields)` and `write_error(message)`. A local copy for
  testing is in `customers/heja/pipeline/script_io.py`.
- **A single image in the body.** Additional images (mask, reference) come as base64 strings
  in `params`. The pipeline's *Original* binding (`ADMIN.md` 7.2) sends the pipeline's input
  image to such an image parameter **(interpretation)**.
- **Parameters are declared in `PARAM_DEFS`** in the script. The admin's *Scan Script* reads
  them and creates the API's parameter list automatically.
- **Extra fields on the root become metadata** that condition nodes can read
  (`condition_field`). Example: `check_quality` writes `has_high_quality`, `check_resolution`
  writes `is_high_resolution`. Never in a nested `metadata` object.
- **Output is RGBA PNG** for image scripts.

## 2. The platform's limits (from the admin 2026-09-29)

| Limit | Value |
|---|---|
| Server | "Pyton Scripts", type `python`, URL `local`. The scripts run on the platform's own server. |
| Allowed packages | `Pillow`, `replicate`, `numpy`, `opencv-python-headless`, `scikit-image`, `cairosvg`, `scipy`, `pillow-heif` + stdlib. Chosen per script in the *Packages* field. Not `requests`, not `scikit-learn`. |
| Environment variables | `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `REPLICATE_API_TOKEN`, `XAI_API_KEY` (via `os.environ`) |
| Timeout | Set per API: default 30 s, max 300 s |
| Output types | Image (PNG/WebP), Video (MP4), Audio, Text (JSON), ZIP |
| Concurrency | 8 runs total, 4 per user (applies to all APIs, not just scripts) |

## 3. From script to node, step by step

1. **Scripts → Add Script:** name (filename without `.py`), description, packages, source
   code. Test with *Test Script* (image + params as JSON). There is also an AI assistant,
   *Ask Claude* / *Fix it*, that can write the script.
2. **APIs → Add API:** server "Pyton Scripts", choose the script, set timeout and I/O types.
   *Scan Script* fetches the parameters. Set a price (scripts are often free) and a
   description. *Test Run* and a pre-save check catch broken APIs.
3. **Access Control:** grant the API at the right level (global, user, team). Without access
   no one can call it, and a template may only use global tools.
4. **Pipelines → Add Pipeline:** click the API in as a node and bind each parameter (*Fixed*,
   *Wire*, *Expose*, *Omit*, *Default*; `ADMIN.md` 7.2).

## 4. State of the scripts

46 scripts on the site, compared with `scripts/` in this repo (details in `scripts/CATALOG.md`):

| State | Count | Scripts |
|---|---|---|
| Identical | 11 | e.g. `check_quality`, `correct_colors`, `detect_and_crop`, `nb_pro_inpaint`, `smooth_mask` |
| Identical, different name | 3 | `smart_crop` = `crop_transparent.py` · `remove_solid_bg` = `remove_solid_background.py` · `auto_crop` = `crop_center.py` |
| Differ | 2 | `check_resolution`, `check_transparency` (the site requires `script_io`; same logic, see `flows/HEJA.md`) |
| Only on the site | 30 | Filters, video, text, format etc. Now kept in `docs/scripts/`. |
| Only in the repo | 4 | `compress_video`, `has_solid_background`, `logo_pipeline_complete`, `make_square` |

**Most used script APIs** (requests 2026-08-31 to 2026-09-29): `flip-mirror` (67),
`correct-colors` (52), `fancy-text-on-images` (29), `format-converter` (21),
`remove-solid-background` (17), `fabric-swap-material-swap` (14).

## 5. Learnings for a new product

1. **Stdin/stdout JSON is enough.** The contract is small enough to run anywhere, e.g. in a
   container or a serverless function. The scripts can be moved unchanged, as long as
   `script_io` comes along.
2. **Metadata on the root is the engine of routing.** Condition nodes read fields directly
   from the previous node's output. Keep the field names stable; they are an API.
3. **The package list is a security boundary.** Allowlist + keys via environment variables
   let customers and the AI assistant write scripts without full system access.
4. **The names drift apart.** Three scripts have been renamed between repo and site, and two
   have been changed only on the site. A new product should have **one** source for the
   script code (the repo) and deploy from there, not edit in the admin.
