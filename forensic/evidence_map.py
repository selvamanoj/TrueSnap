"""
forensic/evidence_map.py

Evidence Map - Stage 5.

Builds a visual "Evidence Map" from the Stage 4 ELA difference image:
grayscale conversion -> thresholding -> noise cleanup -> connected
region detection -> highlighted overlay on a COPY of the original image.

IMPORTANT FORENSIC RULE:
Highlighted regions are described only as "potentially interesting
regions" with "higher ELA differences" that "require further
investigation." This module NEVER claims a region is definitely
edited, fake, or manipulated, and never reports a percentage-certainty
of manipulation.

The original uploaded file is NEVER modified. All work happens on
in-memory copies; only newly generated map/overlay images are written
to disk, inside data/forensics/.
"""

import os
import time
from collections import deque

from PIL import Image, ImageStat, ImageFilter, ImageDraw

from forensic.image_forensics import perform_ela, FORENSICS_OUTPUT_DIR

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

MIN_IMAGE_DIMENSION = 20          # below this, analysis is not considered reliable
THRESHOLD_MULTIPLIER = 2.0        # threshold = mean + (multiplier * stddev)
MIN_THRESHOLD = 15                # clamp bounds so threshold is never degenerate
MAX_THRESHOLD = 245
MAX_ANALYSIS_DIMENSION = 300      # downscale target for connected-component analysis (speed)
MIN_REGION_PIXELS = 4             # regions smaller than this (at analysis scale) are treated as noise
MAX_REGIONS_RETURNED = 8          # cap the number of individual regions reported/drawn

_JPEG_EXTENSIONS = (".jpg", ".jpeg")
_JPEG_FORMATS = ("JPEG",)


def _is_jpeg_applicable(file_path: str, image_format: str) -> bool:
    """Same applicability rule used for ELA in Stage 4: JPEG only."""
    if image_format and image_format.upper() in _JPEG_FORMATS:
        return True
    ext = os.path.splitext(file_path)[1].lower()
    return ext in _JPEG_EXTENSIONS


def _ensure_output_dir() -> str:
    os.makedirs(FORENSICS_OUTPUT_DIR, exist_ok=True)
    return FORENSICS_OUTPUT_DIR


def _safe_base_name(file_path: str) -> str:
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    safe = "".join(c for c in base_name if c.isalnum() or c in ("_", "-"))
    return safe or "image"


# ---------------------------------------------------------------------
# Region detection (pure Python, no extra dependencies)
# ---------------------------------------------------------------------

def analyze_evidence_regions(mask_image, max_analysis_dim: int = MAX_ANALYSIS_DIMENSION,
                              min_region_pixels: int = MIN_REGION_PIXELS):
    """
    Find connected regions of "on" pixels (value >= 128) in a binary
    "L"-mode mask image, using simple 4-connectivity flood fill.

    To keep this fast and dependency-free, the mask is analyzed on a
    downscaled copy; resulting bounding boxes are scaled back up to
    the mask's original resolution.

    Returns:
        {
            "regions": [ {min_x, min_y, max_x, max_y, area} ... ]  # analysis-scale coords
            "scale_x": float,
            "scale_y": float,
            "error": None or "<message>"
        }
    """
    result = {"regions": [], "scale_x": 1.0, "scale_y": 1.0, "error": None}

    try:
        original_w, original_h = mask_image.size
        analysis_img = mask_image.copy()
        analysis_img.thumbnail((max_analysis_dim, max_analysis_dim), Image.NEAREST)
        aw, ah = analysis_img.size

        if aw == 0 or ah == 0:
            result["error"] = "Mask image became empty after downscaling."
            return result

        scale_x = original_w / aw
        scale_y = original_h / ah
        result["scale_x"] = scale_x
        result["scale_y"] = scale_y

        pixels = analysis_img.load()
        visited = [[False] * aw for _ in range(ah)]
        regions = []

        for start_y in range(ah):
            for start_x in range(aw):
                if visited[start_y][start_x]:
                    continue
                if pixels[start_x, start_y] < 128:
                    visited[start_y][start_x] = True
                    continue

                # BFS flood fill for this connected component
                queue = deque()
                queue.append((start_x, start_y))
                visited[start_y][start_x] = True

                min_x = max_x = start_x
                min_y = max_y = start_y
                area = 0

                while queue:
                    x, y = queue.popleft()
                    area += 1
                    if x < min_x:
                        min_x = x
                    if x > max_x:
                        max_x = x
                    if y < min_y:
                        min_y = y
                    if y > max_y:
                        max_y = y

                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= nx < aw and 0 <= ny < ah and not visited[ny][nx]:
                            if pixels[nx, ny] >= 128:
                                visited[ny][nx] = True
                                queue.append((nx, ny))
                            else:
                                visited[ny][nx] = True

                if area >= min_region_pixels:
                    regions.append({
                        "min_x": min_x, "min_y": min_y,
                        "max_x": max_x, "max_y": max_y,
                        "area": area,
                    })

        regions.sort(key=lambda r: r["area"], reverse=True)
        result["regions"] = regions

    except Exception as e:
        result["error"] = f"Unexpected error while analyzing evidence regions: {e}"

    return result


