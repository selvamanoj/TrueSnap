"""
forensic/image_forensics.py

Image Forensics Engine - Stage 4.

Implements Error Level Analysis (ELA), primarily useful for JPEG images,
to surface recompression-related pixel differences as a CONTEXTUAL
forensic indicator.

IMPORTANT FORENSIC DISCLAIMER:
ELA highlights differences caused by recompression and other image-
processing effects. It does NOT, by itself, prove that an image is
authentic, fake, edited, or manipulated. Results must be interpreted
alongside other evidence.

The original uploaded file is NEVER modified. All recompression work
happens on temporary, in-memory or temp-file copies which are cleaned
up after use.
"""

import os
import time
import tempfile

from PIL import Image, ImageChops, ImageStat

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

ELA_QUALITY = 90       # JPEG quality used for the recompressed comparison copy
ELA_SCALE = 15         # Amplification factor so differences are visible to the eye

# Formats for which JPEG-based ELA is meaningful
_JPEG_EXTENSIONS = (".jpg", ".jpeg")
_JPEG_FORMATS = ("JPEG",)

# Project-root-relative output directory: <project_root>/data/forensics
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORENSICS_OUTPUT_DIR = os.path.join(_BASE_DIR, "data", "forensics")


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _is_jpeg_source(file_path: str, image_format: str) -> bool:
    """Determine whether ELA is applicable based on format/extension."""
    if image_format and image_format.upper() in _JPEG_FORMATS:
        return True
    ext = os.path.splitext(file_path)[1].lower()
    return ext in _JPEG_EXTENSIONS


def _ensure_forensics_dir() -> str:
    """Create the data/forensics output directory if it doesn't exist."""
    os.makedirs(FORENSICS_OUTPUT_DIR, exist_ok=True)
    return FORENSICS_OUTPUT_DIR


# ---------------------------------------------------------------------
# Core ELA steps
# ---------------------------------------------------------------------

def perform_ela(file_path: str, quality: int = ELA_QUALITY) -> dict:
    """
    Re-save the image as JPEG at a controlled quality level and compute
    the raw pixel-difference image between the original and the
    recompressed copy.

    The original file on disk is never touched - a temporary file is
    used for the recompressed copy and is deleted afterward.

    Returns:
        {
            "diff_image": PIL.Image or None,
            "error": None or "<message>"
        }
    """
    result = {"diff_image": None, "error": None}
    temp_path = None

    try:
        with Image.open(file_path) as original:
            original.load()
            original_rgb = original.convert("RGB")
    except FileNotFoundError:
        result["error"] = "File not found while performing ELA."
        return result
    except (OSError, SyntaxError):
        result["error"] = "The image could not be opened for ELA (corrupted or unsupported)."
        return result
    except Exception as e:
        result["error"] = f"Unexpected error while opening image for ELA: {e}"
        return result

    try:
        fd, temp_path = tempfile.mkstemp(suffix=".jpg", prefix="truesnap_ela_")
        os.close(fd)

        original_rgb.save(temp_path, "JPEG", quality=quality)

        with Image.open(temp_path) as recompressed:
            recompressed.load()
            recompressed_rgb = recompressed.convert("RGB")

        diff_image = ImageChops.difference(original_rgb, recompressed_rgb)
        result["diff_image"] = diff_image

    except PermissionError:
        result["error"] = "Permission denied while writing the temporary recompression file."
    except OSError as e:
        result["error"] = f"A file system error occurred during ELA processing: {e}"
    except Exception as e:
        result["error"] = f"Unexpected error while performing ELA: {e}"
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass  # Best-effort cleanup; never crash on cleanup failure

    return result


def calculate_ela_statistics(diff_image) -> dict:
    """
    Calculate simple, explainable statistics from an ELA difference image.

    Returns:
        {
            "mean_difference": float or None,
            "max_difference": int or None,
            "error": None or "<message>"
        }
    """
    stats = {"mean_difference": None, "max_difference": None, "error": None}

    if diff_image is None:
        stats["error"] = "No difference image available to analyze."
        return stats

    try:
        stat = ImageStat.Stat(diff_image)
        # Average the per-channel means into a single overall figure
        stats["mean_difference"] = round(sum(stat.mean) / len(stat.mean), 3)

        extrema = diff_image.getextrema()  # e.g. ((r_min, r_max), (g_min, g_max), (b_min, b_max))
        max_val = max(channel_max for (_channel_min, channel_max) in extrema)
        stats["max_difference"] = max_val
    except Exception as e:
        stats["error"] = f"Unexpected error while calculating ELA statistics: {e}"

    return stats


