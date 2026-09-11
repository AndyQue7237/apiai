#!/usr/bin/env python3
"""
Complete Logo Pipeline - All steps in one script
Converts from input (photo/digital) to print-ready transparent PNG.

Params:
  crop_padding (optional) - Padding % during crop (default: 5)
  skip_digitalization (optional) - Skip Gemini if already digital (default: auto-detect)

Pipeline:
1. Grounding DINO detection
2. Crop with padding
3. Digitalize (Gemini) OR Upscale (if already transparent)
4. Remove background (if needed)
5. Final output

Returns:
  - Final transparent PNG
  - Metadata with all intermediate results and bbox coordinates
"""
import sys
import json
import base64
import io
import os
import math
from collections import Counter
from pathlib import Path
from PIL import Image, ImageOps
import replicate
import google.genai as genai
from dotenv import load_dotenv

# Load environment variables from .env file
# Look for .env in parent directories
current_dir = Path(__file__).resolve().parent
for _ in range(5):  # Search up to 5 levels
    env_path = current_dir / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        break
    current_dir = current_dir.parent
from google.genai import types


# ============================================================
# CONFIGURATION CONSTANTS
# ============================================================

# Logo Coverage & Cropping
LOGO_COVERAGE_THRESHOLD = 0.90  # Preserve full image if logo fills >90%
TIGHT_CROP_THRESHOLD = 0.95     # Expand canvas if logo fills >95% after crop
MIN_PADDING_PX = 50
SAFETY_MARGIN_PX = 30
CANVAS_EXPANSION_PX = 25
MIN_PADDING_THRESHOLD_PX = 10

# Color Extraction
WHITE_THRESHOLD = 235
BLACK_THRESHOLD = 30
MIN_COLOR_DISTANCE = 60
ALPHA_THRESHOLD = 200

# Background Removal
CORNER_SAMPLE_SIZE = 20
CORNER_OPAQUE_THRESHOLD = 30  # % opaque corners triggers second pass
ALPHA_OPAQUE_THRESHOLD = 200

# Transparency Detection
TRANSPARENCY_SAMPLE_GRID = 20  # Sample every Nth pixel
TRANSPARENCY_THRESHOLD = 0.1    # 10% transparent pixels = has transparency


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def calculate_luminance(color):
    """Calculate perceived luminance of RGB color."""
    r, g, b = color
    return 0.299 * r + 0.587 * g + 0.114 * b


