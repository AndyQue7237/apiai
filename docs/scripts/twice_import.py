#!/usr/bin/env python3
"""Import items from a ZIP bundle into a Twice commerce store.

Receives the ZIP produced by item_crop_zip.py as input (via pipeline or
direct upload). Reads items.json and item images from the ZIP, then for
each item:

  1. Uploads the image  → POST /internal/files/create
  2. Resolves taxonomy  → GET  /internal/taxonomy/categories/find/<text>
  3. Creates article    → POST /internal/articles
  4. Sets description / condition / price  → PUT /internal/articles/{id}

Returns JSON with a per-item result array and summary counts.

Params:
  twice_api_key         — Twice API key (sk_…)                [required]
  twice_service_loc_id  — Service location UUID               [required]
  twice_api             — API base URL (default: https://server.dev.twicecommerce.com)
  twice_status          — Article status: draft|active (default: draft)
  dry_run               — If "true", plan only — no API calls (default: false)
"""
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "twice_api_key", "description": "Twice API key (sk_…)", "default_value": "", "required": True},
    {"name": "twice_service_loc_id", "description": "Twice service location UUID", "default_value": "", "required": True},
    {"name": "twice_api", "description": "Twice API base URL", "default_value": "https://server.dev.twicecommerce.com"},
    {"name": "twice_status", "description": "Article status on creation", "default_value": "draft",
     "allowed_values": ["draft", "active"]},
    {"name": "dry_run", "description": "If true, plan only — no API calls", "default_value": "false",
     "allowed_values": ["true", "false"]},
]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(method, url, *, api_key, body_bytes=None, content_type=None):
    """Make an HTTP request; return parsed JSON. Raises on non-2xx."""
    headers = {"x-api-key": api_key}
    if content_type:
        headers["content-type"] = content_type
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            detail = json.loads(raw)
            snippet = json.dumps(detail)[:400]
        except Exception:
            snippet = raw.decode(errors="replace")[:400]
        raise RuntimeError(f"{method} {url} → {e.code}: {snippet}") from None
    return json.loads(raw) if raw else None


def _api_get(path, api_base, api_key):
    return _request("GET", api_base + path, api_key=api_key)


def _api_post(path, api_base, api_key, body):
    data = json.dumps(body).encode()
    return _request("POST", api_base + path, api_key=api_key,
                    body_bytes=data, content_type="application/json")


def _api_put(path, api_base, api_key, body):
    data = json.dumps(body).encode()
    return _request("PUT", api_base + path, api_key=api_key,
                    body_bytes=data, content_type="application/json")


def _multipart_body(filename, image_bytes, mime_type="image/jpeg"):
    """Build a multipart/form-data body with a single 'files' field."""
    boundary = uuid.uuid4().hex
    ctype = f"multipart/form-data; boundary={boundary}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode() + image_bytes + f"\r\n--{boundary}--\r\n".encode()
    return body, ctype


# ── Twice API calls ───────────────────────────────────────────────────────────

def upload_image(filename, image_bytes, api_base, api_key):
    """Upload one image; return the file row (has .id)."""
    body, ctype = _multipart_body(filename, image_bytes)
    result = _request("POST", api_base + "/internal/files/create",
                      api_key=api_key, body_bytes=body, content_type=ctype)
    first = result[0] if isinstance(result, list) else result
    if not first.get("success"):
        raise RuntimeError(f"upload failed for {filename}: {first.get('error', 'unknown')}")
    return first["data"]


def find_taxonomy_category(text, api_base, api_key):
    """Return best-matching taxonomy category dict or None."""
    if not text.strip():
        return None
    encoded = urllib.parse.quote(text.strip(), safe="")
    try:
        rows = _api_get(f"/internal/taxonomy/categories/find/{encoded}", api_base, api_key)
    except RuntimeError as e:
        print(f"    taxonomy lookup failed: {e}", file=sys.stderr)
        return None
    if not isinstance(rows, list) or not rows:
        return None
    return rows[0]


def create_article(name, file_ids, taxonomy_category_id, service_location_id, status, api_base, api_key):
    body = {
        "article": {
            "name": name,
            "status": status,
            "serviceLocationId": service_location_id,
            "taxonomyCategoryId": taxonomy_category_id,
        },
    }
    if file_ids:
        body["fileIds"] = file_ids
    result = _api_post("/internal/articles", api_base, api_key, body)
    return result[0] if isinstance(result, list) else result


