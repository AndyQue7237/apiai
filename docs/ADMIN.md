<!-- ADMIN — how the apiai.me admin works: data model, tab by tab. Written 2026-09-29 from the admin HTML (docs/html/extracted/) and the admin API (recording), not from memory. -->

# apiai.me Admin: how it works

Documents **how** the admin part of apiai.me works: which concepts exist, how they relate,
and what each field does. The goal is that a new product can build the same thing, or
deliberately do it differently, without access to the platform.

**Sources** (2026-09-29):
- `docs/html/extracted/*.md`: forms, fields and help texts from the saved Admin Console.
- The admin API (`/admin/api/*`), recorded with `docs/tools/record_admin.py`: data model,
  enum values and counts. The raw recording is local and gitignored.
- `docs/public-docs-summary.md`: the public API documentation (summarized).

No customer data and no keys are included here. Statements that are conclusions rather than
direct readings are marked **(interpretation)**.

---

## 1. Data model at a glance

```
Server ──< API (workflow) >── Pipeline (flow) ── node ── node ── node …
  │           │
  │           └── Script  (when the server is "Python (Local)")
  │
  └── credentials (API key per provider)

User ──> Org (team)          Access: Global │ Per user │ Per team
Admin user (separate login, TOTP)
```

| Concept | In UI | In API/data | What it is |
|---|---|---|---|
| **Server** | Servers | `servers` | A provider connection: type, URL, key. 7 in total. |
| **API** | APIs | `workflows` | A callable tool: a model *or* a script behind a server. 87 in total. Public endpoint `/api/process/{slug}`. |
| **Script** | Scripts | `scripts` | Python source code run by the Python server. 46 in total. Only becomes callable once an API points to it. |
| **Pipeline** | Pipelines | `flows` | A chain of APIs (nodes), with conditions and gates. 27 in total. Public endpoint `/api/pipeline/{slug}`. |
| **User** | Users | `users` | Customer with a balance and an API key. Can belong to an org. |
| **Org** | (Team) | `orgs` | Team; members share pipeline access and balance. |
| **Admin user** | Users → Admin Users | `admin-users` | Separate admin account, with TOTP. |

The names differ between UI and data: **API = workflow** and **Pipeline = flow**. This comes
from the platform's origin as a ComfyUI backend (the export file is called `comfyui-b2b-export`
and the API form still has a field for "Workflow JSON (ComfyUI API format)").

---

## 2. Access Control ⭐

Controls **which APIs and pipelines a user may call**. Three levels, which add up:

| Level | Applies to | Can grant | How |
|---|---|---|---|
| **Global Access** | *All* registered users, automatically | APIs and pipelines | Search, select, "Grant Selected to All Users". |
| **Per-User Access** | One user | APIs and pipelines | Choose user → select → "Grant Selected". *"In addition to any global access."* |
| **Team Access** | A whole org | **Pipelines only** | Choose team → select → "Grant Selected". *"All current and future members automatically inherit access."* |

Status 2026-09-29: **73 APIs and 1 pipeline** were globally available (of 87 and 27
respectively). Every grant has a timestamp (`granted_at`).

**Rules that can be read out:**
- **Templates require global access.** A pipeline marked *Template* is offered as a starting
  point in every user's *My Pipelines*, where they can copy it and edit their own version.
  *"Templates may only use tools that are granted globally — saving tells you which ones are
  missing."* So this is validated on save.
- **Copyable** is a separate flag on the pipeline: whether users may copy it.
- **Customer-specific pipelines** (Heja, AZ, Widforss …) are granted via Team Access or
  Per-User, not globally **(interpretation:** only 1 pipeline is global, and the customer
  flows are not templates).
- **Team roles** (from public docs): *Owner* (everything), *Developer* (API + Dashboard),
  *Designer* (Dashboard only). **Shared billing:** the owner's balance covers all members. The
  role is stored on the user (`org_role`).

