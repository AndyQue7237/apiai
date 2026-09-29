<!-- Extracted from the saved apiai.me Admin Console (#flow-modal) by docs/tools/extract_admin_html.py. Structure only; sanitized. -->

#### Add Pipeline Active Template Copyable
- `input[hidden] id="flow-id"`
- **Name** `input[text] id="flow-name" placeholder="e.g. Logo Digitalize Pipeline"`
- **Slug (URL path)** `input[text] id="flow-slug" placeholder="e.g. logo-digitalize"`
- **Description** `input[text] id="flow-desc" placeholder="What this pipeline does end-to-end"`
- **Preview image (optional — shown on the template card)**
- `input[text] id="flow-preview-url" placeholder="/static/marketing/preview-name.webp"`
- `input[file] id="flow-preview-file"`
[button: Upload]
Tick
Template
above to offer this as a starter in every user's My Pipelines, where they can copy it and edit their own version. Templates may only use tools that are granted globally — saving tells you which ones are missing.
Click a workflow to add it as a node. Configure each parameter as
Expose
(user provides via API),
Fixed
(baked in),
Wire ← prev
(from previous node output),
Default
, or
Omit
(remove from request).
- **Available Workflows**
- **Pipeline Nodes**
/modal-body
[button: Cancel]
[button: Save]
