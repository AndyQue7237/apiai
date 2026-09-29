#!/usr/bin/env python3
"""Extract metadata from an image: dimensions, format, mode, file size, DPI, EXIF.

Returns JSON via the text response_type (no image output).
"""

import io
from PIL import Image
from PIL.ExifTags import TAGS
from script_io import read_input, write_output, write_error


def main():
    input_bytes, content_type, params = read_input()
    if not input_bytes:
        write_error("no input image provided")
        return

    try:
        img = Image.open(io.BytesIO(input_bytes))

        meta = {
            "width": img.width,
            "height": img.height,
            "format": img.format or "unknown",
            "mode": img.mode,
            "has_alpha": img.mode in ("RGBA", "LA", "PA"),
            "file_size_bytes": len(input_bytes),
            "megapixels": round(img.width * img.height / 1_000_000, 2),
        }

        # DPI / resolution
        dpi = img.info.get("dpi")
        if dpi:
            meta["dpi_x"] = round(dpi[0])
            meta["dpi_y"] = round(dpi[1])

        # Animation frames
        try:
            meta["frames"] = getattr(img, "n_frames", 1)
            meta["is_animated"] = getattr(img, "is_animated", False)
        except Exception:
            pass

        # EXIF data (best effort)
        exif = {}
        try:
            raw_exif = img.getexif()
            if raw_exif:
                for tag_id, value in raw_exif.items():
                    tag = TAGS.get(tag_id, str(tag_id))
                    # Skip binary/bytes fields and convert non-serializable types
                    if isinstance(value, bytes):
                        continue
                    elif isinstance(value, (list, tuple)):
                        # Handle sequences that might contain non-serializable items
                        try:
                            exif[tag] = list(value)
                        except (TypeError, ValueError):
                            exif[tag] = str(value)
                    elif isinstance(value, (str, int, float, bool)) or value is None:
                        exif[tag] = value
                    else:
                        exif[tag] = str(value)
        except Exception:
            pass
        if exif:
            meta["exif"] = exif

        # Return as text response
        write_output(b"", "text/plain", text=meta)

    except Exception as e:
        write_error(f"failed to extract metadata: {str(e)}")


if __name__ == "__main__":
    main()
