<!-- public-docs-summary — a summary of https://apiai.me/docs, fetched 2026-09-29 with WebFetch. SUMMARIZED, not verbatim: check exact parameters against the source. -->

# apiai.me API Documentation Structure

## Main Sections

The documentation is organized into seven primary categories:

### 1. **Getting Started**
- Overview: Introduction to tools, pipelines, and the workflow (configure → test → copy curl → integrate)
- How It Works: Four-step integration process via Dashboard
- Authentication: Passwordless email-based login with API key generation
- Rate Limits: Concurrency caps (1 per-user execution, 2 server-wide execution, 10 lightweight reads); 50 MB request body limit
- Base URL: `https://apiai.me/api/v1` with backward-compatible unversioned path

### 2. **Tools**
- **List Tools**: `GET /workflows` — discover available tools with slugs, parameters, pricing
- **Run a Tool**: `POST /process/{slug}` — execute tools via multipart form-data
- **Cost Estimation**: `POST /process/{slug}/estimate` — preview costs before execution
- **Streaming**: `/stream` suffix for long-running jobs with Server-Sent Events (SSE) progress
- **Response Types**: Image (PNG/JPEG), video (MP4), or JSON text
- **Parameters**: `image`, `prompt`, `output_filename`, and tool-specific params

### 3. **Pipelines**
- **List Pipelines**: `GET /flows` — user-created tool chains
- **Create Pipeline**: `POST /flows` — chain tools with legacy step-based or node-based config
- **Execute Pipeline**: `POST /flow/{slug}` — run multi-step workflows
- **Debug Pipeline**: `POST /flow/{slug}/debug` — test single steps in isolation
- **Delete Pipeline**: `DELETE /flows/{id}`
- **Quality Gates**: Special nodes that evaluate content (YES/NO) and conditionally route

### 4. **Batch Processing**
- `POST /batch` — upload multiple images for parallel processing
- `GET /batch` — list batch jobs
- `GET /batch/{id}` — job status and item details
- `POST /batch/{id}/cancel` — stop running batches
- `GET /batch/{id}/download` — retrieve results as ZIP (1-hour window)
- Results stored for 1 hour; supports both workflows and user pipelines (`flow:` prefix)

### 5. **Analytics & Logs**
- **Usage**: `GET /usage` — aggregated account statistics
- **Logs**: `GET /logs` (limit/max 200) — recent request history
- **SSE Events**: `GET /events` — real-time updates (usage changes, new logs) via streaming

### 6. **Quality Monitoring (Auto-Eval)**
- **Profiles**: Define "rubric" with goals, dimensions, pass threshold, watched pipelines
- **Input Slots**: Typed tokens (`{image_1}`, `{prompt_1}`) for multi-input pipelines
- **Manual Eval**: `POST /v1/eval/run` — score content against a profile
- **Monitors**: URL/RSS feeds scored on schedule (`daily` or `manual`)
- **Email Notifications**: Recipients with verdict triggers (`fail`, `review`)
- **Dashboard**: [eval.apiai.me](https://eval.apiai.me) for profile management and results

### 7. **Utilities**
- **Quality Gate**: `POST /quality-gate` — YES/NO evaluation of image, text, or URL (~$0.001)
- **Moderation Check**: `POST /moderation/check-image` — structured decision (allow/reject/review) with configurable policies (`general`, `nsfw`, `violence`, `brand-safety`, `product-photo`, `hate-speech`, `spam`)

### 8. **Billing**
- **Balance**: `GET /account/balance` — current account balance
- **Checkout**: `POST /account/create-checkout` (amounts: $10, $50, $100) — Stripe payment
- **Auto-Refill**: `GET/PUT /account/auto-refill` — auto-charge when balance drops below $5
- **Key Rotation**: `POST /account/regenerate-key` — invalidate old key, issue new

### 9. **Integrations**
- **MCP Server**: `https://apiai.me/mcp` (unauthenticated) or `https://apiai.me/api/mcp` (authenticated) — Model Context Protocol for VS Code, Cursor, Windsurf, Ollama
- **MCP Tools**: `list_workflows`, `generate_image`, `edit_image`, `run_flow`, `quality_gate`, `check_image`, `request_upload_link`, batch operations
- **Shopify**: Combine Shopify + apiai.me connectors in Claude or ChatGPT for automated product image editing

### 10. **Team & Organizations**
- **Roles**: Owner (full control), Developer (API + Dashboard), Designer (Dashboard only)
- **Team Endpoints**:
  - `GET /team` — org info and members
  - `POST /team/invite` — add member (JSON body)
  - `DELETE /team/members/{userId}` — remove member
  - `PUT /team/members/{userId}/role` — change role
  - `POST /team/invite/{token}/accept` — accept invitation
  - `DELETE /team/leave` — exit org
  - `PUT /team/org/rename` — rename org (owner only)
- **Shared Billing**: Owner's balance covers all members

## Key Endpoints Summary

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/workflows` | List available tools |
| POST | `/process/{slug}` | Run single tool |
| POST | `/process/{slug}/estimate` | Preview cost |
| POST | `/process/{slug}/stream` | Long-running tool with SSE |
| GET | `/result/{id}` | Retrieve streamed result |
| POST | `/flow/{slug}` | Execute user pipeline |
| POST | `/flow/{slug}/debug` | Debug single pipeline step |
| GET | `/flows` | List user pipelines |
| POST | `/flows` | Create pipeline |
| DELETE | `/flows/{id}` | Delete pipeline |
| POST | `/batch` | Create batch job |
| GET | `/batch`, `/batch/{id}` | Batch status |
| GET | `/batch/{id}/download` | Download batch results |
| GET | `/quality-gate` | YES/NO evaluation |
| POST | `/moderation/check-image` | Moderation decision |
| POST | `/v1/eval/run` | Manual eval against profile |
| GET | `/account/balance` | Account balance |
| POST | `/account/create-checkout` | Payment |

## Authentication

**Header**: `X-API-Key: ak_xxxxxxx...`  
**Obtained via**: `POST /login` (email) → `POST /verify` (6-digit code)

## Response Headers

- `X-Request-ID` — UUID identifier
- `X-Processing-Time` — milliseconds
- `X-Cost` — USD charge
- `X-Balance-Remaining` — post-request balance
- `X-Workflow`, `X-Pipeline-Steps` — execution metadata

## Error Format

Standard: `{ "error": "description" }`  
Dedicated endpoints (`/v1/*`): `{ "error": "...", "code": "ERROR_CODE" }`

## Pricing Notes

- Most tools: fixed per-request cost
- Formula-priced tools: cost varies by params (metered), with `min`/`max` bounds
- Quality Gate / Moderation: ~$0.001 per evaluation
- Auto-Eval: $0.02 per evaluation (configurable)
