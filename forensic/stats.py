"""
forensic/stats.py

Lightweight technical image statistics for TrueSnap.
Provides quick quantifiable signals useful in investigations.
"""

from __future__ import annotations

import os
from typing import Any

from PIL import Image, ImageStat


def compute_image_stats(file_path: str) -> dict[str, Any]:
    result = {
        "error": None,
        "mode": None,
        "width": None,
        "height": None,
        "megapixels": None,
        "mean_rgb": None,
        "stddev_rgb": None,
        "brightness": None,
        "unique_colors_est": None,
        "is_grayscale": False,
        "aspect": None,
        "notes": [],
    }
    if not file_path or not os.path.isfile(file_path):
        result["error"] = "File not found."
        return result
    try:
        with Image.open(file_path) as im:
            im.load()
            result["mode"] = im.mode
            w, h = im.size
            result["width"], result["height"] = w, h
            result["megapixels"] = round((w * h) / 1_000_000, 2)
            result["aspect"] = round(w / h, 3) if h else None

            rgb = im.convert("RGB")
            st = ImageStat.Stat(rgb)
            means = [round(x, 1) for x in st.mean]
            stds = [round(x, 1) for x in st.stddev]
            result["mean_rgb"] = means
            result["stddev_rgb"] = stds
            result["brightness"] = round(sum(means) / 3, 1)

            # Grayscale check
            if abs(means[0] - means[1]) < 2 and abs(means[1] - means[2]) < 2:
                result["is_grayscale"] = True
                result["notes"].append("Channels are nearly equal — image may be grayscale or desaturated.")

            # Estimate unique colors on a downscaled version (fast)
            small = rgb.copy()
            small.thumbnail((120, 120))
            colors = small.getcolors(maxcolors=120 * 120)
            if colors is not None:
                result["unique_colors_est"] = len(colors)
                if len(colors) < 64:
                    result["notes"].append(
                        f"Low color diversity (~{len(colors)} unique in sample) — possible heavy compression, screenshot, or graphic."
                    )
            else:
                result["unique_colors_est"] = "high"

            if result["brightness"] is not None:
                if result["brightness"] < 40:
                    result["notes"].append("Overall dark image.")
                elif result["brightness"] > 210:
                    result["notes"].append("Overall very bright image.")

    except Exception as e:
        result["error"] = str(e)
    return result
