<!-- Extracted from the saved apiai.me Admin Console (#sec-access) by docs/tools/extract_admin_html.py. Structure only; sanitized. -->

Global Access Card
### Global Access ALL USERS
APIs granted here are accessible to every registered user automatically — no per‑user setup needed.
- **Add to Global Access**
- `input[text] id="global-access-search" placeholder="Search APIs or pipelines..."`
[button: Select All]
[button: Clear]
0 selected
  …(114 more `grant-list-item.api-row` items)
[button: Grant Selected to All Users]
[data: #global-access-table — 74 items, values omitted (PII)]
Per-User Access Card
### Per‑User Access
Grant specific APIs to individual users in addition to any global access.
- **Select User** `select: — choose user — | …(185 options omitted: PII) id="access-user"`
- **Grant API Access**
- `input[text] id="access-workflow-search" placeholder="Search APIs or pipelines..."`
[button: Select All]
[button: Clear]
0 selected
[button: Grant Selected]
  …(114 more `grant-list-item.api-row` items)
[data: #access-table — 1 items, values omitted (PII)]
Team (Org) Pipeline Access Card
### Team Access
Grant pipeline access to an entire team. All current and future members automatically inherit access.
- **Select Team** `select: — choose team — | …(4 options omitted: PII) id="org-access-select"`
- **Grant Pipeline Access**
- `input[text] id="org-pipeline-search" placeholder="Search pipelines..."`
[button: Select All]
[button: Clear]
0 selected
[button: Grant Selected]
  …(27 more `grant-list-item.api-row` items)
Select a team above to see their pipeline access.
