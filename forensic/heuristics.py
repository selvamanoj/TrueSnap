"""
forensic/heuristics.py

Contextual image origin heuristics for TrueSnap.

Provides lightweight, explainable signals that help distinguish common
screenshot characteristics from typical camera-captured photos.

IMPORTANT:
These are *heuristics and indicators only*. They never claim certainty
about authenticity, manipulation, or origin. Results must be interpreted
together with hash, metadata, ELA, and human review.
"""

from __future__ import annotations

import os
from typing import Any

from PIL import Image


# Common screenshot resolutions (width, height) – both orientations
_COMMON_SCREEN_RESOLUTIONS = {
    (1080, 1920), (1920, 1080),
    (1170, 2532), (2532, 1170),   # iPhone 12/13
    (1284, 2778), (2778, 1284),   # iPhone 12/13 Pro Max
    (1179, 2556), (2556, 1179),   # iPhone 14/15
    (1290, 2796), (2796, 1290),   # iPhone 14/15 Pro Max
    (1206, 2622), (2622, 1206),
    (1320, 2868), (2868, 1320),
    (1440, 3200), (3200, 1440),
    (1440, 2560), (2560, 1440),
    (1080, 2400), (2400, 1080),
    (1080, 2340), (2340, 1080),
    (720, 1280), (1280, 720),
    (1366, 768), (768, 1366),
    (1536, 2048), (2048, 1536),  # iPad
    (1668, 2388), (2388, 1668),
    (2048, 2732), (2732, 2048),
}


def analyze_origin_heuristics(file_path: str, basic_info: dict, metadata: dict) -> dict[str, Any]:
    """
    Produce contextual origin indicators.

    Returns a structured dict safe for UI and report consumption.
    """
    result: dict[str, Any] = {
        "likely_screenshot": False,
        "confidence_label": "Low signal",
        "score": 0,                 # 0–100 contextual only
        "signals": [],
        "summary": "Insufficient signals to form an origin hypothesis.",
        "recommendations": [],
        "error": None,
    }

    if not file_path or not os.path.isfile(file_path):
        result["error"] = "File not available for heuristic analysis."
        return result

    try:
        width = height = None
        if basic_info.get("width") and basic_info.get("height"):
            try:
                width = int(str(basic_info["width"]).replace(" px", "").strip())
                height = int(str(basic_info["height"]).replace(" px", "").strip())
            except (ValueError, TypeError):
                pass

        if width is None or height is None:
            with Image.open(file_path) as im:
                width, height = im.size

        score = 0
        signals: list[str] = []

        # --- Signal 1: Missing EXIF (very common for screenshots) ---
        has_exif = bool(metadata.get("has_exif"))
        if not has_exif:
            score += 28
            signals.append(
                "No EXIF metadata detected. Screenshots and many social-media "
                "exports commonly strip camera data."
            )
        else:
            # Presence of camera make/model reduces screenshot likelihood
            device = metadata.get("device") or {}
            if device.get("Make") or device.get("Model"):
                score -= 18
                signals.append(
                    f"Camera/device tags present ({device.get('Make', '')} "
                    f"{device.get('Model', '')}). More consistent with a "
                    "native capture than a typical screenshot."
                )

        # --- Signal 2: Software tags that suggest editing / capture tools ---
        software = metadata.get("software") or {}
        soft_str = " ".join(str(v).lower() for v in software.values())
        screenshot_soft = ("screenshot", "snipping", "greenshot", "lightshot",
                           "sharex", "monoshot", "cleanshot", "picpick")
        if any(s in soft_str for s in screenshot_soft):
            score += 35
            signals.append(
                f"Software metadata suggests a screen-capture tool: {software}"
            )
        elif "photoshop" in soft_str or "gimp" in soft_str or "affinity" in soft_str:
            score += 12
            signals.append(
                "Editing software detected in metadata. Image may have been "
                "opened or re-saved in an editor (common for both real photos "
                "and screenshots)."
            )

        # --- Signal 3: Exact common screen resolutions ---
        if width and height:
            dims = (width, height)
            if dims in _COMMON_SCREEN_RESOLUTIONS:
                score += 22
                signals.append(
                    f"Dimensions {width}×{height} match a common mobile/desktop "
                    "screen resolution, frequently seen in screenshots."
                )
            # Very tall aspect ratios are also common on phones
            aspect = max(width, height) / max(1, min(width, height))
            if aspect > 1.9:
                score += 8
                signals.append(
                    f"Tall aspect ratio ({aspect:.2f}:1) is typical of modern "
                    "smartphone screenshots."
                )

        # --- Signal 4: PNG without EXIF is classic screenshot pattern ---
        fmt = (basic_info.get("image_format") or "").upper()
        if fmt == "PNG" and not has_exif:
            score += 15
            signals.append(
                "PNG format combined with absent EXIF is a frequent pattern "
                "for screenshots and UI captures."
            )

        # Clamp and label
        score = max(0, min(100, score))
        result["score"] = score

        if score >= 55:
            result["likely_screenshot"] = True
            result["confidence_label"] = "Strong screenshot indicators"
            result["summary"] = (
                "Multiple independent signals are consistent with a screenshot "
                "or screen-captured image rather than a direct camera capture."
            )
            result["recommendations"] = [
                "Treat visual content as potentially secondary evidence.",
                "Request original camera file or device extraction if chain of custody matters.",
                "Cross-check timestamps and surrounding conversation context.",
            ]
        elif score >= 30:
            result["likely_screenshot"] = False
            result["confidence_label"] = "Mixed / possible screenshot signals"
            result["summary"] = (
                "Some signals lean toward screenshot characteristics, but the "
                "evidence is not decisive. Further context is required."
            )
            result["recommendations"] = [
                "Inspect ELA and Evidence Map for local inconsistencies.",
                "Compare with any claimed original source file via SHA-256.",
            ]
        else:
            result["likely_screenshot"] = False
            result["confidence_label"] = "More consistent with camera / original capture"
            result["summary"] = (
                "Available signals do not strongly suggest a typical screenshot. "
                "This does not prove the image is an unaltered original."
            )
            result["recommendations"] = [
                "Still verify integrity with the cryptographic hash.",
                "Review ELA for possible localized editing even on camera images.",
            ]

        if not signals:
            signals.append("No strong origin signals were detected from available metadata and dimensions.")

        result["signals"] = signals

    except Exception as e:
        result["error"] = f"Heuristic analysis failed: {e}"

    return result
