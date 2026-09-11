#!/usr/bin/env python3
"""
Detect logo in image using Florence-2 (via Replicate) and crop with
symmetric padding. Returns the cropped image as base64 PNG.

Falls back to passing through the original image if detection fails,
since most logos are already centered/cropped.

Params:
  query            - Detection prompt (default: "complete logo with text, full team logo with text, entire emblem, club logo")
  padding_percent  - Padding as % of logo size (default: 5)
  min_padding      - Minimum padding in pixels (default: 50)
  safety_margin    - Extra safety pixels (default: 30)

Metadata returned:
  detection_label, bbox, logo_coverage, cropped_size, detection_fallback
"""
import sys
import json
import base64
import io
import os
import replicate
from PIL import Image
from script_io import read_input, write_output, write_error

# Florence-2 model on Replicate
FLORENCE_MODEL = "lucataco/florence-2-large:da53547e17d45b9cfb48174b2f18af8b83ca020fa76db62136bf9c6616762595"


def detect_logo_florence(image_bytes, content_type, params):
    """
    Call Florence-2 on Replicate and return best detection bbox.
    Returns None if no detection found.
    """
    query = params.get("query",
        "complete logo with text, full team logo with text, entire emblem, club logo")

    # Convert to base64 data URI
    mime = "image/png"
    if "jpeg" in content_type or "jpg" in content_type:
        mime = "image/jpeg"
    elif "webp" in content_type:
        mime = "image/webp"

    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"

    try:
        output = replicate.run(
            FLORENCE_MODEL,
            input={
                "image": data_uri,
                "task_input": "Caption to Phrase Grounding",
                "text_input": query,
            },
        )
    except Exception as e:
        # API error - return None to trigger fallback
        print(f"Florence-2 API error: {e}", file=sys.stderr)
        return None

    # Parse output
    text_output = output.get("text", "")
    if isinstance(text_output, str):
        try:
            import ast
            parsed = ast.literal_eval(text_output)
        except:
            parsed = {}
    else:
        parsed = text_output

    # Extract bboxes from the nested structure
    grounding = parsed.get("<CAPTION_TO_PHRASE_GROUNDING>", {})
    bboxes = grounding.get("bboxes", [])
    labels = grounding.get("labels", [])

    if not bboxes:
        return None

    # Return first detection (they're usually nearly identical)
    return {
        "bbox": bboxes[0],
        "label": labels[0] if labels else "logo",
    }


def crop_with_padding(img, bbox, params):
    """Crop image around bbox with symmetric padding. Returns (cropped_img, metadata)."""
    padding_percent = int(params.get("padding_percent", "5"))
    min_padding = int(params.get("min_padding", "50"))
    safety_margin = int(params.get("safety_margin", "30"))

    img_width, img_height = img.size
    x1, y1, x2, y2 = bbox
    logo_width = x2 - x1
    logo_height = y2 - y1

    logo_coverage = (logo_width * logo_height) / (img_width * img_height)

    # If logo takes up >90% of image, return the full image
    if logo_coverage > 0.90:
        return img, {"logo_coverage": round(logo_coverage, 3), "full_image": True}

    # Calculate smart padding
    padding_x_pct = int(logo_width * (padding_percent / 100))
    padding_y_pct = int(logo_height * (padding_percent / 100))

    desired_padding_x = max(padding_x_pct, min_padding) + safety_margin
    desired_padding_y = max(padding_y_pct, min_padding) + safety_margin

    # Max symmetric padding limited by image edges
    max_pad_left = x1
    max_pad_right = img_width - x2
    max_pad_top = y1
    max_pad_bottom = img_height - y2

    padding_x = min(desired_padding_x, max_pad_left, max_pad_right)
    padding_y = min(desired_padding_y, max_pad_top, max_pad_bottom)

    # Calculate centered crop box
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2

    crop_w = logo_width + 2 * padding_x
    crop_h = logo_height + 2 * padding_y

    cx1 = center_x - crop_w / 2
    cy1 = center_y - crop_h / 2
    cx2 = center_x + crop_w / 2
    cy2 = center_y + crop_h / 2

    # Edge clamping
    if cx1 < 0:
        cx2 -= cx1
        cx1 = 0
    if cx2 > img_width:
        cx1 -= (cx2 - img_width)
        cx2 = img_width
    if cy1 < 0:
        cy2 -= cy1
        cy1 = 0
    if cy2 > img_height:
        cy1 -= (cy2 - img_height)
        cy2 = img_height

    cx1 = int(max(0, cx1))
    cy1 = int(max(0, cy1))
    cx2 = int(min(img_width, cx2))
    cy2 = int(min(img_height, cy2))

    cropped = img.crop((cx1, cy1, cx2, cy2))

    # If very tight crop (>95% coverage or tiny padding), expand canvas
    if logo_coverage > 0.95 or padding_x < 10 or padding_y < 10:
        expansion = 25
        new_w = cropped.width + 2 * expansion
        new_h = cropped.height + 2 * expansion
        if cropped.mode in ("RGBA", "LA"):
            expanded = Image.new("RGBA", (new_w, new_h), (255, 255, 255, 0))
        else:
            expanded = Image.new("RGB", (new_w, new_h), (255, 255, 255))
        expanded.paste(cropped, (expansion, expansion))
        cropped = expanded

    meta = {
        "logo_coverage": round(logo_coverage, 3),
        "padding_x": padding_x,
        "padding_y": padding_y,
        "full_image": False,
    }
    return cropped, meta


def main():
    img_bytes, content_type, params = read_input()
    if not content_type:
        content_type = "image/png"
    if not img_bytes:
        write_error("no input image provided")
        return

    # Step 1: Try to detect with Florence-2
    detection = detect_logo_florence(img_bytes, content_type, params)

    # Step 2: Process based on detection result
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGBA")

    if detection is None:
        # Fallback: pass through original image
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        write_output(
            buf.getvalue(), "image/png",
            detection_label="none",
            bbox=[],
            logo_coverage=1.0,
            cropped_size=f"{img.width}x{img.height}",
            detection_fallback=True,
        )
        return

    # Detection succeeded - crop
    bbox = detection["bbox"]
    label = detection.get("label", "logo")

    cropped, crop_meta = crop_with_padding(img, bbox, params)

    # Encode result
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")

    write_output(
        buf.getvalue(), "image/png",
        detection_label=label,
        bbox=bbox,
        logo_coverage=crop_meta["logo_coverage"],
        cropped_size=f"{cropped.width}x{cropped.height}",
        detection_fallback=False,
    )


if __name__ == "__main__":
    main()
