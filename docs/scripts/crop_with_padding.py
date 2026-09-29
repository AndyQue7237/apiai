#!/usr/bin/env python3
"""
Crop image around a detected region with symmetric padding.

Params:
  x1, y1, x2, y2  - Bounding box coordinates (required)
  padding_percent  - Padding as % of logo size (default: 5)
  min_padding      - Minimum padding in pixels (default: 50)
"""
import io
from PIL import Image
from script_io import read_input, write_output, write_error


def _int_param(params, key, default):
    val = params.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def process(img, params):
    # Parse bounding box (required)
    x1 = _int_param(params, "x1", 0)
    y1 = _int_param(params, "y1", 0)
    x2 = _int_param(params, "x2", img.width)
    y2 = _int_param(params, "y2", img.height)

    padding_percent = _int_param(params, "padding_percent", 5)
    min_padding     = _int_param(params, "min_padding", 50)

    img_width, img_height = img.size
    logo_width = x2 - x1
    logo_height = y2 - y1

    # Calculate smart padding
    padding_x_pct = int(logo_width * (padding_percent / 100))
    padding_y_pct = int(logo_height * (padding_percent / 100))

    desired_padding_x = max(padding_x_pct, min_padding)
    desired_padding_y = max(padding_y_pct, min_padding)

    # Calculate max symmetric padding (limited by image edges)
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

    # Handle edge clamping
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

    return img.crop((cx1, cy1, cx2, cy2))


def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    img = Image.open(io.BytesIO(input_bytes))

    result = process(img, params)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    write_output(buf.getvalue(), "image/png")


if __name__ == "__main__":
    main()