def create_ela_visualization(diff_image, original_file_path: str, scale: int = ELA_SCALE) -> dict:
    """
    Amplify the raw ELA difference image so differences are visible to
    the human eye, then save it as a PNG inside data/forensics/.

    Returns:
        {
            "output_path": "<path>" or None,
            "error": None or "<message>"
        }
    """
    result = {"output_path": None, "error": None}

    if diff_image is None:
        result["error"] = "No difference image available to visualize."
        return result

    try:
        amplified = diff_image.point(lambda x: min(255, x * scale))
    except Exception as e:
        result["error"] = f"Unexpected error while amplifying ELA visualization: {e}"
        return result

    try:
        output_dir = _ensure_forensics_dir()
        base_name = os.path.splitext(os.path.basename(original_file_path))[0]
        # Sanitize the base name lightly to avoid filesystem issues
        safe_base = "".join(c for c in base_name if c.isalnum() or c in ("_", "-")) or "image"
        timestamp = int(time.time())
        output_filename = f"{safe_base}_ela_{timestamp}.png"
        output_path = os.path.join(output_dir, output_filename)

        amplified.save(output_path, "PNG")
        result["output_path"] = output_path
    except PermissionError:
        result["error"] = "Permission denied while saving the ELA visualization."
    except OSError as e:
        result["error"] = f"Could not save the ELA visualization: {e}"
    except Exception as e:
        result["error"] = f"Unexpected error while saving ELA visualization: {e}"

    return result


# ---------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------

def analyze_image_forensics(file_path: str) -> dict:
    """
    Run the full Stage 4 forensic analysis pipeline for a given image.

    Always returns a dictionary with a consistent shape, even on
    failure or when ELA is not applicable, so the GUI never has to
    guess which keys exist.

    Returns:
        {
            "status": "success" | "not_applicable" | "error",
            "message": "<human-readable summary>",
            "image_format": "<format>" or None,
            "width": int or None,
            "height": int or None,
            "ela_available": bool,
            "ela_image_path": "<path>" or None,
            "mean_difference": float or None,
            "max_difference": int or None,
            "observations": [list of strings],
        }
    """
    output = {
        "status": "error",
        "message": "",
        "image_format": None,
        "width": None,
        "height": None,
        "ela_available": False,
        "ela_image_path": None,
        "mean_difference": None,
        "max_difference": None,
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
        output["message"] = "File not found. It may have been moved or deleted."
        return output
    except (OSError, SyntaxError):
        output["message"] = "The image could not be opened (corrupted or unsupported format)."
        return output
    except Exception as e:
        output["message"] = f"Unexpected error while inspecting the image: {e}"
        return output

    output["image_format"] = image_format
    output["width"] = width
    output["height"] = height

    # --- Step 2: applicability check ---
    if not _is_jpeg_source(file_path, image_format):
        output["status"] = "not_applicable"
        output["message"] = (
            "ELA not applicable: this analysis is primarily useful for JPEG images, "
            f"because it measures differences introduced by JPEG recompression. "
            f"The selected file is {image_format}, which was not JPEG-compressed to "
            "begin with, so ELA results would not be meaningful here."
        )
        output["observations"].append(
            "Image forensics provides contextual indicators and does not by itself prove "
            "that an image is authentic, fake, edited, or manipulated."
        )
        return output

    # --- Step 3: perform ELA ---
    ela_result = perform_ela(file_path)
    if ela_result["error"]:
        output["status"] = "error"
        output["message"] = ela_result["error"]
        return output

    diff_image = ela_result["diff_image"]

    # --- Step 4: statistics ---
    stats = calculate_ela_statistics(diff_image)
    if stats["error"]:
        output["status"] = "error"
        output["message"] = stats["error"]
        return output

    output["mean_difference"] = stats["mean_difference"]
    output["max_difference"] = stats["max_difference"]

    # --- Step 5: visualization ---
    viz_result = create_ela_visualization(diff_image, file_path)
    if viz_result["error"]:
        output["status"] = "error"
        output["message"] = viz_result["error"]
        return output

    output["ela_image_path"] = viz_result["output_path"]
    output["ela_available"] = True
    output["status"] = "success"
    output["message"] = "ELA visualization generated successfully."

    # --- Step 6: plain-language observations ---
    observations = ["ELA visualization generated successfully."]

    mean_diff = output["mean_difference"]
    max_diff = output["max_difference"]

    if mean_diff is not None and max_diff is not None:
        if max_diff < 20:
            observations.append(
                "Differences across the image are low and fairly uniform, which may be "
                "consistent with a single, normal JPEG compression pass."
            )
        elif max_diff >= 20 and (mean_diff == 0 or (max_diff / max(mean_diff, 0.01)) > 8):
            observations.append(
                "Some localized regions show noticeably higher differences than the rest "
                "of the image. Higher local differences may indicate regions that "
                "underwent a different compression or processing history, but can also "
                "occur naturally around edges, text, or high-contrast detail."
            )
        else:
            observations.append(
                "Differences are moderate and spread across the image, which may be "
                "consistent with normal JPEG recompression."
            )

    observations.append(
        "ELA findings are contextual indicators and require interpretation alongside "
        "other evidence - they are not conclusive on their own."
    )
    observations.append(
        "Image forensics provides contextual indicators and does not by itself prove "
        "that an image is authentic, fake, edited, or manipulated."
    )

    output["observations"] = observations
    return output