#!/usr/bin/env python3
"""
Extract dominant colors from a logo image.

Filters out whites, blacks, and transparent pixels, then uses color
quantization to group similar shades. Returns the INPUT IMAGE unchanged
(pass-through for pipelines) plus color data in the output JSON metadata.

Params:
  num_colors     - Number of colors to extract (default: 4)
"""
import sys
import json
import base64
import io
import math
from collections import Counter
from PIL import Image
from script_io import read_input, write_output, write_error


def color_distance(c1, c2):
    return math.sqrt((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2)


def quantize_color(color, bucket=32):
    r, g, b = color
    return ((r // bucket) * bucket, (g // bucket) * bucket, (b // bucket) * bucket)


def luminance(color):
    r, g, b = color
    return 0.299 * r + 0.587 * g + 0.114 * b


def get_dominant_colors(img, num_colors=4):
    # Downsample for performance - color extraction does not need full res
    analysis = img.copy()
    MAX_DIM = 256
    if analysis.width > MAX_DIM or analysis.height > MAX_DIM:
        analysis.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)

    if analysis.mode != 'RGBA':
        analysis = analysis.convert('RGBA')

    pixels = analysis.load()
    all_colors = []
    color_to_q = {}

    WHITE_THRESH = 235
    BLACK_THRESH = 30

    for y in range(analysis.height):
        for x in range(analysis.width):
            r, g, b, a = pixels[x, y]
            if a < 200:
                continue
            if r > WHITE_THRESH and g > WHITE_THRESH and b > WHITE_THRESH:
                continue
            if r < BLACK_THRESH and g < BLACK_THRESH and b < BLACK_THRESH:
                continue

            actual = (r, g, b)
            q = quantize_color(actual)
            all_colors.append(actual)
            color_to_q[actual] = q

    if not all_colors:
        return [(128, 128, 128)]

    groups = {}
    for c in all_colors:
        q = color_to_q[c]
        if q not in groups:
            groups[q] = []
        groups[q].append(c)

    reps = []
    for q, actuals in groups.items():
        counts = Counter(actuals)
        best = counts.most_common(1)[0][0]
        reps.append((best, len(actuals), q))

    reps.sort(key=lambda x: x[1], reverse=True)

    MIN_DIST = 60
    result = []
    for actual, count, q in reps:
        distinct = True
        for existing in result:
            eq = color_to_q.get(existing, existing)
            if color_distance(q, eq) < MIN_DIST:
                distinct = False
                break
        if distinct:
            result.append(actual)
        if len(result) >= num_colors:
            break

    return result if result else [(128, 128, 128)]


def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    img = Image.open(io.BytesIO(input_bytes))

    num_colors = int(params.get("num_colors", "4"))

    colors = get_dominant_colors(img, num_colors)
    colors.sort(key=luminance)

    # Pass through the original input image unchanged
    buf = io.BytesIO()
    fmt = "PNG"
    ct = content_type or "image/png"
    if ct == "image/jpeg":
        fmt = "JPEG"
        if img.mode == "RGBA":
            img = img.convert("RGB")
    img.save(buf, format=fmt)

    colors_data = []
    for c in colors:
        colors_data.append({
            "rgb": list(c),
            "hex": "#{:02x}{:02x}{:02x}".format(c[0], c[1], c[2]),
            "luminance": round(luminance(c), 1),
        })

    write_output(buf.getvalue(), ct, colors=colors_data)


if __name__ == "__main__":
    main()
