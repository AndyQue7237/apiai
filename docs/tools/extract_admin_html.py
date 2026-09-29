"""Extract selected tabs and modals of a saved apiai.me Admin Console page into
sanitized Markdown outlines (how the admin works: sections, forms, fields, help texts).

Removed: all <script>/<style> (implementation), secrets, e-mails, IPs, and every
data row in people-related sections (only structure and counts are kept).

Usage: python3 docs/tools/extract_admin_html.py "docs/html/apiai.me — Admin Console.html"
Output: docs/html/extracted/<name>.md
"""
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).parent))
from sanitize_export import SECRET_VALUE_RE  # noqa: E402

# Output name -> element id. PII sections keep no repeated items / table rows.
SECTIONS = {
    "apis": "sec-workflows",
    "pipelines": "sec-flows",
    "scripts": "sec-scripts",
    "servers": "sec-servers",
    "users": "sec-users",
    "access-control": "sec-access",
    "usage-billing": "sec-usage",
    "monitor": "sec-monitor",
}
MODALS = {
    "modal-add-api": "wf-modal",
    "modal-add-server": "srv-modal",
    "modal-add-script": "script-modal",
    "modal-test-script": "script-test-modal",
    "modal-add-pipeline": "flow-modal",
    "modal-test-pipeline": "flow-test-modal",
}
PII_SECTIONS = {"users", "access-control", "usage-billing", "monitor"}
# Containers that hold records about people/customers.
#   "omit":     only the item count is kept
#   "template": the first item is kept as a shape (controls, buttons, labels), no values
DATA_CONTAINERS = {
    "admin-users-table": "omit",
    "blocked-domains-table": "omit",
    "signup-refusals-table": "omit",
    "users-domains": "omit",
    "users-table": "template",
    "access-table": "omit",
    "global-access-table": "omit",
}
SKIP_TAGS = {"script", "style", "svg", "noscript", "template"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")
IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
KEEP_REPEATED = 2  # items kept from a repeated list in non-PII sections
# Selects whose options are people/customers: only the option count is kept
ENTITY_SELECTS = {"access-user", "org-access-select"}


def clean(text):
    text = re.sub(r"\s+", " ", text).strip()
    text = SECRET_VALUE_RE.sub("<REDACTED>", text)
    text = EMAIL_RE.sub("<email>", text)
    return IP_RE.sub("<ip>", text)


def describe_control(el):
    """One-line description of an input/select/textarea."""
    attrs = []
    if el.name == "select" and el.get("id") in ENTITY_SELECTS:
        opts = [clean(o.get_text()) for o in el.find_all("option")]
        attrs.append(f"select: {opts[0] if opts else ''} | …({len(opts) - 1} options omitted: PII)")
    elif el.name == "select":
        opts = [clean(o.get_text()) for o in el.find_all("option")]
        attrs.append("select: " + " | ".join(o for o in opts[:25] if o)
                     + (f" | …(+{len(opts) - 25})" if len(opts) > 25 else ""))
    elif el.name == "textarea":
        attrs.append("textarea")
    else:
        kind = el.get("type", "text")
        attrs.append(f"input[{kind}]")
        if kind in ("checkbox", "radio"):
            attrs.append("checked" if el.has_attr("checked") else "unchecked")
    for a in ("id", "name", "placeholder", "title", "min", "max", "step"):
        if el.get(a):
            attrs.append(f'{a}="{clean(el[a])}"')
    return "`" + " ".join(attrs) + "`"


def class_sig(el):
    return (el.name, tuple(el.get("class", [])))


class Outliner:
    def __init__(self, pii, collapse=True, shape_only=False):
        self.pii = pii
        self.shape_only = shape_only  # drop free text (values); keep controls/buttons/labels
        self.collapse = collapse  # forms (modals) are never collapsed, only data lists
        self.lines = []
        self.consumed = set()

    def emit(self, line, depth):
        line = line.rstrip()
        if line and (not self.lines or self.lines[-1] != "  " * depth + line):
            self.lines.append("  " * depth + line)

    def walk(self, el, depth=0):
        if isinstance(el, NavigableString):
            text = clean(str(el))
            if text and not self.shape_only:
                self.emit(text, depth)
            return
        if not isinstance(el, Tag) or el.name in SKIP_TAGS or id(el) in self.consumed:
            return
        name = el.name
        mode = DATA_CONTAINERS.get(el.get("id")) if self.pii else None
        if mode:
            self.data_container(el, mode, depth)
            return
        if name in ("h1", "h2", "h3", "h4", "h5"):
            self.emit("", 0)
            self.emit("#" * (int(name[1]) + 1) + " " + clean(el.get_text(" ")), 0)
            return
        if name == "label":
            self.label(el, depth)
            return
        if name in ("input", "select", "textarea"):
            self.emit("- " + describe_control(el), depth)
            return
        if name == "button":
            text = clean(el.get_text(" ")) or el.get("title", "")
            if text:
                self.emit(f"[button: {clean(text)}]", depth)
            return
        if name == "table":
            self.table(el, depth)
            return
        self.children(el, depth)

    def data_container(self, el, mode, depth):
        items = el.find_all(recursive=False)
        while 0 < len(items) <= 3:  # header/wrapper level: descend into the largest child
            biggest = max(items, key=lambda k: len(k.find_all(recursive=False)))
            if len(biggest.find_all(recursive=False)) <= len(items):
                break
            items = biggest.find_all(recursive=False)
        self.emit(f"[data: #{el['id']} — {len(items)} items, values omitted (PII)]", depth)
        if mode == "template" and items:
            self.emit("shape of one item (controls and actions only):", depth)
            shape = Outliner(pii=True, collapse=False, shape_only=True)
            # Lists mix headers (e.g. per-day) with records; the record has the most actions
            shape.walk(max(items, key=lambda k: len(k.find_all("button"))), 0)
            for line in shape.lines:
                self.emit(line, depth + 1)

    def label(self, el, depth):
        control = el.find(["input", "select", "textarea"])
        if control is None and el.get("for"):
            control = el.find_parent("body").find(id=el["for"]) if el.find_parent("body") else None
        if control is None:
            sib = el.find_next_sibling()
            if sib is not None and sib.name in ("input", "select", "textarea"):
                control = sib
        text = clean(el.get_text(" "))
        if control is not None:
            self.consumed.add(id(control))
            self.emit(f"- **{text}** {describe_control(control)}", depth)
        else:
            self.emit(f"- **{text}**", depth)

    def table(self, el, depth):
        headers = [clean(th.get_text(" ")) for th in el.find_all("th")]
        rows = [tr for tr in el.find_all("tr") if tr.find("td")]
        self.emit(f"[table] columns: {' | '.join(headers) or '?'} — {len(rows)} rows", depth)
        if not self.pii:
            for tr in rows[:KEEP_REPEATED]:
                self.emit("row: " + " | ".join(clean(td.get_text(" ")) for td in tr.find_all("td")), depth + 1)

    def children(self, el, depth):
        kids = [k for k in el.children if isinstance(k, Tag) or clean(str(k))]
        tags = [k for k in kids if isinstance(k, Tag)]
        sigs = [class_sig(k) for k in tags]
        repeated = {s for s in set(sigs) if self.collapse and sigs.count(s) > 4 and s[1]}
        shown = {s: 0 for s in repeated}
        for k in kids:
            if isinstance(k, Tag) and class_sig(k) in repeated:
                s = class_sig(k)
                shown[s] += 1
                limit = 0 if self.pii else KEEP_REPEATED
                if shown[s] <= limit:
                    self.walk(k, depth + 1)
                elif shown[s] == limit + 1:
                    total = sigs.count(s)
                    why = ""
                    self.emit(f"…({total - limit} more `{'.'.join(s[1])}` items){why}", depth + 1)
                continue
            self.walk(k, depth)


def main(src):
    soup = BeautifulSoup(Path(src).read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for t in soup.find_all(list(SKIP_TAGS)):
        t.decompose()
    out = Path(src).parent / "extracted"
    out.mkdir(exist_ok=True)
    for name, el_id in {**SECTIONS, **MODALS}.items():
        el = soup.find(id=el_id)
        if el is None:
            print(f"  missing: {el_id}")
            continue
        o = Outliner(pii=name in PII_SECTIONS, collapse=name in SECTIONS)
        o.walk(el)
        header = (f"<!-- Extracted from the saved apiai.me Admin Console (#{el_id}) by "
                  f"docs/tools/extract_admin_html.py. Structure only; sanitized. -->\n\n")
        text = header + "\n".join(o.lines).strip() + "\n"
        (out / f"{name}.md").write_text(text)
        leaks = EMAIL_RE.findall(text) + SECRET_VALUE_RE.findall(text)
        print(f"  {name:22} {len(o.lines):4} lines{'  LEAK!' if leaks else ''}")


if __name__ == "__main__":
    main(sys.argv[1])
