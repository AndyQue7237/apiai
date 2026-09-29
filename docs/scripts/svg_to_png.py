#!/usr/bin/env python3
"""Convert an SVG image to PNG.

Params:
    width - output width in pixels; aspect ratio is preserved if height is omitted (default: original SVG size)
    height - output height in pixels (default: derived from width or original)
    scale - scale factor applied when width/height are not set (default: 1)
"""

import io
from script_io import read_input, write_output, write_error

try:
    import cairosvg
except ImportError:
    write_error("cairosvg is not installed")
    exit(1)

PARAM_DEFS = [
    {"name": "width", "description": "Output width in pixels", "default_value": ""},
    {"name": "height", "description": "Output height in pixels", "default_value": ""},
    {"name": "scale", "description": "Scale factor when width/height not set", "default_value": "1"},
]


def main():
    input_bytes, content_type, params = read_input()
    
    if not input_bytes:
        write_error("no SVG input provided")
        return

    width = params.get("width", "").strip()
    height = params.get("height", "").strip()
    scale = params.get("scale", "1").strip()

    try:
        width = int(width) if width else None
        height = int(height) if height else None
        scale = float(scale) if scale else 1.0
    except ValueError as e:
        write_error(f"invalid parameter value: {e}")
        return

    kwargs = {}
    if width:
        kwargs["output_width"] = width
    if height:
        kwargs["output_height"] = height
    if not width and not height and scale != 1.0:
        kwargs["scale"] = scale

    try:
        png_bytes = cairosvg.svg2png(bytestring=input_bytes, **kwargs)
        write_output(png_bytes, "image/png")
    except Exception as e:
        write_error(f"SVG conversion failed: {e}")


if __name__ == "__main__":
    main()
