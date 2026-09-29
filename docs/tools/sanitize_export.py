"""Write a copy of an apiai.me admin export with all secrets redacted.

The raw export stores provider API keys in plain text (servers[].config.api_key).
The raw file is gitignored; only the sanitized copy is committed.

Usage: python3 docs/tools/sanitize_export.py docs/export/<raw>.json
Output: docs/export/<raw>.sanitized.json
"""
import json
import re
import sys
from pathlib import Path

SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|bearer|credential)", re.I)
SECRET_VALUE_RE = re.compile(
    r"(sk-(proj|ant)-[A-Za-z0-9_-]{20,}|r8_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}"
    r"|xai-[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|(sk|rk)_(live|test)_[A-Za-z0-9]{10,}"
    r"|ak_[A-Za-z0-9]{16,})"  # apiai.me user API keys
)
REDACTED = "<REDACTED>"


def redact(obj):
    """Recursively redact secret-named keys and secret-looking string values."""
    if isinstance(obj, dict):
        return {
            k: REDACTED if SECRET_KEY_RE.search(k) and isinstance(v, str) and v else redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        return SECRET_VALUE_RE.sub(REDACTED, obj)
    return obj


def main(src):
    src = Path(src)
    dst = src.with_suffix(".sanitized.json")
    clean = redact(json.loads(src.read_text()))
    text = json.dumps(clean, indent=2, ensure_ascii=False)
    leftovers = SECRET_VALUE_RE.findall(text)
    if leftovers:
        sys.exit(f"Secrets still present after redaction: {len(leftovers)}")
    dst.write_text(text + "\n")
    print(f"Wrote {dst} ({text.count(REDACTED)} redactions)")


if __name__ == "__main__":
    main(sys.argv[1])
