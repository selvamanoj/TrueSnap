"""
forensic/compare.py — Image Comparison with clear plain-language explanations.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from PIL import Image, ImageChops, ImageStat, ImageDraw, ImageFont

from forensic.hashing import compute_sha256, compare_hashes
from forensic.metadata import get_metadata
from forensic.file_info import get_basic_file_info


def _open_rgb(path: str) -> Optional[Image.Image]:
    try:
        im = Image.open(path)
        im.load()
        return im.convert("RGB")
    except Exception:
        return None


def _explain_difference(mean_diff: float, changed_pct: float, max_diff: int,
                        hashes_match: bool, dims_match: bool) -> list[str]:
    """Produce clear, non-technical explanations of what differs."""
    lines = []

    if hashes_match:
        lines.append("The two files are exactly the same at the byte level (identical SHA-256). There is no difference in content or metadata encoding.")
        return lines

    lines.append("The two files are NOT identical — their SHA-256 hashes differ, so something about the file data changed.")

    if not dims_match:
        lines.append("The images have different dimensions (width/height). One may be cropped, resized, or from a different source.")

    # Visual magnitude
    if mean_diff is not None and changed_pct is not None:
        if mean_diff < 1.0 and changed_pct < 1.5:
            lines.append(
                f"Visual difference is VERY SMALL (average pixel change ≈ {mean_diff}, "
                f"only about {changed_pct}% of pixels differ noticeably). "
                "This often means: re-saving as JPEG, slight compression change, or metadata-only edit — not a major visual edit."
            )
        elif mean_diff < 5 and changed_pct < 8:
            lines.append(
                f"Visual difference is SMALL to MODERATE (average pixel change ≈ {mean_diff}, "
                f"~{changed_pct}% of pixels differ). Possible causes: re-encoding, mild filtering, color adjustment, or localized touch-ups."
            )
        elif changed_pct < 25:
            lines.append(
                f"Visual difference is NOTICEABLE (~{changed_pct}% of pixels differ, average change ≈ {mean_diff}). "
                "Something visible was likely altered, added, removed, or the image was significantly reprocessed."
            )
        else:
            lines.append(
                f"Visual difference is LARGE (~{changed_pct}% of pixels differ). "
                "The images may be different photos, heavily edited, or one may be a different version entirely."
            )

    if max_diff is not None and max_diff >= 200:
        lines.append("Some pixels differ by a large amount (high max channel difference). Check the DIFFERENCE panel — bright spots mark the strongest changes.")

    return lines


def _ai_related_signals(meta_a: dict, meta_b: dict, stats_notes: list) -> list[str]:
    """
    Cautious signals only. We cannot reliably detect AI generation from
    simple heuristics; we only surface soft clues and state the limitation.
    """
    notes = []
    notes.append(
        "AI-generation detection: TrueSnap does NOT reliably detect AI-generated images. "
        "Specialized classifiers are required for that. Below are only soft contextual clues."
    )

    for label, meta in (("A", meta_a), ("B", meta_b)):
        soft = " ".join(str(v).lower() for v in (meta.get("software") or {}).values())
        if any(k in soft for k in ("stable diffusion", "midjourney", "dall·e", "dall-e", "firefly", "generative")):
            notes.append(f"Image {label} software metadata mentions a generative tool name — treat as a clue only, not proof.")
        if not meta.get("has_exif"):
            notes.append(f"Image {label} has no EXIF — common for AI exports, screenshots, and social-media downloads (not specific to AI).")

    return notes


def compare_images(path_a: str, path_b: str, output_dir: str = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "error",
        "error": None,
        "hash_a": None,
        "hash_b": None,
        "hashes_match": False,
        "identical_bytes": False,
        "dimensions_match": False,
        "size_a": None,
        "size_b": None,
        "mean_abs_diff": None,
        "changed_pixel_pct": None,
        "max_channel_diff": None,
        "diff_image_path": None,
        "side_by_side_path": None,
        "metadata_deltas": [],
        "summary": "",
        "explanations": [],      # clear plain-language list
        "ai_notes": [],
        "indicators": [],
        "basic_a": {},
        "basic_b": {},
        "auto_notes": "",        # ready-to-use case note paragraph
    }

    if not path_a or not os.path.isfile(path_a):
        result["error"] = "Image A not found."
        return result
    if not path_b or not os.path.isfile(path_b):
        result["error"] = "Image B not found."
        return result

    ha = compute_sha256(path_a)
    hb = compute_sha256(path_b)
    result["hash_a"] = ha.get("hash")
    result["hash_b"] = hb.get("hash")
    result["hashes_match"] = compare_hashes(result["hash_a"], result["hash_b"])
    result["identical_bytes"] = result["hashes_match"]
    result["basic_a"] = get_basic_file_info(path_a)
    result["basic_b"] = get_basic_file_info(path_b)

    img_a = _open_rgb(path_a)
    img_b = _open_rgb(path_b)
    if img_a is None or img_b is None:
        result["error"] = "Could not open one or both images."
        result["status"] = "partial"
        result["summary"] = "Hash comparison only — visual analysis failed."
        result["explanations"] = [
            "Files could not be fully decoded for pixel comparison.",
            f"Hashes match: {'Yes' if result['hashes_match'] else 'No'}.",
        ]
        return result

    result["size_a"] = img_a.size
    result["size_b"] = img_b.size
    result["dimensions_match"] = img_a.size == img_b.size

    work_b = img_b
    if img_a.size != img_b.size:
        work_b = img_b.resize(img_a.size, Image.Resampling.LANCZOS)
        result["indicators"].append(
            f"Dimensions differ: A={img_a.size[0]}×{img_a.size[1]}, B={img_b.size[0]}×{img_b.size[1]}. B was resized for pixel comparison."
        )

    diff = ImageChops.difference(img_a, work_b)
    st = ImageStat.Stat(diff)
    mean_diff = sum(st.mean) / len(st.mean)
    result["mean_abs_diff"] = round(mean_diff, 3)
    extrema = diff.getextrema()
    max_diff = max(ch[1] for ch in extrema)
    result["max_channel_diff"] = max_diff

    gray = diff.convert("L")
    hist = gray.histogram()
    total = sum(hist) or 1
    changed = sum(hist[8:])
    result["changed_pixel_pct"] = round(changed / total * 100, 2)

    # Metadata deltas
    meta_a = get_metadata(path_a)
    meta_b = get_metadata(path_b)
    deltas = []
    for section in ("datetime", "device", "software"):
        da, db = meta_a.get(section) or {}, meta_b.get(section) or {}
        for k in sorted(set(da) | set(db)):
            va, vb = da.get(k), db.get(k)
            if va != vb:
                deltas.append({"field": f"{section}.{k}", "a": va or "—", "b": vb or "—"})
    result["metadata_deltas"] = deltas[:15]

    # Output images (larger for readability)
    if output_dir is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(base, "data", "forensics")
    os.makedirs(output_dir, exist_ok=True)
    ts = int(time.time())
    safe = "".join(c for c in os.path.splitext(os.path.basename(path_a))[0] if c.isalnum() or c in "_-")[:18]

    ampl = diff.point(lambda p: min(255, int(p * 14)))
    diff_path = os.path.join(output_dir, f"compare_diff_{safe}_{ts}.png")
    ampl.save(diff_path)
    result["diff_image_path"] = diff_path

    # Larger side-by-side
    max_side = 520
    wa, ha_ = img_a.size
    scale = min(1.0, max_side / max(wa, ha_))
    disp_a = img_a.resize((int(wa * scale), int(ha_ * scale)), Image.Resampling.LANCZOS)
    disp_b = work_b.resize(disp_a.size, Image.Resampling.LANCZOS)
    disp_d = ampl.resize(disp_a.size, Image.Resampling.LANCZOS)

    gap, label_h = 10, 24
    sw, sh = disp_a.size
    canvas = Image.new("RGB", (sw * 3 + gap * 2, sh + label_h + 6), (12, 18, 28))
    canvas.paste(disp_a, (0, label_h))
    canvas.paste(disp_b, (sw + gap, label_h))
    canvas.paste(disp_d, (sw * 2 + gap * 2, label_h))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        font = ImageFont.load_default()
    draw.text((6, 5), "IMAGE A (reference)", fill=(34, 211, 238), font=font)
    draw.text((sw + gap + 6, 5), "IMAGE B (suspect)", fill=(34, 211, 238), font=font)
    draw.text((sw * 2 + gap * 2 + 6, 5), "DIFFERENCE (bright = changed)", fill=(251, 191, 36), font=font)

    sbs_path = os.path.join(output_dir, f"compare_sbs_{safe}_{ts}.png")
    canvas.save(sbs_path)
    result["side_by_side_path"] = sbs_path

    # Explanations
    result["explanations"] = _explain_difference(
        result["mean_abs_diff"], result["changed_pixel_pct"], max_diff,
        result["hashes_match"], result["dimensions_match"]
    )
    if deltas:
        result["explanations"].append(
            f"{len(deltas)} metadata field(s) differ (for example timestamps, camera, or software tags). See the list for details."
        )
    result["ai_notes"] = _ai_related_signals(meta_a, meta_b, [])

    if result["identical_bytes"]:
        result["summary"] = "Files are byte-for-byte identical."
    else:
        result["summary"] = (
            f"Files differ. Visual change: ~{result['changed_pixel_pct']}% pixels, "
            f"mean pixel Δ {result['mean_abs_diff']}."
        )

    # Auto case notes
    lines = [
        f"Comparison performed on {time.strftime('%Y-%m-%d %H:%M')}.",
        f"Image A: {os.path.basename(path_a)}",
        f"Image B: {os.path.basename(path_b)}",
        f"SHA-256 match: {'YES — identical files' if result['hashes_match'] else 'NO — files differ'}.",
    ]
    lines.extend(result["explanations"][:4])
    if result["metadata_deltas"]:
        lines.append("Metadata differences were found; review fields in the comparison panel.")
    lines.append("Note: TrueSnap provides contextual indicators only and does not prove authenticity, forgery, or AI generation.")
    result["auto_notes"] = "\n".join(lines)

    result["status"] = "success"
    return result