def color_distance(c1, c2):
    """Calculate Euclidean distance between two RGB colors."""
    return math.sqrt((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2)


def quantize_color(color, bucket_size=32):
    """Quantize color to reduce color space."""
    r, g, b = color
    return (
        (r // bucket_size) * bucket_size,
        (g // bucket_size) * bucket_size,
        (b // bucket_size) * bucket_size
    )


def get_dominant_colors(img, num_colors=2):
    """Extract dominant colors from logo."""
    # Ensure RGBA mode
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    pixels = img.load()
    all_colors = []
    color_to_quantized = {}

    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pixels[x, y]

            if a < ALPHA_THRESHOLD:
                continue

            if r > WHITE_THRESHOLD and g > WHITE_THRESHOLD and b > WHITE_THRESHOLD:
                continue

            if r < BLACK_THRESHOLD and g < BLACK_THRESHOLD and b < BLACK_THRESHOLD:
                continue

            actual_color = (r, g, b)
            quantized = quantize_color(actual_color, bucket_size=32)

            all_colors.append(actual_color)
            color_to_quantized[actual_color] = quantized

    if not all_colors:
        return [(200, 0, 0), (0, 0, 200)]

    # Group by quantized version
    quantized_groups = {}
    for actual_color in all_colors:
        quantized = color_to_quantized[actual_color]
        if quantized not in quantized_groups:
            quantized_groups[quantized] = []
        quantized_groups[quantized].append(actual_color)

    # Find most common actual color per group
    group_representatives = []
    for quantized, actual_colors in quantized_groups.items():
        color_counts = Counter(actual_colors)
        most_common_actual = color_counts.most_common(1)[0][0]
        total_count = len(actual_colors)
        group_representatives.append((most_common_actual, total_count, quantized))

    group_representatives.sort(key=lambda x: x[1], reverse=True)

    # Find top N distinct colors
    dominant_colors = []

    for actual_color, count, quantized in group_representatives:
        is_distinct = True
        for existing_color in dominant_colors:
            existing_quantized = color_to_quantized.get(existing_color, existing_color)
            if color_distance(quantized, existing_quantized) < MIN_COLOR_DISTANCE:
                is_distinct = False
                break

        if is_distinct:
            dominant_colors.append(actual_color)

        if len(dominant_colors) >= num_colors:
            break

    if len(dominant_colors) == 1:
        dominant_colors.append(dominant_colors[0])

    return dominant_colors[:num_colors]


def has_transparency(img):
    """Check if image has transparent background."""
    if img.mode not in ('RGBA', 'LA', 'PA'):
        return False

    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    pixels = img.load()
    width, height = img.size

    transparent_count = 0
    total_checked = 0

    for x in range(0, width, max(1, width // TRANSPARENCY_SAMPLE_GRID)):
        for y in range(0, height, max(1, height // TRANSPARENCY_SAMPLE_GRID)):
            r, g, b, a = pixels[x, y]
            total_checked += 1
            if a < 250:
                transparent_count += 1

    return transparent_count > total_checked * TRANSPARENCY_THRESHOLD


def image_to_base64(img):
    """Convert PIL Image to base64 string."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ============================================================
# PIPELINE STEPS
# ============================================================

def step1_detect_logo(img, params):
    """Step 1: Detect logo using Grounding DINO."""
    query = params.get("query", "complete logo with text, full team logo with text, entire emblem, club logo")
    box_threshold = float(params.get("box_threshold", "0.25"))
    text_threshold = float(params.get("text_threshold", "0.25"))

    # Save to temp buffer for Replicate
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    output = replicate.run(
        "adirik/grounding-dino:efd10a8ddc57ea28773327e881ce95e20cc1d734c589f7dd01d2036921ed78aa",
        input={
            "image": buf,
            "query": query,
            "box_threshold": box_threshold,
            "text_threshold": text_threshold,
            "show_visualisation": False
        }
    )

    if not output or 'detections' not in output or len(output['detections']) == 0:
        return None, {"error": "No logo detected"}

    # Get best detection
    detections = output['detections']
    best = max(detections, key=lambda x: x['confidence'])

    return best['bbox'], {
        "bbox": best['bbox'],
        "confidence": best['confidence'],
        "label": best['label']
    }


def step2_crop_with_padding(img, bbox, params):
    """Step 2: Crop logo with symmetric padding (matches original pipeline)."""
    padding_percent = int(params.get("crop_padding", "5"))

    x1, y1, x2, y2 = bbox
    img_width, img_height = img.size
    logo_width = x2 - x1
    logo_height = y2 - y1

    # Check if logo takes up >90% of image - if so, use entire image
    logo_coverage = (logo_width * logo_height) / (img_width * img_height)

    if logo_coverage > LOGO_COVERAGE_THRESHOLD:
        # Logo is already nearly full image - don't crop to preserve all edges
        return img, {
            "cropped_size": f"{img.width}x{img.height}",
            "padding_applied": "0px (full image preserved)",
            "reason": f"Logo coverage {logo_coverage:.1%} > 90%"
        }

    # Calculate smart padding with safety margin
    padding_x_percent = int(logo_width * (padding_percent / 100))
    padding_y_percent = int(logo_height * (padding_percent / 100))

    desired_padding_x = max(padding_x_percent, MIN_PADDING_PX) + SAFETY_MARGIN_PX
    desired_padding_y = max(padding_y_percent, MIN_PADDING_PX) + SAFETY_MARGIN_PX

    # Calculate max symmetric padding
    max_padding_left = x1
    max_padding_right = img_width - x2
    max_padding_top = y1
    max_padding_bottom = img_height - y2

    padding_x = min(desired_padding_x, max_padding_left, max_padding_right)
    padding_y = min(desired_padding_y, max_padding_top, max_padding_bottom)

    # Calculate centered crop box
    logo_center_x = (x1 + x2) / 2
    logo_center_y = (y1 + y2) / 2

    crop_width = logo_width + 2 * padding_x
    crop_height = logo_height + 2 * padding_y

    crop_x1 = logo_center_x - crop_width / 2
    crop_y1 = logo_center_y - crop_height / 2
    crop_x2 = logo_center_x + crop_width / 2
    crop_y2 = logo_center_y + crop_height / 2

    # Handle edge cases
    shift_x = 0
    shift_y = 0

    if crop_x1 < 0:
        shift_x = -crop_x1
    elif crop_x2 > img_width:
        shift_x = img_width - crop_x2

    if crop_y1 < 0:
        shift_y = -crop_y1
    elif crop_y2 > img_height:
        shift_y = img_height - crop_y2

    # Apply shifts and clamp
    crop_x1 = int(max(0, min(img_width - crop_width, crop_x1 + shift_x)))
    crop_y1 = int(max(0, min(img_height - crop_height, crop_y1 + shift_y)))
    crop_x2 = int(min(img_width, crop_x1 + crop_width))
    crop_y2 = int(min(img_height, crop_y1 + crop_height))

    # Crop
    cropped = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))

    # Check if logo takes up >95% of cropped image (tight crop) - expand canvas if needed
    cropped_coverage = (logo_width * logo_height) / (cropped.width * cropped.height)

    if cropped_coverage > TIGHT_CROP_THRESHOLD or padding_x < MIN_PADDING_THRESHOLD_PX or padding_y < MIN_PADDING_THRESHOLD_PX:
        # Create new image with expanded canvas
        new_width = cropped.width + 2 * CANVAS_EXPANSION_PX
        new_height = cropped.height + 2 * CANVAS_EXPANSION_PX

        # Use transparent background if image has alpha, otherwise white
        if cropped.mode in ('RGBA', 'LA'):
            expanded = Image.new('RGBA', (new_width, new_height), (255, 255, 255, 0))
        else:
            expanded = Image.new('RGB', (new_width, new_height), (255, 255, 255))

        # Paste cropped image in center
        expanded.paste(cropped, (CANVAS_EXPANSION_PX, CANVAS_EXPANSION_PX))
        cropped = expanded

        return cropped, {
            "cropped_size": f"{cropped.width}x{cropped.height}",
            "padding_applied": f"{padding_x}px x {padding_y}px",
            "canvas_expanded": f"{CANVAS_EXPANSION_PX}px (tight crop)"
        }

    return cropped, {
        "cropped_size": f"{cropped.width}x{cropped.height}",
        "padding_applied": f"{padding_x}px x {padding_y}px"
    }


def step3_digitalize_with_recraft(img, params):
    """Fallback: Vectorize with Recraft AI when Gemini blocks (IMAGE_RECITATION)."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    try:
        # Use Recraft Vectorize - same as original pipeline
        output = replicate.run(
            "recraft-ai/recraft-vectorize",
            input={"image": buf}
        )

        # Recraft Vectorize returns SVG
        svg_data = output.read()

        vectorized_img = None

        # Method 1: Try cairosvg (if available in backoffice)
        try:
            import cairosvg
            png_data = cairosvg.svg2png(bytestring=svg_data)
            vectorized_img = Image.open(io.BytesIO(png_data))
        except (ImportError, Exception) as cairo_err:
            # Method 2: Save SVG and use system tools (qlmanage on macOS)
            import tempfile
            import subprocess

            with tempfile.NamedTemporaryFile(suffix='.svg', delete=False) as svg_file:
                svg_file.write(svg_data)
                svg_path = svg_file.name

            try:
                # Try qlmanage (macOS)
                png_path = svg_path + '.png'
                result = subprocess.run(
                    ['qlmanage', '-t', '-s', '2000', '-o', tempfile.gettempdir(), svg_path],
                    capture_output=True,
                    timeout=10
                )

                if os.path.exists(png_path):
                    vectorized_img = Image.open(png_path)
                    os.unlink(svg_path)
                    os.unlink(png_path)
            except Exception:
                pass
            finally:
                if os.path.exists(svg_path):
                    os.unlink(svg_path)

        if vectorized_img is None:
            return None, {"error": "Recraft vectorize: SVG conversion failed (install cairosvg)"}

        return vectorized_img, {
            "digitalized": True,
            "method": "recraft_vectorize",
            "output_size": f"{vectorized_img.width}x{vectorized_img.height}"
        }

    except Exception as e:
        return None, {"error": f"Recraft error: {str(e)}"}


def step3_digitalize_with_gemini(img, params):
    """Step 3: Digitalize with Gemini (with Recraft fallback)."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment")

    prompt = "Transform this team logo to flat vector style logo, professional clean lines, high contrast, solid colors. Important: High fidelity to original shape and colours. Solid white background."

    client = genai.Client(api_key=api_key)

    # Convert image to bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_data = buf.getvalue()

    try:
        parts = [
            types.Part.from_text(text=prompt),
            types.Part.from_bytes(data=image_data, mime_type="image/png")
        ]

        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=parts,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                temperature=1.0
            )
        )

        # Check for blocks
        if not response or not response.candidates:
            # Fallback to Recraft
            return step3_digitalize_with_recraft(img, params)

        finish_reason = response.candidates[0].finish_reason
        if finish_reason and str(finish_reason) == 'FinishReason.IMAGE_RECITATION':
            # Fallback to Recraft for copyright-protected logos
            return step3_digitalize_with_recraft(img, params)

        # Extract image
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                digital_img = Image.open(io.BytesIO(part.inline_data.data))
                return digital_img, {
                    "digitalized": True,
                    "method": "gemini",
                    "output_size": f"{digital_img.width}x{digital_img.height}"
                }

        # No image found, fallback to Recraft
        return step3_digitalize_with_recraft(img, params)

    except Exception as e:
        # Any Gemini error, fallback to Recraft
        return step3_digitalize_with_recraft(img, params)


def step4_upscale(img, target_size=1000):
    """Step 4: Upscale if needed."""
    max_dim = max(img.width, img.height)

    if max_dim >= target_size:
        return img, {"upscaled": False, "reason": "Already large enough"}

    # Calculate scale
    scale_needed = target_size / max_dim
    if scale_needed <= 2:
        scale_factor = 2
    elif scale_needed <= 4:
        scale_factor = 4
    else:
        scale_factor = 8

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    output = replicate.run(
        "nightmareai/real-esrgan:42fed1c4974146d4d2414e2be2c5277c7fcf05fcc3a73abf41610695738c1d7b",
        input={
            "image": buf,
            "scale": scale_factor,
            "face_enhance": False
        }
    )

    upscaled_img = Image.open(output)

    return upscaled_img, {
        "upscaled": True,
        "scale_factor": scale_factor,
        "output_size": f"{upscaled_img.width}x{upscaled_img.height}"
    }


def step5_remove_background(img):
    """Step 5: Remove background."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    # First pass
    output = replicate.run(
        "recraft-ai/recraft-remove-background",
        input={"image": buf}
    )

    img_pass1 = Image.open(output)

    # Check for residual background
    if img_pass1.mode == 'RGBA':
        pixels = img_pass1.load()
        corner_opaque_count = 0
        corner_samples = 0

        corners = [
            (0, 0),
            (img_pass1.width - CORNER_SAMPLE_SIZE, 0),
            (0, img_pass1.height - CORNER_SAMPLE_SIZE),
            (img_pass1.width - CORNER_SAMPLE_SIZE, img_pass1.height - CORNER_SAMPLE_SIZE)
        ]

        for corner_x, corner_y in corners:
            for x in range(max(0, corner_x), min(img_pass1.width, corner_x + CORNER_SAMPLE_SIZE)):
                for y in range(max(0, corner_y), min(img_pass1.height, corner_y + CORNER_SAMPLE_SIZE)):
                    r, g, b, a = pixels[x, y]
                    corner_samples += 1
                    if a > ALPHA_OPAQUE_THRESHOLD:
                        corner_opaque_count += 1

        corner_opaque_percentage = (corner_opaque_count / corner_samples) * 100 if corner_samples > 0 else 0

        if corner_opaque_percentage > CORNER_OPAQUE_THRESHOLD:
            # Second pass
            buf2 = io.BytesIO()
            img_pass1.save(buf2, format="PNG")
            buf2.seek(0)

            output2 = replicate.run(
                "recraft-ai/recraft-remove-background",
                input={"image": buf2}
            )

            img_final = Image.open(output2)
            return img_final, {"passes": 2, "residual_detected": True}

    return img_pass1, {"passes": 1, "residual_detected": False}


# ============================================================
# MAIN PIPELINE
# ============================================================

def process(img, params):
    """Run complete pipeline."""
    metadata = {
        "steps": [],
        "success": False
    }

    try:
        # Step 0: Auto-rotate based on EXIF orientation (if present)
        img_original = img
        img = ImageOps.exif_transpose(img)

        if img is None:
            # No EXIF orientation data, use original
            img = img_original
            metadata["steps"].append({
                "step": "exif_rotation",
                "result": {"rotated": False, "reason": "No EXIF orientation data"}
            })
        elif img.size != img_original.size:
            # Image was rotated
            metadata["steps"].append({
                "step": "exif_rotation",
                "result": {
                    "rotated": True,
                    "original_size": f"{img_original.width}x{img_original.height}",
                    "corrected_size": f"{img.width}x{img.height}"
                }
            })
        else:
            # EXIF present but no rotation needed
            metadata["steps"].append({
                "step": "exif_rotation",
                "result": {"rotated": False, "reason": "Already correct orientation"}
            })

        # Step 1: Detection
        bbox, detect_meta = step1_detect_logo(img, params)
        if bbox is None:
            metadata["error"] = detect_meta.get("error")
            return img, metadata

        metadata["steps"].append({"step": "detection", "result": detect_meta})
        metadata["bbox"] = bbox
        metadata["x1"] = int(bbox[0])
        metadata["y1"] = int(bbox[1])
        metadata["x2"] = int(bbox[2])
        metadata["y2"] = int(bbox[3])

        # Step 2: Crop
        cropped_img, crop_meta = step2_crop_with_padding(img, bbox, params)
        metadata["steps"].append({"step": "crop", "result": crop_meta})

        # Check if already transparent
        is_transparent = has_transparency(cropped_img)
        metadata["is_transparent"] = is_transparent

        if is_transparent:
            # Path for transparent images: Just upscale if needed
            final_img, upscale_meta = step4_upscale(cropped_img)
            metadata["steps"].append({"step": "upscale", "result": upscale_meta})
        else:
            # Path for opaque images: Digitalize + Remove BG
            digital_img, digital_meta = step3_digitalize_with_gemini(cropped_img, params)

            if digital_img is None:
                metadata["error"] = digital_meta.get("error")
                return cropped_img, metadata

            metadata["steps"].append({"step": "digitalize", "result": digital_meta})

            # Remove background
            nobg_img, bg_meta = step5_remove_background(digital_img)
            metadata["steps"].append({"step": "remove_background", "result": bg_meta})

            final_img = nobg_img

        # Extract colors
        colors = get_dominant_colors(final_img, num_colors=2)
        colors.sort(key=calculate_luminance)

        colors_info = []
        for rgb in colors:
            colors_info.append({
                "rgb": list(rgb),
                "hex": f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}",
                "luminance": round(calculate_luminance(rgb), 1)
            })

        metadata["colors"] = colors_info
        metadata["final_size"] = f"{final_img.width}x{final_img.height}"
        metadata["success"] = True

        return final_img, metadata

    except Exception as e:
        metadata["error"] = str(e)
        return img, metadata


def main():
    """Main entry point for backoffice integration."""
    data = json.load(sys.stdin)
    img_bytes = base64.b64decode(data["image"])
    img = Image.open(io.BytesIO(img_bytes))
    params = data.get("params", {})

    result_img, metadata = process(img, params)

    buf = io.BytesIO()
    result_img.save(buf, format="PNG")

    json.dump({
        "image": base64.b64encode(buf.getvalue()).decode(),
        "content_type": "image/png",
        "metadata": metadata
    }, sys.stdout)


if __name__ == "__main__":
    main()
