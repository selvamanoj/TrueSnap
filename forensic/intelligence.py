"""
forensic/intelligence.py

Image Intelligence Report generator.

Builds a structured, human-readable briefing about an image:
identity, technical profile, origin, content/use-case signals,
soft AI-generation clues, and practical "what this may be used for".

Limitations are stated clearly — especially for AI detection and
content understanding without a vision model.
"""

from __future__ import annotations

import os
from typing import Any

from forensic.file_info import get_basic_file_info
from forensic.metadata import get_metadata
from forensic.hashing import compute_sha256
from forensic.heuristics import analyze_origin_heuristics
from forensic.stats import compute_image_stats


# Common app / OS screenshot fingerprints (soft)
_APP_HINTS = [
    ("whatsapp", ["whatsapp", "wa.statusbar", "com.whatsapp"]),
    ("instagram", ["instagram", "com.instagram"]),
    ("telegram", ["telegram", "org.telegram"]),
    ("twitter/x", ["twitter", "x-client", "com.twitter"]),
    ("facebook", ["facebook", "com.facebook"]),
    ("chrome", ["chrome", "chromium"]),
    ("safari", ["safari", "mobile safari"]),
    ("edge", ["edg/", "microsoft edge"]),
    ("windows snip", ["snippingtool", "screen sketch", "snipping tool"]),
    ("android system", ["android", "screenshot_"]),
    ("ios", ["iphone", "ios", "mobile"]),
]


def _software_blob(meta: dict) -> str:
    soft = meta.get("software") or {}
    other = meta.get("other") or {}
    parts = [str(v).lower() for v in list(soft.values()) + list(other.values())]
    return " ".join(parts)


def _guess_source_app(meta: dict, basic: dict, heur: dict) -> list[str]:
    hints = []
    blob = _software_blob(meta)
    name = (basic.get("file_name") or "").lower()
    for app, keys in _APP_HINTS:
        if any(k in blob or k in name for k in keys):
            hints.append(f"Possible link to **{app}** (filename or software metadata).")
    if heur.get("likely_screenshot") and not hints:
        hints.append("Looks consistent with a screenshot, but the specific app is not identified from metadata.")
    if not hints:
        hints.append("No clear app/source fingerprint in metadata or filename.")
    return hints


def _use_case_suggestions(heur: dict, basic: dict, meta: dict, stats: dict) -> list[str]:
    """Practical 'what this image could be used for' — investigative framing."""
    uses = []
    is_ss = heur.get("likely_screenshot") or heur.get("score", 0) >= 45
    fmt = (basic.get("image_format") or "").upper()
    has_exif = meta.get("has_exif")

    if is_ss:
        uses.append("May be used as evidence of an on-screen conversation, transaction, error message, or app state.")
        uses.append("Often shared in disputes, customer support, or social proof — verify it was not edited or restaged.")
        uses.append("If used legally, prefer original device extraction over a re-shared screenshot file.")
    else:
        if has_exif and (meta.get("device") or {}):
            uses.append("May be a camera-origin photo suitable as primary visual evidence (still verify integrity via hash).")
        uses.append("Could be used in reporting, documentation, identity, or product contexts depending on content.")

    if fmt == "PNG" and is_ss:
        uses.append("PNG screenshots often preserve sharp UI text — good for reading interface content, weak as sole proof of authenticity.")

    br = stats.get("brightness")
    if br is not None and br < 35:
        uses.append("Image is dark — may be a night photo, dark-mode UI, or underexposed capture; interpret content cautiously.")

    if not uses:
        uses.append("Use case depends on visual content; TrueSnap does not auto-caption objects without a vision model.")
    return uses


def _ai_assessment(meta: dict, stats: dict, heur: dict) -> dict[str, Any]:
    """
    Soft AI-generation assessment. NOT a reliable detector.
    """
    score = 0
    clues = []
    blob = _software_blob(meta)
    gen_keys = ["stable diffusion", "midjourney", "dall-e", "dall·e", "firefly", "generative",
                "novelai", "comfyui", "automatic1111", "leonardo"]
    for k in gen_keys:
        if k in blob:
            score += 40
            clues.append(f"Software/metadata mentions generative tooling ({k}).")

    if not meta.get("has_exif"):
        score += 10
        clues.append("No EXIF — common for AI exports, but also for screenshots and social downloads.")

    if heur.get("likely_screenshot"):
        score -= 15
        clues.append("Screenshot-like signals reduce (but do not eliminate) likelihood of a pure AI render.")

    # Low unique colors can be graphic/AI or simple UI
    uc = stats.get("unique_colors_est")
    if isinstance(uc, int) and uc < 40:
        score += 5
        clues.append("Low color diversity in sample — can appear in AI art, graphics, or flat UI screenshots.")

    score = max(0, min(100, score))
    if score >= 50:
        label = "Elevated generative-tool signals"
        summary = ("Some metadata or patterns are consistent with generative-tool output. "
                   "This is NOT proof the image is AI-generated.")
    elif score >= 25:
        label = "Mixed / inconclusive"
        summary = "Weak or mixed signals only. Do not treat as AI or real based on this alone."
    else:
        label = "No strong generative-tool signals"
        summary = ("No strong generative-software fingerprints found. "
                   "Absence of signals does not prove a photograph is camera-original.")

    clues.append("Limitation: Reliable AI-image detection requires specialized models; TrueSnap only reports soft clues.")
    return {"score": score, "label": label, "summary": summary, "clues": clues}


def build_image_report(file_path: str) -> dict[str, Any]:
    """Full intelligence briefing for one image."""
    basic = get_basic_file_info(file_path)
    meta = get_metadata(file_path)
    h = compute_sha256(file_path)
    heur = analyze_origin_heuristics(file_path, basic, meta)
    stats = compute_image_stats(file_path)
    ai = _ai_assessment(meta, stats, heur)
    apps = _guess_source_app(meta, basic, heur)
    uses = _use_case_suggestions(heur, basic, meta, stats)

    narrative = []
    narrative.append(f"File: {basic.get('file_name', os.path.basename(file_path))}")
    narrative.append(
        f"Technical: {basic.get('image_format', '?')} · {basic.get('width', '?')} × {basic.get('height', '?')} · "
        f"{basic.get('file_size', '?')} · ~{stats.get('megapixels', '?')} MP"
    )
    narrative.append(f"Origin assessment: {heur.get('confidence_label', 'n/a')} (score {heur.get('score', 0)}/100).")
    narrative.append(heur.get("summary") or "")
    narrative.append(f"AI-tool signals: {ai['label']}. {ai['summary']}")
    narrative.append("Possible source: " + "; ".join(apps[:2]))
    narrative.append("Possible uses: " + uses[0] if uses else "")

    auto_notes = "\n".join([
        f"Image intelligence summary for {basic.get('file_name', file_path)}",
        f"SHA-256: {h.get('hash') or 'n/a'}",
        f"Origin: {heur.get('confidence_label')} ({heur.get('score', 0)}/100)",
        f"AI-tool signals: {ai['label']} ({ai['score']}/100) — soft clues only",
        "Source hints: " + "; ".join(apps[:3]),
        "Use-case notes: " + " ".join(uses[:2]),
        "Disclaimer: Contextual indicators only. Not legal proof of authenticity, source app, or AI generation.",
    ])

    return {
        "basic": basic,
        "sha256": h.get("hash"),
        "metadata": meta,
        "heuristics": heur,
        "stats": stats,
        "ai": ai,
        "source_hints": apps,
        "use_cases": uses,
        "narrative": [n for n in narrative if n],
        "auto_notes": auto_notes,
        "path": file_path,
    }
