<!-- Extracted from the saved apiai.me Admin Console (#sec-users) by docs/tools/extract_admin_html.py. Structure only; sanitized. -->

Admin Users
### Admin Users
[button: + Add Admin]
- `input[email] id="new-admin-email" placeholder="<email>"`
- `input[text] id="new-admin-name" placeholder="Name"`
[button: Add]
[button: Cancel]
[data: #admin-users-table — 3 items, values omitted (PII)]
Sign-up abuse: blocked email domains
### Blocked Sign-up Domains
[button: Refresh]
Registrations from these email domains are silently refused. Domains that reach 3 verified sign-ups in 24 hours are added automatically; the public disposable-mail list is compiled in and not shown here. Sign-up IPs are shown on each user card below.
- `input[text] id="block-domain-input" placeholder="example.org"`
- `input[text] id="block-domain-reason" placeholder="reason (optional)"`
[button: Block]
[data: #blocked-domains-table — 2 items, values omitted (PII)]
#### Refused sign-ups
- `select: Last 24 hours | Last 7 days | Last 30 days id="refusals-hours"`
[data: #signup-refusals-table — 1 items, values omitted (PII)]
Regular Users
### Registered Users
[button: + Add User]
- `input[email] id="new-user-email" placeholder="<email>"`
- `input[text] id="new-user-company" placeholder="Company name"`
[button: Create & Send Code]
[button: Cancel]
- `input[search] id="users-search" placeholder="Search email, name, company, IP…"`
- `select: All users | Verified only | Never entered a code | Balance above $0 | Trial credit held | Suspended id="users-filter"`
185 users · 3 never entered a code
[data: #users-domains — 8 items, values omitted (PII)]
[data: #users-table — 30 items, values omitted (PII)]
shape of one item (controls and actions only):
  [button: ✎]
  [button: Grant trial]
  [button: Decline]
  [button: Suspend]
