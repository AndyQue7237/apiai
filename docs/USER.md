<!-- USER — how apiai.me works for a customer: the user dashboard, page by page, plus the account/team/billing data model. Written 2026-09-29 from a recorded user session (docs/crawl/user, gitignored), not from memory. -->

# apiai.me User Dashboard: how it works for a customer

The customer-facing side of apiai.me, counterpart to [`ADMIN.md`](ADMIN.md). Describes what a
logged-in user sees and can do, and the data behind it.

**Source:** a recorded user session 2026-09-29 (`docs/tools/record_admin.py --label user`),
with page texts and the JSON the dashboard loads. Personal data and API keys were removed.
Statements that are conclusions rather than readings are marked **(interpretation)**.

---

## 1. Sign-in

- **Passwordless.** Email → 6-digit code (expires in 10 minutes), or *Continue with Google*
  (Google One Tap). *Login* and *Register* are the same flow.
- After sign-in the user lands on `/dashboard/start`.
- API calls authenticate with the header `X-API-Key: ak_…`. There is one key per user, shown
  masked (`ak_55b7b••••`) and labelled with the team name. *Regenerate* invalidates the old key.

## 2. Navigation

`/dashboard/…`: **Start here** · **API Toolbox** · **My Pipelines** · **Custom Pipelines** ·
**Batches** · **API Keys** · **Use in AI tools** · **Team** · **Analytics** · **Funds** ·
**Docs** · **Eval** (links to eval.apiai.me). The balance is always visible in the sidebar.

## 3. Start here (onboarding)

*"Three steps from sign-up to an API of your own."* Progress is shown as `2/3` in the sidebar.

| Step | What it asks | Tracked by (`/api/account/start`) |
|---|---|---|
| Run a template | Pick a ready-made pipeline, drop in a photo, press Run | `ran` |
| Call it from your code | Copy a curl (the API key is already in it) | `api_called` |
| Build your own pipeline | Chain tools into one endpoint | `pipelines` (count) |

The page can be hidden (`dismissed`); it stays under *Start here*.

**Lesson:** onboarding is built around **the first successful call**, not around reading docs.
Every tool and pipeline card has a ready-made curl with the user's own key filled in.

## 4. API Toolbox

*"Your deployed API endpoints."* Every tool the user has access to (see `ADMIN.md` section 2).

- **Filters:** All · Favorites · Recent · Free · Paid, plus one per category (Background
  Removal, Image Generation, Video, Visual Intelligence …).
