"""Local stand-in for the apiai.me runtime's `script_io`.

The node scripts import this from the platform runtime; it is not in this repo, so without it
they cannot be driven locally at all. The contract is documented in
`apiai-tools/SCRIPT_GUIDELINES.md` §4 and this implements exactly that, nothing more:

    stdin:  {"image": "<base64>", "content_type": "image/png", "params": {...}}
    stdout: {"image": "<base64>", "content_type": "image/png", ...extra root fields}

Dev-only. It must never be uploaded with a node — the platform has its own.
"""
import base64
import json
import sys

_input = None


def read_input():
    global _input
    _input = json.load(sys.stdin)
    img = _input.get("image") or ""
    raw = base64.b64decode(img) if img else b""
    return raw, _input.get("content_type", "image/png"), _input.get("params", {}) or {}


def write_output(image_bytes, content_type="image/png", **extra):
    out = {"image": base64.b64encode(image_bytes).decode(), "content_type": content_type}
    out.update(extra)
    json.dump(out, sys.stdout)
    sys.stdout.flush()


def write_error(message):
    json.dump({"error": str(message)}, sys.stdout)
    sys.stdout.flush()
    sys.exit(1)
