<!-- Extracted from the saved apiai.me Admin Console (#script-modal) by docs/tools/extract_admin_html.py. Structure only; sanitized. -->

#### Add Script
- `input[hidden] id="script-id"`
- **Name (filename without .py)** `input[text] id="script-name" placeholder="e.g. logo_crop"`
- **Packages**
Loading…
- `input[hidden] id="script-reqs"`
- **Description** `input[text] id="script-desc" placeholder="What this script does"`
Available via os.environ:
- **Ask Claude** `textarea id="ai-assist-prompt" placeholder="e.g. "Create a script that converts an image to greyscale with an adjustable intensity parameter" or paste existing code below and ask "Add a brightness parameter with range 0-200""`
[button: Ask Claude]
[button: Fix it]
- **Source Code**
- **📂 Upload .py** `input[file] id="script-file-upload"`
- `textarea id="script-code" placeholder="#!/usr/bin/env python3"`
/modal-body
[button: Cancel]
[button: Save]
