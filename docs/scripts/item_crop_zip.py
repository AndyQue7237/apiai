#!/usr/bin/env python3
"""Crop individual items from an image and return a ZIP bundle.

Receives the original image as INPUT_IMAGE and a JSON array (from an AI
vision step) via the 'items_json' param.  Each item must have a 'bbox'.

Supported bbox formats:
  - Gemini native list [y_min, x_min, y_max, x_max] values 0-1000
  - Dict {x, y, w, h} as percentages 0-100 (top-left + size)

Returns a ZIP file containing:
  items.json  — metadata array (id, name, description, category,
                condition, estimated_value_sek, image_file)
  item_0.jpg, item_1.jpg, ...  — one cropped JPEG per item

Params:
  items_json  — JSON string: array of item objects with bbox field
  padding     — extra padding % around each crop (default: 2)
  min_size    — minimum crop dimension in pixels (default: 64)
"""
import io
import json
import re
import zipfile

from PIL import Image
from script_io import read_input, write_output, write_error

PARAM_DEFS = [
    {"name": "items_json", "description": "JSON array of items with bbox fields (from AI vision step)", "default_value": ""},
    {"name": "padding", "description": "Extra padding percentage around each crop (0-20)", "default_value": "2"},
    {"name": "min_size", "description": "Minimum crop dimension in pixels", "default_value": "64"},
]


def extract_json_array(text):
    """Extract first JSON array of objects from a string that may contain prose or markdown fences."""
    # Strip all markdown code fence variants (```json, ```JSON, ```, etc.)
    text = re.sub(r"```[^\n]*\n?", "", text)
    text = re.sub(r"```", "", text).strip()

    # Try parsing the whole thing as JSON first — handles plain array or {"items":[...]} wrapper
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
    except Exception:
        pass

    # Try every '[' position and attempt to parse a valid JSON array of objects.
    # This handles cases where prose precedes the JSON, or Gemini wraps the bbox
    # in text before the items array.
    for m in re.finditer(r"\[", text):
        start = m.start()
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        result = json.loads(candidate)
                        if isinstance(result, list) and result and isinstance(result[0], dict):
                            return result
                    except json.JSONDecodeError:
                        pass
                    break  # move to next '[' position

    # Last resort: Gemini sometimes returns bare comma-separated objects with no enclosing [].
    # Try wrapping the entire stripped text in [] and parsing.
    wrapped = "[" + text + "]"
    try:
        result = json.loads(wrapped)
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return result
    except json.JSONDecodeError:
        pass

    raise ValueError("no JSON array of objects found in items_json")


def crop_item(img, bbox, padding_pct, min_size):
    """Return a cropped PIL Image for one item bbox.

    Accepts four bbox formats:
      - Gemini native list [y_min, x_min, y_max, x_max] values 0-1000
      - Gemini dict {y_min, x_min, y_max, x_max} values 0-1000
      - Pixel coords dict {x, y, w, h} where w > x (x2/y2 format)
      - Percentage dict {x, y, w, h} values 0-100 (top-left + size)
    """
    iw, ih = img.size

    if isinstance(bbox, list) and len(bbox) == 4:
        # Gemini native: [y_min, x_min, y_max, x_max], normalized 0-1000
        y1 = (bbox[0] / 1000) * ih
        x1 = (bbox[1] / 1000) * iw
        y2 = (bbox[2] / 1000) * ih
        x2 = (bbox[3] / 1000) * iw
    elif isinstance(bbox, dict) and all(k in bbox for k in ("y_min", "x_min", "y_max", "x_max")):
        # Gemini dict format: {y_min, x_min, y_max, x_max}, normalized 0-1000
        y1 = (bbox["y_min"] / 1000) * ih
        x1 = (bbox["x_min"] / 1000) * iw
        y2 = (bbox["y_max"] / 1000) * ih
        x2 = (bbox["x_max"] / 1000) * iw
    else:
        bx, by, bw, bh = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
        if bw > bx or bh > by:
            # Pixel x1,y1,x2,y2 format
            x1, y1, x2, y2 = bx, by, bw, bh
        else:
            # Percentage top-left + size format
            x1 = (bx / 100) * iw
            y1 = (by / 100) * ih
            x2 = ((bx + bw) / 100) * iw
            y2 = ((by + bh) / 100) * ih

    pad_x = iw * padding_pct / 100
    pad_y = ih * padding_pct / 100

    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(iw, x2 + pad_x)
    y2 = min(ih, y2 + pad_y)

    if (x2 - x1) < min_size or (y2 - y1) < min_size:
        return None

    return img.crop((int(x1), int(y1), int(x2), int(y2)))


def jpeg_bytes(img):
    """Encode a PIL Image as JPEG bytes."""
    buf = io.BytesIO()
    rgb = img.convert("RGB")
    rgb.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def main():
    input_bytes, content_type, params = read_input()

    if not input_bytes:
        write_error("no input image provided")
        return

    items_json_str = params.get("items_json", "").strip()
    # Also accept PREVIOUS_TEXT — the auto-injected output from a preceding text step
    if not items_json_str:
        items_json_str = params.get("PREVIOUS_TEXT", "").strip()
    if not items_json_str:
        write_error("items_json param is required")
        return

    try:
        padding = float(params.get("padding", 2))
        min_size = int(params.get("min_size", 64))
    except (ValueError, TypeError):
        write_error("padding and min_size must be numbers")
        return

    try:
        items = extract_json_array(items_json_str)
    except Exception as e:
        preview = repr(items_json_str[:500])
        write_error(f"failed to parse items_json: {e}\nreceived ({len(items_json_str)} chars): {preview}")
        return

    try:
        img = Image.open(io.BytesIO(input_bytes))
    except Exception as e:
        write_error(f"failed to open image: {e}")
        return

    zip_buf = io.BytesIO()
    output_meta = []

    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        crop_idx = 0
        for item in items:
            bbox = item.get("bbox")
            meta = {k: v for k, v in item.items() if k != "bbox"}

            valid_list_bbox = isinstance(bbox, list) and len(bbox) == 4
            valid_dict_bbox = isinstance(bbox, dict) and (
                all(k in bbox for k in ("x", "y", "w", "h"))
                or all(k in bbox for k in ("y_min", "x_min", "y_max", "x_max"))
            )
            if not bbox or (not valid_list_bbox and not valid_dict_bbox):
                meta["image_file"] = None
                meta["skip_reason"] = f"invalid or missing bbox: {bbox!r}"
                output_meta.append(meta)
                continue

            try:
                cropped = crop_item(img, bbox, padding, min_size)
            except Exception as e:
                cropped = None
                meta["image_file"] = None
                meta["skip_reason"] = f"crop error: {e}"
                output_meta.append(meta)
                continue

            if cropped is None:
                meta["image_file"] = None
                meta["skip_reason"] = f"crop too small (min_size={min_size}px)"
                output_meta.append(meta)
                continue

            filename = f"item_{crop_idx}.jpg"
            zf.writestr(filename, jpeg_bytes(cropped))

            meta["image_file"] = filename
            output_meta.append(meta)
            crop_idx += 1

        zf.writestr("items.json", json.dumps(output_meta, ensure_ascii=False, indent=2))

    write_output(
        zip_buf.getvalue(),
        "application/zip",
        item_count=len(output_meta),
        cropped_count=sum(1 for m in output_meta if m.get("image_file")),
    )


if __name__ == "__main__":
    main()