def update_article(article_id, description, condition, purchase_price_minor, api_base, api_key):
    body = {}
    if description is not None:
        body["description"] = description
    if condition is not None:
        body["condition"] = condition
    if purchase_price_minor is not None:
        body["purchasePrice"] = purchase_price_minor
    if body:
        _api_put(f"/internal/articles/{article_id}", api_base, api_key, body)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    input_bytes, _content_type, params = read_input()

    if not input_bytes:
        write_error("no input provided — expected a ZIP file from item_crop_zip")
        return

    api_key = params.get("twice_api_key", "").strip()
    service_loc_id = params.get("twice_service_loc_id", "").strip()
    if not api_key:
        write_error("twice_api_key param is required")
        return
    if not service_loc_id:
        write_error("twice_service_loc_id param is required")
        return

    api_base = params.get("twice_api", "https://server.dev.twicecommerce.com").rstrip("/")
    status = params.get("twice_status", "draft")
    dry_run = params.get("dry_run", "false").lower() == "true"

    # Open the ZIP
    try:
        zf = zipfile.ZipFile(io.BytesIO(input_bytes))
    except Exception as e:
        write_error(f"failed to open ZIP: {e}")
        return

    # Read items.json from ZIP
    try:
        items = json.loads(zf.read("items.json"))
    except Exception as e:
        write_error(f"failed to read items.json from ZIP: {e}")
        return

    results = []
    ok = failed = 0

    for item in items:
        name = item.get("name") or ""
        label = f"[{item.get('id', '?')}] {name or '(no name)'}"

        if not name:
            print(f"{label} — skipped: no name", file=sys.stderr)
            results.append({"name": None, "status": "skipped", "reason": "missing name"})
            failed += 1
            continue

        image_file = item.get("image_file")
        description = item.get("description") or None
        condition = item.get("condition") or None
        value_sek = item.get("estimated_value_sek")
        purchase_price_minor = None
        if value_sek is not None:
            try:
                purchase_price_minor = int(value_sek)
            except (TypeError, ValueError):
                pass

        # Build taxonomy search text
        parts = [p for p in (name, description) if p]
        taxonomy_text = ". ".join(parts)

        try:
            if dry_run:
                cat = find_taxonomy_category(taxonomy_text, api_base, api_key)
                print(
                    f"{label} — plan: image={image_file or '-'}, "
                    f"price={purchase_price_minor or '-'}, condition={condition or '-'}, "
                    f"category={cat['fullName'] if cat else '(none)'}",
                    file=sys.stderr,
                )
                results.append({
                    "name": name,
                    "status": "dry-run",
                    "taxonomyCategoryId": cat["id"] if cat else None,
                    "taxonomyCategoryName": cat["fullName"] if cat else None,
                })
                continue

            # 1. Upload image
            file_ids = []
            if image_file:
                try:
                    img_bytes = zf.read(image_file)
                    file_row = upload_image(image_file, img_bytes, api_base, api_key)
                    file_ids = [file_row["id"]]
                    print(f"{label} — uploaded {image_file} → {file_row['id']}", file=sys.stderr)
                except Exception as e:
                    print(f"{label} — image upload failed: {e}", file=sys.stderr)
                    # Proceed without image rather than failing the whole item
            else:
                print(f"{label} — no image", file=sys.stderr)

            # 2. Resolve taxonomy
            cat = None
            if item.get("taxonomy_category_id"):
                cat = {"id": item["taxonomy_category_id"], "fullName": "(provided)"}
            else:
                cat = find_taxonomy_category(taxonomy_text, api_base, api_key)
            if cat:
                print(f"{label} — category: {cat['fullName']}", file=sys.stderr)
            else:
                print(f"{label} — no taxonomy match", file=sys.stderr)

            # 3. Create article
            created = create_article(
                name=name,
                file_ids=file_ids,
                taxonomy_category_id=cat["id"] if cat else None,
                service_location_id=service_loc_id,
                status=status,
                api_base=api_base,
                api_key=api_key,
            )
            article_id = created["id"]
            print(f"{label} — created article {article_id}", file=sys.stderr)

            # 4. Set description / condition / price
            update_article(article_id, description, condition, purchase_price_minor, api_base, api_key)
            print(f"{label} — updated metadata", file=sys.stderr)

            results.append({
                "name": name,
                "status": "ok",
                "articleId": article_id,
                "fileId": file_ids[0] if file_ids else None,
                "taxonomyCategoryId": cat["id"] if cat else None,
                "taxonomyCategoryName": cat["fullName"] if cat else None,
            })
            ok += 1

        except Exception as e:
            print(f"{label} — FAILED: {e}", file=sys.stderr)
            results.append({"name": name, "status": "error", "error": str(e)})
            failed += 1

    summary = {"ok": ok, "failed": failed, "total": len(results), "items": results}
    output_json = json.dumps(summary, ensure_ascii=False, indent=2).encode()

    write_output(
        output_json,
        "application/json",
        ok=ok,
        failed=failed,
        total=len(results),
    )


if __name__ == "__main__":
    main()