- **One card per tool:** name, price, status, category, endpoint `/api/process/{slug}`,
  description, **Ask AI** (help chat that uses the API's *AI context*), a **curl example**
  with the key and default params, a **parameter table** (name, description, default,
  allowed values, required/optional), and **Run** directly in the browser.
- **Price estimate** for tools with parametric pricing: `POST /api/process/{slug}/estimate`
  with the chosen params. Two behaviours:

| `reconciled` | Meaning (verbatim note from the API) |
|---|---|
| `false` | *"Cost varies with the params you submit. Actual charge is fixed at request time."* |
| `true` | *"Estimate is what we'll reserve upfront. Final charge is reconciled against actual provider metrics (e.g. GPU seconds) after the request completes — bounded by min/max."* |

The user-side tool list (`/api/workflows`, 89 entries) contains three types:
`workflow` (76, `/api/process/{slug}`), `pipeline` (11, the customer's custom pipelines,
`/api/pipeline/{slug}`) and `utility` (2, `/api/v1/…`, e.g. quality gate and moderation).

## 5. Pipelines: two kinds

| | **My Pipelines** | **Custom Pipelines** |
|---|---|---|
| Built by | The user, in the dashboard | apiai.me staff, in admin (*"Pipelines built for your account by our team"*) |
| Endpoint | `/api/flow/{slug}` | `/api/pipeline/{slug}` |
| Source | `/api/flows` (per user; `is_node_based`, `flow_config`) | Admin `flows`, granted via Team/Per-User access |
| Example | *Carpx studio image Seedream*: Format Converter → Bria Remove Background → Place Image on Canvas → Seedream 4.5 | *AZ Change Fabric - Mask*, *Heja Team Emblem* |
| Extra | **Debug** (run step by step) + Run | Run; *"Need a completely custom pipeline? Request here →"* |

- **Templates:** 13 ready-made pipelines (`/api/pipeline-templates`) that a user can copy into
  *My Pipelines* and edit. These are the admin pipelines marked *Template*.
- **The pipeline price is the sum of its nodes' prices.** Verified on six user pipelines, e.g.
  *Carpx studio image Seedream* = Format Converter $0.01 + Bria $0.02 + Place Image $0 +
  Seedream 4.5 $0.05 = $0.08. The AZ custom pipelines cost $0 in admin but are shown to the
  customer as $0.150, the price of their single Nano Banana Pro node.
- The card shows the node chain and **only the exposed parameters**, grouped per node, so the
  customer never sees the fixed prompts inside.
- The account in this session had 17 own pipelines (Carpx, IKEA, AZ, fashion mockups, video)
  and 11 custom pipelines.

### 5.1 The user pipeline builder

Source: a user-dashboard page saved with an existing pipeline open in *Edit Flow* (2026-09-29).
It is a three-step form inline on *My Pipelines* (`#flow-builder`), not a modal as in admin.

1. **Name your pipeline:** *Pipeline name*, *API endpoint* (auto-filled from the name; the page
   shows the resulting `POST /api/pipeline/{slug}`), *Description* (optional, *"tells
   teammates you share it with what it's for"*).
2. **Add tools:** *"Click a tool to add it as a step — chain as many as you need."* The tools
   are grouped by **category** with counts and a search field, and **Gate** sits in its own
   group at the top. Only tools the user has access to appear (78 in this account).
3. **Configure each step:** *Pipeline Nodes (n/30)*, so there is **a limit of 30 nodes**. Each
   node card is collapsible (▶), with a **?** help button (the *Ask AI* help) and ✕ to remove.
   Buttons: *Save Changes*, *Cancel*.

**Binding choices, user wording vs admin wording** (from the help text in step 3):

| User builder | Admin builder (`ADMIN.md` 7.3) | Meaning |
|---|---|---|
| User Input (*"caller sends it"*) | Expose | Becomes a parameter of the pipeline API |
| Link from Prev. (*"from a previous step's output"*) | Wire ← prev | Takes an earlier node's output |
| Constant Value (*"baked-in value"*) | Fixed | Fixed value |
| Default (*"use API default"*) | Default | The API's default |
| Skip (*"exclude from request"*) | Omit | Not sent |
| — | Use original ↑ | Not mentioned on the user side |

**Differences from the admin builder:**
- **No Condition node** in the user tool list, only **Gate**. Users can stop a pipeline on a
  YES/NO question but cannot skip steps. Branching like Heja's is admin-only.
- **Customer-friendly labels** (User Input / Link from Prev. / Constant Value / Skip) instead
  of Expose / Wire / Fixed / Omit, and tools grouped by category instead of one A–Z list.
- **Utilities available as steps:** *Quality Gate* and *Check Image (Moderation)* appear as
  regular tools.
- **Per-parameter mode is a button menu with explanations**, not a bare dropdown:
  *User Input: "User provides the value when running."* · *Constant Value: "A fixed value
  locked into this pipeline."* · *Default: "Uses the AI model's built-in default setting."* ·
  *Skip: "This parameter will be excluded from the request."* Each row shows the parameter's
  description underneath. Constant values get a dropdown when the API declares allowed values
  (e.g. `aspect_ratio`), otherwise a text box.
- **Required parameters are restricted.** `PROMPT` on Nano Banana 2 (marked REQUIRED) offers
  only *User Input* or *Constant Value*; *Default* and *Skip* are not available.
- **Stop pipeline after this step** exists on the user side as well.
- **No Failover workflow** on user nodes; the admin builder has one per node (`ADMIN.md` 7.3).
- **No Use original.** In admin, the first node's `image` parameter offers *Use original ↑*;
  on the user side the same parameter only offers User Input / Constant Value / Default / Skip.
  So a user pipeline cannot send the original input to a later step, which is what Heja's
  color correction depends on **(interpretation:** only node 1 was expanded; *Link from Prev.*
  appears from node 2 per the help text).

**Lesson:** "build your own" and "built for you" are separate lists with separate
endpoints. A customer can start with a custom pipeline and later build variants on their own.

## 6. Batches

*"Process multiple images through any workflow at once."* Choose a tool or pipeline, drop
files (**max 50 per batch**), press *Start batch*. Results can be downloaded for **1 hour**
after completion, as many times as needed within that window.

## 7. Use in AI tools (MCP)

*"Every tool and pipeline in your account, callable from the AI assistant you already use."*

- **MCP server:** `https://apiai.me/api/mcp`.
- **Sign-in based** (no API key): Claude.ai, ChatGPT, Gemini (they connect with OAuth to the
  apiai.me account).
- **API key based** (key pre-filled in the snippet): Claude Code, Codex, Gemini CLI, Cursor,
  VS Code, Claude API, OpenAI API, Gemini API, Other.
- **Example prompts** on the page: *"What tools does apiai have, and what do they cost?"*,
  *"Remove the background from this product photo, then check the result has a clean white
  background."*, *"Run my pipeline on these five images and tell me which ones failed the
  quality check."*
- **Shopify:** connect Shopify to the same assistant, and results can go straight onto products.
- **Connected apps:** list of apps signed in with the account; disconnecting takes effect
  immediately.

**Lesson:** the tools and pipelines are exposed as agent tools with no extra work. For a
content product this is probably the main channel, not the dashboard.

## 8. Team

*"Team — {org name}. Manage your organization members and invitations."*

- **Members:** name, email, role (`owner` / `developer` / …). Roles per the public docs:
  *Owner* (everything), *Developer* (API + dashboard), *Designer* (dashboard only).
- **Invitations** (pending invites). Invite, change role and remove are owner actions
  (public API: `/team/invite`, `/team/members/{id}/role`).
- **Leave organization:** *"You will lose access to this organization's workflows and shared
  balance."*
- **Shared balance:** the balance sits on the **org** (`org.balance`), not on the member.
- **Team notes** (`/api/team/notes`): free-text notes attached to a resource
  (`resource_type`, `resource_id`), shared within the org, with author and time.

## 9. Analytics

*"Monitor your API usage and costs."* Four figures for the current month (`/api/usage`):
balance, total requests (+ successful), success rate (+ failed), total cost. Below, **Recent
activity** (`/api/logs`, latest 20): status, slug, type, duration, cost, time, request id.

Log `request_type` is `workflow`, `flow` or **`eval`**. In the session every run of the
pipeline `draw-hero-banner` was followed by an `eval` entry within seconds. That is the
auto-eval (Quality Monitoring) scoring each run of a watched pipeline, and it is logged
without a cost of its own **(interpretation)**.

## 10. Funds

*"Top up your account balance to continue processing."*

- **Top-up** $10 / $50 / $100 via Stripe (redirect to Stripe checkout, with a confirmation
  dialog first).
- **Auto refill** per amount: *"Your card is saved for auto-refill."* The setting is
  `{enabled, amount}`; the public docs say it triggers when the balance falls below $5.
- *"Costs are deducted per successful API call."*
- **Payment history:** date, amount, status (e.g. *Refunded*), receipt link from Stripe.

---

## 11. Data model (customer side)

| Endpoint | Returns |
|---|---|
| `GET /api/account` | `id`, `username`, `email`, `company`, `org_name`, `org_role`, `balance`, `trial_status`, `api_key`, `created_at` |
| `GET /api/account/start` | Onboarding: `ran`, `api_called`, `pipelines`, `company`, `dismissed` |
| `GET /api/account/auto-refill` | `enabled`, `amount` |
| `GET /api/account/payments` | `amount`, `currency`, `created`, `status`, `refunded`, `receipt_url` |
| `GET /api/account/connected-apps` | Apps connected via OAuth (MCP) |
| `GET /api/workflows` | Tools visible to the user: `slug`, `endpoint`, `method`, `type`, `category`, `params` (with `base_name`, `max_files`), `price_per_request`, `pricing_kind`, `supports_prompt`, I/O types |
| `POST /api/process/{slug}/estimate` | `kind`, `estimate`, `min`, `max`, `reconciled`, `note` |
| `GET /api/flows` | The user's own pipelines, including `flow_config`, `is_node_based`, `price_per_request`, first-step input info |
| `GET /api/pipeline-templates` | The 13 templates |
| `GET /api/batch` | `batches`, `limit` (50) |
| `GET /api/usage` | `period`, `total_requests`, `success_count`, `error_count`, `total_cost`, `balance` |
| `GET /api/logs` | Latest calls: `request_type`, `workflow_slug`, `status`, `cost`, `processing_ms`, `request_id` |
| `GET /api/team` | `org` (incl. `balance`, `owner_user_id`), `members`, `invitations`, `my_role` |
| `GET /api/team/notes` | Notes per resource within the org |

## 12. Lessons for a new product

1. **Time to first call is the product.** A curl with the user's own key on every card, Run in
   the browser, and a three-step onboarding tracked on the server.
2. **Two pipeline lists work.** "Mine" (self-built, debuggable) and "built for you"
   (staff-built, fixed prompts hidden) serve different customers without mixing them up.
3. **Hide the recipe, show the knobs.** Customers see only exposed params; prompts and fixed
   values stay server-side.
4. **Price before running.** Estimates with explicit reconciled vs fixed semantics prevent
   surprises on video and other per-second models.
5. **The balance belongs to the team.** Shared balance + roles makes agencies and in-house
   teams easy to support.
6. **Agents are a first-class client.** MCP with OAuth for chat assistants and a key for
   developer tools, plus connected-app management.