# ---------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------

def create_evidence_map(file_path: str) -> dict:
    """
    Build the full Stage 5 Evidence Map for a given image file.

    Always returns a dictionary with a consistent shape, even on
    failure, so the GUI never has to guess which keys exist.
    """
    output = {
        "success": False,
        "status": "error",
        "error": None,
        "message": "",
        "map_path": None,
        "overlay_path": None,
        "region_count": 0,
        "affected_percentage": 0.0,
        "largest_region": None,
        "regions": [],
        "observations": [],
    }

    # --- Step 1: basic image inspection ---
    try:
        with Image.open(file_path) as img:
            img.verify()
        with Image.open(file_path) as img:
            image_format = img.format or "UNKNOWN"
            width, height = img.size
    except FileNotFoundError:
        output["error"] = "File not found. It may have been moved or deleted."
        return output
    except (OSError, SyntaxError):
        output["error"] = "The image could not be opened (corrupted or unsupported format)."
        return output
    except Exception as e:
        output["error"] = f"Unexpected error while inspecting the image: {e}"
        return output

    if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
        output["status"] = "error"
        output["error"] = (
            f"Image is too small ({width}x{height} px) for a reliable Evidence Map analysis."
        )
        return output

    # --- Step 2: applicability check (JPEG only, same rule as Stage 4 ELA) ---
    if not _is_jpeg_applicable(file_path, image_format):
        output["status"] = "not_applicable"
        output["error"] = None
        output["message"] = (
            "Evidence Map requires a JPEG ELA result. This image "
            f"is {image_format}, so JPEG-based Error Level Analysis does not apply, "
            "and no Evidence Map can be generated."
        )
        return output

    # --- Step 3: run ELA (reuses Stage 4's existing, unmodified function) ---
    try:
        ela_result = perform_ela(file_path)
    except Exception as e:
        output["status"] = "error"
        output["error"] = f"Unexpected error while running ELA for the Evidence Map: {e}"
        return output

    if ela_result["error"]:
        output["status"] = "error"
        output["error"] = ela_result["error"]
        return output

    diff_image = ela_result["diff_image"]
    if diff_image is None:
        output["status"] = "error"
        output["error"] = "No ELA difference image was available to build an Evidence Map."
        return output

    try:
        # --- Step 4: grayscale + threshold ---
        gray = diff_image.convert("L")

        try:
            stat = ImageStat.Stat(gray)
            mean_val = stat.mean[0]
            stddev_val = stat.stddev[0]
        except Exception:
            mean_val, stddev_val = 0.0, 0.0

        threshold_value = mean_val + (THRESHOLD_MULTIPLIER * stddev_val)
        threshold_value = max(MIN_THRESHOLD, min(MAX_THRESHOLD, threshold_value))

        mask = gray.point(lambda p: 255 if p >= threshold_value else 0)

        # --- Step 5: cleanup isolated noise pixels ---
        try:
            mask = mask.filter(ImageFilter.MedianFilter(size=3))
        except Exception:
            pass  # cleanup is best-effort; continue with unfiltered mask if it fails

        # --- Step 6: affected percentage (computed on the full-resolution mask) ---
        histogram = mask.histogram()
        on_pixels = histogram[255] if len(histogram) > 255 else 0
        total_pixels = width * height
        affected_percentage = round((on_pixels / total_pixels) * 100, 2) if total_pixels > 0 else 0.0

        # --- Step 7: connected-region detection ---
        region_result = analyze_evidence_regions(mask)
        if region_result["error"]:
            output["status"] = "error"
            output["error"] = region_result["error"]
            return output

        scale_x = region_result["scale_x"]
        scale_y = region_result["scale_y"]
        raw_regions = region_result["regions"]

        regions_output = []
        for r in raw_regions[:MAX_REGIONS_RETURNED]:
            orig_x = int(r["min_x"] * scale_x)
            orig_y = int(r["min_y"] * scale_y)
            orig_w = max(1, int((r["max_x"] - r["min_x"] + 1) * scale_x))
            orig_h = max(1, int((r["max_y"] - r["min_y"] + 1) * scale_y))
            approx_area_px = int(r["area"] * scale_x * scale_y)
            regions_output.append({
                "x": orig_x, "y": orig_y,
                "width": orig_w, "height": orig_h,
                "approx_area_px": approx_area_px,
            })

        region_count = len(raw_regions)
        largest_region = regions_output[0] if regions_output else None

        # --- Step 8: build overlay on a COPY of the original image ---
        with Image.open(file_path) as original:
            original.load()
            original_rgb = original.convert("RGB")

        tint_layer = Image.new("RGB", original_rgb.size, (255, 45, 45))
        blended_color = Image.blend(original_rgb, tint_layer, 0.45)
        overlay_img = Image.composite(blended_color, original_rgb, mask)

        if regions_output:
            draw = ImageDraw.Draw(overlay_img)
            outline_width = max(2, int(min(original_rgb.size) / 300))
            for r in regions_output:
                box = [r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"]]
                draw.rectangle(box, outline=(255, 230, 0), width=outline_width)

        # --- Step 9: save generated files (never overwrite the original) ---
        output_dir = _ensure_output_dir()
        safe_base = _safe_base_name(file_path)
        timestamp = int(time.time())

        map_filename = f"{safe_base}_evidencemask_{timestamp}.png"
        overlay_filename = f"{safe_base}_evidencemap_{timestamp}.png"
        map_path = os.path.join(output_dir, map_filename)
        overlay_path = os.path.join(output_dir, overlay_filename)

        mask.save(map_path, "PNG")
        overlay_img.save(overlay_path, "PNG")

        # --- Step 10: plain-language, non-conclusive observations ---
        observations = []
        if region_count == 0:
            observations.append(
                "No regions exceeded the difference threshold. This does not confirm "
                "that the image is unedited - it simply means no strong localized "
                "differences were found at this threshold."
            )
        else:
            observations.append(
                f"{region_count} potentially interesting region(s) were detected based on "
                "higher ELA differences."
            )
            observations.append(
                "Highlighted areas show a higher ELA difference relative to the rest of "
                "the image. This is a forensic indicator, not a conclusion."
            )
        observations.append(
            f"Approximately {affected_percentage}% of the image area exceeded the "
            "difference threshold used for this Evidence Map."
        )
        observations.append(
            "Highlighted regions require further investigation and must not be treated "
            "as proof that any area was edited, faked, or manipulated."
        )

        output.update({
            "success": True,
            "status": "success",
            "error": None,
            "message": "Evidence Map generated successfully.",
            "map_path": map_path,
            "overlay_path": overlay_path,
            "region_count": region_count,
            "affected_percentage": affected_percentage,
            "largest_region": largest_region,
            "regions": regions_output,
            "observations": observations,
        })
        return output

    except PermissionError:
        output["status"] = "error"
        output["error"] = "Permission denied while generating or saving the Evidence Map."
        return output
    except OSError as e:
        output["status"] = "error"
        output["error"] = f"A file system error occurred while generating the Evidence Map: {e}"
        return output
    except Exception as e:
        output["status"] = "error"
        output["error"] = f"Unexpected error while generating the Evidence Map: {e}"
        return output