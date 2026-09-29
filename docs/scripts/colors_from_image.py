#!/usr/bin/env python3
"""Extract the dominant colours from an image and return them as JSON hex values.

Unlike extract_colors.py (which renders a swatch image) this returns data only,
so it can be the last step of a pipeline that answers a question rather than
producing a picture.

Params:
  num_colors - number of dominant colours to extract, 1-8 (default: "4")
"""
import io
import json
import logging
import sys

from PIL import Image

from script_io import read_input, write_output, write_error

log = logging.getLogger("extract_colors_json")
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(name)s %(levelname)s: %(message)s")

PARAM_DEFS = [
    {
        "name": "num_colors",
        "description": "How many dominant colours to return (1-8)",
        "default_value": "4",
    },
]

MAX_COLORS = 8
SAMPLE_EDGE = 200  # px; quantising a thumbnail is far faster and shifts nothing


def rgb_to_hex(r, g, b):
    return "#{:02X}{:02X}{:02X}".format(r, g, b)


def flatten_transparency(img):
    """Composite any alpha onto white before reading colours.

    convert("RGB") discards alpha without compositing, leaving whatever RGB sits
    beneath a transparent pixel — usually black. A logo on a transparent
    background would then report #000000 as its brand colour, which is the exact
    case this tool exists for. White is the right ground: it is how the logo will
    be seen nearly everywhere it is placed.
    """
    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )
    if has_alpha:
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img)
    return img.convert("RGB")


def extract_dominant_colors(img, num_colors):
    img = flatten_transparency(img)
    img.thumbnail((SAMPLE_EDGE, SAMPLE_EDGE), Image.LANCZOS)

    quantized = img.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT)
    pixels = list(quantized.convert("RGB").getdata())

    counts = {}
    for pixel in pixels:
        counts[pixel] = counts.get(pixel, 0) + 1

    total = len(pixels) or 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [
        {"hex": rgb_to_hex(*rgb), "share": round(count / total, 3)}
        for rgb, count in ranked[:num_colors]
    ]


def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    try:
        num_colors = int(params.get("num_colors", "4"))
    except (TypeError, ValueError):
        num_colors = 4
    num_colors = max(1, min(MAX_COLORS, num_colors))

    try:
        img = Image.open(io.BytesIO(input_bytes))
    except Exception:
        # HEIC arrives undecoded unless pillow-heif is installed, and PIL's own
        # message ("cannot identify image file") says nothing a caller can act on.
        write_error("could not read this image — supported formats are PNG, JPEG, "
                    "WebP and HEIC")
        return

    try:
        colors = extract_dominant_colors(img, num_colors)
        log.info("extracted %d colours: %s", len(colors),
                 ", ".join(c["hex"] for c in colors))

        payload = {
            "num_colors": len(colors),
            "colors": [c["hex"] for c in colors],
            # Share is what separates a brand colour from an accent. Drop this key
            # if you only want the list.
            "palette": colors,
        }
        # Both, deliberately — the platform reads a script's result from two
        # different places depending on how it is called:
        #   single tool, response_type=text  -> returns output.Metadata as JSON,
        #                                       ignoring the bytes entirely
        #   step inside a pipeline           -> takes OutputData bytes, ignoring
        #                                       metadata
        # Sending the payload down both channels is the only way to work in both
        # positions. Cheap here: it is a few hundred bytes of JSON.
        write_output(json.dumps(payload, indent=2).encode(), "application/json", **payload)

    except Exception as e:
        write_error(str(e))


if __name__ == "__main__":
    main()
