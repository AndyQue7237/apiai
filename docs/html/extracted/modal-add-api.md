<!-- Extracted from the saved apiai.me Admin Console (#wf-modal) by docs/tools/extract_admin_html.py. Structure only; sanitized. -->

#### Add API Active Canva
- `input[hidden] id="wf-id"`
- **Name** `input[text] id="wf-name" placeholder="e.g. Image Crop"`
- **Slug (URL path)** `input[text] id="wf-slug" placeholder="auto-generated from name"`
- **Description** `input[text] id="wf-desc" placeholder="Short description of what this workflow does"`
- **AI Context (optional — extra guidance for the "?" help chat: known good param values, when to use, upstream model quirks, common failure modes)**
[button: Suggest]
- `textarea id="wf-ai-context" placeholder="e.g. Best for portraits shot in daylight. Setting margin above 15 introduces artefacts. Use this over Detect and Crop when the subject fills the frame."`
- **Category** `select: — Uncategorized — | AI Generation | Analysis | Background & Segmentation | Format & Export | Image Editing | Upscaling | Video | APIs | + Add new category... id="wf-category"`
- `input[text] id="wf-category-custom" placeholder="Type new category (e.g. filter)"`
- **Price per Request ($)** `input[number] id="wf-price" placeholder="0.0000" min="0" step="0.0001"`
Cost basis: what the provider bills us and the per-slug markup override. Neither is used at charge time; they make the margin visible so a tool we own (gate, background removal) can be priced on value, not cost+default.
- **Provider cost per request ($) (what the model bills us; blank = not recorded)** `input[number] id="wf-provider-cost" placeholder="blank" min="0" step="0.0001"`
- **Markup override (%) (blank = default from Pricing)** `input[number] id="wf-markup" placeholder="default" min="0" step="1"`
Parametric pricing rule (overrides the flat Price per Request above when enabled)
- **Use parametric pricing rule (charges based on request params, e.g. duration × resolution — falls back to flat price when off)** `input[checkbox] unchecked id="wf-pricing-rule-enabled"`
[button: Veo (request params)]
[button: Replicate-by-seconds (reconciled)]
[button: Token-based (LLM, not yet reconciled)]
[button: Flat]
- `textarea id="wf-pricing-rule-json" placeholder="{"kind":"formula","base":0.05,"min":0.10,"max":20.00,"linear":[{"param":"duration_sec","rate":0.50}],"multipliers":[{"param":"resolution","values":{"720p":1.0,"1080p":2.0,"4k":6.0},"default":1.0}]}"`
Empty — rule will be cleared on save.
Cost preview
Type sample params (one per line,
name=value
) to see the computed cost.
- `textarea id="wf-pricing-rule-sample" placeholder="duration_sec=8 resolution=1080p num_outputs=1"`
$ —
- **Server** `select: — default (first active) — | Pyton Scripts (python) | Replicate (replicate) | Gemini (gemini) | GROK (xai) | GROK Video (xai) | Gemini Video (gemini) | OpenAI (openai) id="wf-server"`
I/O Type Declarations
- **Accepted Inputs (click to cycle: off → optional → required)**
[button: Image]
[button: Video]
[button: Text / JSON]
[button: Audio]
- **Output Type**
[button: Image]
[button: Video]
[button: Text / JSON]
[button: Audio]
[button: ZIP]
- **Max Images (how many image files the primary input accepts — 1 = single, higher = multi-file)** `input[number] id="wf-max-images" min="1" max="20"`
- **Workflow JSON (ComfyUI API format)**
- **📂 Upload JSON file** `input[file] id="wf-file"`
- `textarea id="wf-json" placeholder="Or paste workflow JSON here manually."`
The loader will auto-replace the LoadImage input with
{{INPUT_IMAGE}}
. Use
{{PARAM_NAME}}
placeholders for configurable parameters.
Write your prompt for the Gemini model. Use
{{PARAM_NAME}}
placeholders for configurable parameters and
{{PROMPT}}
for customer-supplied ad-hoc prompts.
- **Gemini Model**
- `select: — click Fetch Models — id="wf-gemini-model"`
[button: Fetch Models]
- **Response Type** `select: Image | Video | Text | Auto (Image + Text) id="wf-gemini-response-type"`
- **Generation Config**
- **Temperature** `input[number] id="wf-gemini-temperature" placeholder="model default" min="0" max="2" step="0.05"`
- **Top-P** `input[number] id="wf-gemini-top-p" placeholder="model default" min="0" max="1" step="0.05"`
- **Top-K** `input[number] id="wf-gemini-top-k" placeholder="model default" min="1" step="1"`
- **Max Output Tokens** `input[number] id="wf-gemini-max-tokens" placeholder="model default" min="1" step="1"`
- **Image Generation Defaults**
- **Aspect Ratio** `select: caller default | 1:1 | 3:4 (portrait) | 4:3 (landscape) | 9:16 (tall) | 16:9 (wide) id="wf-gemini-aspect-ratio"`
- **Image Size** `select: caller default | 512 | 1K | 2K | 4K id="wf-gemini-image-size"`
- **Num Images** `input[number] id="wf-gemini-num-images" placeholder="1" min="1" max="4" step="1"`
- **Safety Filter** `select: caller default | Block low+ | Block medium+ | Block only high | Off id="wf-gemini-safety-filter"`
- **Negative Prompt** `input[text] id="wf-gemini-negative-prompt" placeholder="Elements to exclude from generated images…"`
- **Grok Model**
- `select: — click Fetch Models — id="wf-xai-model"`
[button: Fetch Models]
- **Response Type** `select: Text | Image | Video | Auto id="wf-xai-response-type"`
- **Generation Config**
- **Temperature** `input[number] id="wf-xai-temperature" placeholder="model default" min="0" max="2" step="0.05"`
- **Top-P** `input[number] id="wf-xai-top-p" placeholder="model default" min="0" max="1" step="0.05"`
- **Max Tokens** `input[number] id="wf-xai-max-tokens" placeholder="model default" min="1" step="1"`
- **Freq. Penalty** `input[number] id="wf-xai-freq-penalty" placeholder="0" min="-2" max="2" step="0.1"`
- **Pres. Penalty** `input[number] id="wf-xai-pres-penalty" placeholder="0" min="-2" max="2" step="0.1"`
Write your prompt for the Grok model. Use
{{PARAM_NAME}}
placeholders for configurable parameters and
{{PROMPT}}
for customer-supplied ad-hoc prompts.
- **OpenAI Model**
- `select: — click Fetch Models — id="wf-openai-model"`
[button: Fetch Models]
- **Response Type** `select: Text | Image id="wf-openai-response-type"`
- **Generation Config**
- **Temperature** `input[number] id="wf-openai-temperature" placeholder="model default" min="0" max="2" step="0.05"`
- **Top-P** `input[number] id="wf-openai-top-p" placeholder="model default" min="0" max="1" step="0.05"`
- **Max Tokens** `input[number] id="wf-openai-max-tokens" placeholder="model default" min="1" step="1"`
- **Freq. Penalty** `input[number] id="wf-openai-freq-penalty" placeholder="0" min="-2" max="2" step="0.1"`
- **Pres. Penalty** `input[number] id="wf-openai-pres-penalty" placeholder="0" min="-2" max="2" step="0.1"`
- **Image Config**
- **Size** `select: auto | 1024×1024 | 1536×1024 (landscape) | 1024×1536 (portrait) | 1792×1024 (dall-e-3) | 1024×1792 (dall-e-3) id="wf-openai-size"`
- **Quality** `select: default | Standard | HD | Low | Medium | High | Auto id="wf-openai-quality"`
- **Background** `select: default | Transparent | Opaque | Auto id="wf-openai-background"`
- **Style** `select: default | Vivid | Natural id="wf-openai-style"`
Write your prompt for the OpenAI model. Use
{{PARAM_NAME}}
placeholders for configurable parameters and
{{PROMPT}}
for customer-supplied ad-hoc prompts.
Search the Replicate catalog or enter a model ID directly and click
Fetch Schema
to auto-discover the model's inputs.
Parameters are automatically mapped to canonical API names (e.g.
prompt
,
image
).
- **Search Replicate Models**
- `input[text] id="wf-replicate-search" placeholder="e.g. flux, remove background, video generation…"`
[button: Search]
- **Replicate Model ID**
- `input[text] id="wf-replicate-model" placeholder="e.g. bytedance/seedream-4"`
[button: Fetch Schema]
- **Image Field** `input[text] id="wf-replicate-image-field" placeholder="auto-detect" title="Which input field receives the uploaded image (leave blank for auto-detect)"`
- **Image Upload (Auto: Data URL for video, Files API for image — override only if a model misbehaves)** `select: Auto (Data URL for video, Files API otherwise) | Files API (force) | Data URL (force — embed bytes) id="wf-replicate-image-upload" title="How the uploaded image is delivered to Replicate. Auto handles the common case; override when a specific model needs the other path."`
- **Output Type** `select: Image (PNG/WebP) | Video (MP4) | Audio (MP3/WAV) | Text (JSON) id="wf-replicate-output-type"`
Select a script from the Scripts tab. Optionally set a timeout in seconds.
- **Script** `select: — select script — id="wf-python-script"`
- **Timeout (seconds)** `input[number] id="wf-python-timeout" placeholder="30" min="1" max="300"`
- **Output Type** `select: Image (PNG/WebP) | Video (MP4) | Audio (MP3/WAV) | Text (JSON) | ZIP Archive id="wf-python-response-type"`
Workflow Parameters
- **Parameters**
[button: Scan JSON]
[button: Scan Script]
[button: + Add]
Test Run Panel
##### Test Run
[button: Close]
- `input[file] id="wf-test-file"`
Drop image here or click to select
- **Prompt / Text Input** `textarea id="wf-test-prompt" placeholder="Optional prompt text..."`
- **Parameter Overrides**
[button: Run Test]
Execution Logs
▶
/modal-body
Pre-flight validation results. Filled by saveWorkflow() before anything is written, so a broken API is caught here rather than by a customer.
[button: Cancel]
[button: Test Run]
[button: Save]