**To carry over to a new product:** three levels go a long way. The team level, inherited by
future members, is what makes customer flows manageable. That teams can only be granted
*pipelines*, not individual APIs, is a deliberate choice worth reconsidering.

---

## 3. Users ⭐

The tab has three parts: Admin Users, sign-up blocking, and registered users.

### 3.1 Registered users

**Login is passwordless:** email → 6-digit code (`POST /login` → `POST /verify` in the
public API). API calls are authenticated with `X-API-Key: ak_…`. The user can rotate the key.

**Create user (admin):** email + company name → **"Create & Send Code"**. The user receives a
code and verifies themselves.

**Fields per user:**

| Field | Meaning |
|---|---|
| `username`, `email`, `company` | Identity. The username is derived from the email **(interpretation)**. |
| `api_key` | The user's API key. |
| `balance` | Prepaid balance in USD. Deducted per call (`X-Cost`). |
| `email_verified` | Has entered the code. *"Never entered a code"* = registered but never verified. |
| `org_role` | Role in their team (Owner / Developer / Designer). |
| `trial_status` | Status of trial credit. Admin can *Grant trial* or *Decline*. |
| `suspended` | Suspended; *Suspend* / *Unsuspend*. |
| `signup_ip`, `signup_country` | Stored at sign-up, for abuse protection. |

