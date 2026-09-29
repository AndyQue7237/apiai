<!-- HEJA — differences between the local Heja documentation and the flow that actually ran on apiai.me on 2026-09-29. From flow_config (admin API) and the exported scripts. -->

# Heja Team Emblem: apiai.me compared with local

The Heja flow is already documented locally, and that is the **primary source**:

- `customers/heja/pipeline/APIAI_SETUP.md` — all 22 nodes, parameters and conditions
- `customers/heja/pipeline/WINNER.md` — why it looks the way it does, eval results and learnings
- `customers/heja/pipeline/run_pipeline_v2.py` — the local runnable version

This document covers **only what differs** between the local documentation and the flow
`heja-team-emblem` as it stood on apiai.me on 2026-09-29, read from `flow_config`.
The structure matches: 22 nodes, same order, same five conditions with the same `skip_count`,
`output_node = node_22`.

## Differences

| # | Node | Local (`APIAI_SETUP.md`) | On apiai.me | Meaning |
|---|---|---|---|---|
| 1 | 10, 22 (final crop) | Script `crop_transparent`, `format: 1:1` | API **`smart-crop`**, `format: square`, `background: transparent`, `subject_scale` omitted | **Same code, different name:** the local `scripts/crop_transparent.py` is identical to the script `smart_crop` on the site. `square` and `1:1` mean the same thing. (The local `scripts/smart_crop.py` is an older, different script.) |
| 2 | 10 (end of the low-quality branch) | `end_pipeline: true` | **`stop_after: true`** on the node | Same function, different name. |
| 3 | 6, 14, 18 (check resolution) | `min_pixels: 5000000` | **`max_pixels: 5000000`** + `field: is_high_resolution` | The parameter is called `max_pixels` locally too, even though it is a floor. `APIAI_SETUP.md` has the wrong name. |
| 4 | 1 (detect and crop) | `query`, `min_padding` | + **`safety_margin: 30`**, **`padding_percent: 5`** | Two extra parameters on the site. |
| 5 | 4 (GPT Image 2) | — | + **`moderation: low`** | Lowered moderation, so logos are not blocked unnecessarily **(interpretation)**. |
| 6 | 9, 17, 21 (Real-ESRGAN) | `scale`, `face_enhance` | + `threshold` and `sample_percent` **Omit** | The `real-esrgan` API has two incorrect parameters (copied from `check-transparency`). Omit prevents them from being sent to Replicate. |
| 7 | 11 (check transparency) | `sample_percent`, `threshold` | + `field: has_transparency` | The field name is set explicitly. |

## Skip: code locally, condition nodes on apiai

Locally (`run_pipeline_v2.py`) the routing and skips live in the Python code as `if/else`.
Routes: `gpt2_enhancement`, `transparent_skip`, `script_bg_removal`, `gpt2_edge_case`.
On apiai there is no code between the nodes, so the same decisions are made with **condition nodes**, where
`skip_count` skips the next N nodes. That is why the flow has 22 nodes, with two
separate branches one after the other: nodes 1–10 for low quality, ending with `stop_after`, and
nodes 11–22 for high quality.

Two consequences:
- **The same steps are repeated.** Check resolution, downscale and upscale exist in both branches,
  because a condition can only skip forward, not branch and merge again.
- **`run_pipeline_v2.py` is an older version than the apiai flow.** It lacks
  color correction and the second upscale, and still has the `gpt2_edge_case` route
  (multi-colored background → GPT). On apiai that image is instead passed on unchanged
  (`passthrough_on_mismatch: true` on node 13). `APIAI_SETUP.md` describes the apiai version.

## How the wiring works on apiai

Each node takes the image from the previous node (`from_node`), **including from condition nodes and from
nodes that are skipped**. Example: node 11 reads from node 10, but in the high-quality branch
nodes 4–10 never run. So the platform passes the latest actual result on through skipped
nodes **(interpretation:** it is the only way the flow can work).

The only exception is node 5 (`correct-colors`): `image_reference` is bound to **Original**
(`use_original`), i.e. the pipeline's input image. That is how the GPT image is compared against the original's colors.

The pipeline's public input is only `image` (Expose on node 1). All other parameters are fixed.

## Script versions

Two scripts differ in code between `scripts/` and the site, and one has been renamed:

| Script | Difference |
|---|---|
| `check_resolution` | The site uses `PARAM_DEFS` + `script_io`, returns only the boolean. Same logic. |
| `check_transparency` | The site requires `script_io` (locally there is a fallback without it). Same logic. |
| `smart_crop` | The site's `smart_crop` = local `crop_transparent.py`, identical code. The local `smart_crop.py` is an older variant. |

The site's versions are available verbatim in `docs/export/*.sanitized.json` (`scripts[].source_code`).

## Minor details

- The `check-resolution` API has `response_type: "video"` in its configuration, even though it
  returns an image. It does not seem to affect the flow, but it is wrong.
- `WINNER.md` (2026-09-21): node 20 is set to `max_pixels: 2000000`, which matches the site.
