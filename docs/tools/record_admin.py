"""Record an authenticated apiai.me session for documentation.

Opens a visible browser. You log in and click through the pages you want documented;
the script records, until you close the browser window:

- every JSON response from the target host (the data behind the SPA: flows, nodes,
  prompts, params, costs), with method, status, request body and X-Cost header
- the visible text of each page state (on URL change or significant DOM change)
- a screenshot per page state (disable with --no-screenshots)

All JSON and text is sanitized with the same rules as sanitize_export.py before it
is written. Screenshots cannot be sanitized — review them before sharing/committing.

Usage:
    python3 docs/tools/record_admin.py https://apiai.me/admin --label admin
    python3 docs/tools/record_admin.py https://apiai.me/dashboard --label user
Output: docs/crawl/<label>/{api,pages}/ + log.md
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from sanitize_export import SECRET_VALUE_RE, REDACTED, redact  # noqa: E402

DOCS = Path(__file__).resolve().parents[1]
POLL_MS = 1000
MIN_TEXT_CHANGE = 40  # chars; smaller DOM changes (timers, spinners) are ignored


def slugify(text, max_len=60):
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:max_len] or "root"


def sanitize_text(text):
    return SECRET_VALUE_RE.sub(REDACTED, text)


def parse_json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


class Recorder:
    def __init__(self, out_dir, host, screenshots):
        self.out = out_dir
        self.host = host
        self.screenshots = screenshots
        self.pending = []
        self.seen_bodies = set()
        self.n_api = 0
        self.n_page = 0
        (out_dir / "api").mkdir(parents=True, exist_ok=True)
        (out_dir / "pages").mkdir(parents=True, exist_ok=True)
        self.log = open(out_dir / "log.md", "a")
        self.log.write(f"\n## Session {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    def on_response(self, response):
        # Only queue here; reading bodies inside the event handler can deadlock (sync API)
        if urlparse(response.url).hostname == self.host:
            self.pending.append(response)

    def flush_responses(self):
        while self.pending:
            response = self.pending.pop(0)
            try:
                if "json" not in (response.headers.get("content-type") or ""):
                    continue
                body = response.text()
            except Exception:
                continue  # body gone (redirect, navigation) — nothing to save
            request = response.request
            key = hashlib.sha1(f"{request.method} {response.url} {body}".encode()).hexdigest()
            if key in self.seen_bodies:
                continue
            self.seen_bodies.add(key)
            self.n_api += 1
            parsed = urlparse(response.url)
            record = {
                "method": request.method,
                "url": sanitize_text(response.url),
                "status": response.status,
                "x_cost": response.headers.get("x-cost"),
                "request_body": redact(parse_json(request.post_data) or request.post_data),
                "response": redact(parse_json(body)),
            }
            name = f"{self.n_api:04d}_{request.method}_{slugify(parsed.path)}.json"
            (self.out / "api" / name).write_text(json.dumps(record, indent=2, ensure_ascii=False))
            self.log.write(f"- api `{name}` {response.status} {request.method} {parsed.path}\n")
            print(f"  api  {request.method} {parsed.path} ({response.status})")

    def snapshot(self, page, text):
        self.n_page += 1
        base = f"{self.n_page:04d}_{slugify(urlparse(page.url).path)}"
        header = f"URL: {sanitize_text(page.url)}\nTitle: {page.title()}\n\n"
        (self.out / "pages" / f"{base}.txt").write_text(header + sanitize_text(text))
        if self.screenshots:
            page.screenshot(path=str(self.out / "pages" / f"{base}.png"), full_page=True)
        self.log.write(f"- page `{base}` {sanitize_text(page.url)}\n")
        print(f"  page {page.url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="Start URL (login happens here)")
    parser.add_argument("--label", required=True, help="Output folder name, e.g. admin / user")
    parser.add_argument("--no-screenshots", action="store_true")
    args = parser.parse_args()

    out_dir = DOCS / "crawl" / args.label
    host = urlparse(args.url).hostname
    rec = Recorder(out_dir, host, screenshots=not args.no_screenshots)

    print(f"Recording {host} -> {out_dir}")
    print("Log in and click through everything worth documenting.")
    print("Open node/step settings too — modal contents are captured on DOM change.")
    print("CLOSE THE BROWSER WINDOW when done.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.on("response", rec.on_response)
        page.goto(args.url)

        last_url, last_text = None, ""
        while not page.is_closed():
            try:
                page.wait_for_timeout(POLL_MS)
                rec.flush_responses()
                text = page.inner_text("body")
                changed = page.url != last_url or abs(len(text) - len(last_text)) >= MIN_TEXT_CHANGE
                if changed and text.strip():
                    rec.snapshot(page, text)
                    last_url, last_text = page.url, text
            except Exception as e:
                if page.is_closed() or "closed" in str(e).lower():
                    break
                # Mid-navigation errors are expected; try again next tick
        try:
            browser.close()
        except Exception:
            pass

    rec.log.close()
    print(f"\nDone: {rec.n_api} API responses, {rec.n_page} page states -> {out_dir}")


if __name__ == "__main__":
    main()