**Actions on a user card:** ✎ edit (balance and role are edited inline, **interpretation**
from the element names), *Grant trial*, *Decline*, *Suspend*/*Unsuspend*.

**Filters:** All users · Verified only · Never entered a code · Balance above $0 · Trial credit
held · Suspended. Search by email, name, company or IP. The list is grouped by day and by email domain.

Status 2026-09-29: 185 users, of whom 3 never verified.

### 3.2 Sign-up abuse protection

- **Blocked Sign-up Domains:** sign-ups from these email domains are *silently refused*.
  - Manually: domain + optional reason → *Block*.
  - **Automatically:** a domain that reaches **3 verified sign-ups in 24 hours** is blocked.
  - A public list of disposable email addresses is built into the code and not shown in the list.
- **Refused sign-ups:** log of refused sign-ups, filter 24 h / 7 d / 30 d.

### 3.3 Admin Users

- Separate login from regular users: **email + TOTP code** (Google Authenticator,
  1Password, Authy …).
- **First time:** *"Enroll TOTP via bootstrap token"* — a one-time token is used to register
  the authenticator app.
- Add admin: email + name. Per admin: *Reset TOTP*, *Remove*.

---

## 4. Servers

A server is a **provider connection**. APIs point to a server.

**Form (Add Server):** Name · Type · URL · credentials. The server's type determines which
configuration panel the API form shows (see 5.2).

**Selectable types:** ComfyUI · Google Gemini · xAI (Grok) · OpenAI · RunPod Serverless ·
Replicate · Python (Local) · Other.

**Configured servers (7):**

| Name | Type | URL | Config |
|---|---|---|---|
| Pyton Scripts | python | `local` | — |
| Replicate | replicate | — | `api_key` |
| Gemini | gemini | `https://generativelanguage.googleapis.com/v1beta` | `api_key` |
| GROK | xai | `https://api.x.ai/v1` | `api_key` |
| GROK Video | xai | `https://api.x.ai/v1` | `api_key`, `model` |
| Gemini Video | gemini | `https://generativelanguage.googleapis.com/v1beta` | `api_key`, `model` |
| OpenAI | openai | `https://api.openai.com/v1` | `api_key`, `model` |

**Health check (probe):** the admin calls `/admin/api/{provider}/probe` per API and stores the
result on the API (`last_probe_status`, `…_capability`, `…_elapsed_ms`, `…_inference_tested`).
The UI shows "✓ live". Status: 56 verified, 7 failed, 24 never tested.

**Lesson:** the keys are stored in plain text in the server config and are included in the
export. A new product should store them in a secrets manager and never export them.

---

## 5. APIs

An API is **a callable unit**: either a model at a provider or a script.
87 in total: 44 script-based, 43 model-based (Replicate 24, Gemini 11, OpenAI 7, Grok 1).

### 5.1 Common fields (Add API)

| Field | Meaning |
|---|---|
| Name, Slug, Description | The slug becomes the URL: `/api/process/{slug}`. The slug is generated from the name. |
| **AI Context** | Extra guidance for the "?" help chat: good parameter values, when to use the tool, model quirks, common failures. The *Suggest* button generates a proposal. 44 of 87 APIs have it filled in. |
| Category | Image Generation, Video, Image Editing and Cropping, Visual Intelligence, Utilities, Image Filters, Background Removal, Customer Scripts, Text Generation … |
| **Price per Request ($)** | What the customer is charged per call (four decimals). |
| Provider cost per request ($) | What the provider charges us. *"Neither is used at charge time; they make the margin visible."* **Filled in on 0 of 87.** |
| Markup override (%) | Markup per API; empty = default from Pricing. Filled in on 0 of 87. |
| **Parametric pricing rule** | Replaces the flat price when enabled: price computed from request parameters. See 5.3. |
| Server | Which provider. Determines the configuration panel below. |
| **I/O Type Declarations** | Accepted Inputs: Image / Video / Text-JSON / Audio, each *off → optional → required*. Output Type: Image / Video / Text-JSON / Audio / ZIP. |
| Max Images | How many image files the primary input accepts (1 = one, higher = several, max 20). |
| Canva | Flag for the Canva integration (16 APIs). |
| **Parameters** | List of parameters. *Scan JSON* / *Scan Script* find them automatically. See 5.4. |

**Before saving:** a *pre-flight validation* runs, *"so a broken API is caught here rather
than by a customer"*. There is also a **Test Run** panel: upload an image, write a prompt,
override parameters, see the run log.

### 5.2 Configuration per server type

| Server type | Fields |
|---|---|
| **Gemini** | Model (*Fetch Models* lists the available ones) · Response Type: Image / Video / Text / Auto (Image + Text) · Temperature, Top-P, Top-K, Max Output Tokens · Aspect Ratio (1:1, 3:4, 4:3, 9:16, 16:9) · Image Size (512, 1K, 2K, 4K) · Num Images (1–4) · Safety Filter · Negative Prompt · **Prompt** |
| **xAI (Grok)** | Model (*Fetch Models*) · Response Type: Text / Image / Video / Auto · Temperature, Top-P, Max Tokens, Frequency/Presence Penalty · **Prompt** |
| **OpenAI** | Model (*Fetch Models*) · Response Type: Text / Image · Temperature, Top-P, Max Tokens, Penalties · Size (auto, 1024², 1536×1024, 1024×1536 …) · Quality (Standard, HD, Low, Medium, High, Auto) · Background (Transparent, Opaque, Auto) · Style (Vivid, Natural) · **Prompt** |
| **Replicate** | Search the Replicate catalog or enter a model ID (`bytedance/seedream-4`) → *Fetch Schema* fetches the model's inputs automatically and maps them to canonical names (`prompt`, `image`) · Image Field (auto-detect) · Image Upload: Auto (Data URL for video, Files API otherwise) / force Files API / force Data URL · Output Type |
| **Python (Local)** | Script (from the Scripts tab) · Timeout (s, default 30, max 300) · Output Type (incl. ZIP) |
| **ComfyUI** | Workflow JSON (ComfyUI API format). `LoadImage` is automatically replaced with `{{INPUT_IMAGE}}`. |

**Prompt templates:** for Gemini, Grok and OpenAI the prompt is written in the API with placeholders:
- `{{PARAM_NAME}}` — replaced with a configurable parameter.
- `{{PROMPT}}` — replaced with the customer's own ad-hoc prompt.

This way the same model can exist as several APIs with different baked-in prompts, for example
"Nano Banana Pro Inpainting" and "Nano Banana Pro Reference Image".

### 5.3 Parametric pricing

A JSON rule that computes the price from the call's parameters. Preset types: *Veo (request
params)*, *Replicate-by-seconds (reconciled)*, *Token-based (LLM, not yet reconciled)*, *Flat*.
Example from the form's placeholder:

```json
{"kind": "formula", "base": 0.05, "min": 0.10, "max": 20.00,
 "linear": [{"param": "duration_sec", "rate": 0.50}],
 "multipliers": [{"param": "resolution", "values": {"720p": 1.0, "1080p": 2.0, "4k": 6.0}, "default": 1.0}]}
```

Price = base + Σ(param × rate), times multipliers, clamped between min and max
**(interpretation** of the format). A preview computes the cost for sample parameters. The
public API has `POST /process/{slug}/estimate` for the same thing.

### 5.4 Parameters

Per parameter: `name`, `expose_name` (public name if it differs), `description`,
`default_value`, `required`, `is_image`, `type` (string / int / float).

---

## 6. Scripts

Python source code run by the "Python (Local)" server. Full source code for all 46 scripts
is in the sanitized export (`docs/export/*.sanitized.json`). The contract for how a script is
written is in `guidelines/SCRIPT_GUIDELINES.md`.

**Form (Add Script):**
- Name (filename without `.py`) · Description.
- **Packages**, only from an allowlist: `Pillow`, `replicate`, `numpy`,
  `opencv-python-headless`, `scikit-image`, `cairosvg`, `scipy`, `pillow-heif`.
- **Environment variables** (via `os.environ`): `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
  `OPENAI_API_KEY`, `REPLICATE_API_TOKEN`, `XAI_API_KEY`. So a script can call models
  itself: `nb_pro_inpaint` and `nb_pro_reference_image` call Gemini, and
  `detect_and_crop`, `correct_colors` and `Detect and Remove Background` use the
  `replicate` library (which reads `REPLICATE_API_TOKEN`).
- Source Code: paste in or *Upload .py*.
- **Ask Claude** / **Fix it**: AI assistant that writes or changes the script from a
  description.

**Test Script:** upload an image + parameters as JSON (`{"padding": "20"}`) → *Run Test*.

**From script to callable tool:** create an API with the "Pyton Scripts" server, choose the
script, set timeout and output type, and add parameters (*Scan Script* finds them).

---

## 7. Pipelines

*"Build multi-step pipelines that chain tools together. Metadata (bounding boxes, colors,
flags) can be passed between steps."*

**Form (Add Pipeline):** Name · Slug (`/api/pipeline/{slug}`) · Description · Preview image
(for the template card) · flags **Active**, **Template**, **Copyable**. Below that: *Available
Workflows* (click to add as a node) and *Pipeline Nodes*.

**Test Flow:** *Run Flow* runs the whole chain; *Debug* runs step by step (public:
`POST /flow/{slug}/debug`).

### 7.1 Node types

From `flow_config` across all flows: 82 workflow nodes, 7 condition, 3 gate.

| Type | Fields | Behavior |
|---|---|---|
| **workflow** | `workflow` (API slug), `params` | Runs an API. |
| **condition** | `condition_field`, `condition_value`, `skip_count` | If the field in the previous node's JSON output has the value → **skip the next N nodes**. E.g. `is_high_resolution = true, skip 2` skips the upscaling. |
| **gate** | `gate_prompt`, `gate_input`, `yes_message`, `no_message`, `rejected_message`, `gate_branch_yes`, `gate_expose` | An LLM answers YES/NO to a question about the image (Quality Gate, ~$0.001). NO stops the flow with `no_message`. `rejected_message` if the safety filter blocks. `gate_branch_yes: "stop"` also ends the flow on YES **(interpretation)**. |

`output_node` specifies which node's result the flow returns.

### 7.2 Parameters on a node: six ways to bind

From the help text: *"Configure each parameter as Expose (user provides via API), Fixed (baked in),
Wire ← prev (from previous node output), Default, or Omit (remove from request)."*

| Binding | In `flow_config` | Meaning | Count |
|---|---|---|---|
| **Fixed** | `{"fixed": "…"}` | Baked-in value, e.g. a prompt. | 308 |
| **Wire** | `{"from_node": "node_4", "is_image": true}` | Takes the output of an earlier node. | 54 |
| **Original** | `{"use_original": true, "is_image": true}` | Takes the pipeline's *original* input image, regardless of step. | 6 |
| **Expose** | `{"expose": "image", "required": true, "default": "…"}` | Becomes a parameter in the pipeline's public API. | 39 |
| **Omit** | `{"omit": true}` | The parameter is not sent at all. | 51 |
| **Default** | `{}` | The API's own default value applies. | 20 |

A condition node passes the image through: the next node wires `from_node` to the condition node.

**Lesson for a new product:** this binding model is the core of "chaining models and scripts".
The *Original* binding (compare against the source image after generation) is what makes e.g.
Heja's color correction possible.

Heja and AZ flows: see `docs/flows/HEJA.md` and `docs/flows/AZ.md`.

---

## 8. Usage & Billing

Date filter (from–to) → two tables:

| Table | Columns |
|---|---|
| **By User** | Consumption per user (not shown here: customer data). |
| **By API** | `workflow_slug`, `workflow_name`, `total_requests`, `success_count`, `error_count`, `total_cost`. Pipelines appear as `flow:{slug}`. |

`total_cost` is what the customer was charged, not the provider cost, which was never recorded (5.1).

**Example, 2026-08-31 to 2026-09-29** (74 APIs/pipelines with traffic), the three largest:

| API / pipeline | Calls | Errors | Charged |
|---|---|---|---|
| Nano Banana 2 | 4 896 | 50 | $242.30 |
| `flow:widforss-produktbild` | 2 900 | 32 | $86.04 |
| Gemini 3.1 Flash Lite Preview | 1 180 | 1 | $47.16 |

**How billing works** (from public docs): prepaid balance; every response has `X-Cost` and
`X-Balance-Remaining`. Top-up via Stripe ($10 / $50 / $100) and auto-refill when the balance
drops below $5.

---

## 9. Monitor

Time window 1 h / 6 h / 24 h / 48 h / 7 d.

| Part | Content |
|---|---|
| **Stats Cards** | total_requests, success/error_count, error_rate, avg_ms, **p95_ms**, total_cost |
| **Live execution capacity** | Who holds the execution slots right now: `in_flight`, `holders`. **Limits: 8 concurrent executions in total, 4 per user.** |
| Hourly Chart | requests, errors, avg_ms per hour |
| Error Breakdown | most common error per API/pipeline with count |
| Slowest Requests | the slowest calls |
| Recent Errors | latest errors with error message |
| **AI Analysis** | AI summary of the error picture |

**Example, 24 h to 2026-09-29:** 296 calls, 6.4 % errors, average 8.7 s, p95 26.7 s, $8.66.
All 19 errors came from one flow (`widforss-produktbild`): Replicate background removal
rejects AVIF (415). **Lesson:** normalize the image format before the first provider.

**Discrepancy:** public docs say 1 concurrent execution per user and 2 in total; the admin shows
4 and 8. The admin value is current.

---

## 10. Open questions

- **The pipeline editor UI** (the node list, how a binding is chosen) is only visible with a
  flow open. The data is documented (7.1–7.2); the editor itself is not saved.
- **The user part** (regular login: dashboard, My Pipelines, API keys) has not been crawled.
- **The Pricing tab** (subscriptions, *What if?*) is deliberately left out: not launched.
- **The eval platform** (eval.apiai.me) and **batch** exist only in the public docs.
- **Provider costs** were never recorded; the margin per API is unknown.
