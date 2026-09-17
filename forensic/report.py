"""
forensic/report.py

Professional PDF forensic report generator for TrueSnap.

Produces a clean, investigation-oriented report containing:
- Case / analysis header with timestamp
- File identity & SHA-256 fingerprint
- Origin heuristics summary
- Metadata highlights
- ELA statistics & observations
- Evidence Map summary
- Clear methodological disclaimers

Designed for journalists, investigators, legal support, and content teams.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)


# Brand colours matching the UI
_CYAN = colors.HexColor("#22d3ee")
_DARK = colors.HexColor("#0a0e14")
_SURFACE = colors.HexColor("#111720")
_TEXT = colors.HexColor("#e7edf3")
_MUTED = colors.HexColor("#8a97a8")
_WARN = colors.HexColor("#fbbf24")
_SUCCESS = colors.HexColor("#34d399")
_BORDER = colors.HexColor("#232c3a")


def _styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "TSTitle",
            parent=base["Heading1"],
            fontSize=22,
            textColor=_CYAN,
            spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "subtitle": ParagraphStyle(
            "TSSubtitle",
            parent=base["Normal"],
            fontSize=10,
            textColor=_MUTED,
            spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "TSH2",
            parent=base["Heading2"],
            fontSize=13,
            textColor=_CYAN,
            spaceBefore=14,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "TSBody",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#1a1f2e"),
            leading=13,
            alignment=TA_JUSTIFY,
        ),
        "small": ParagraphStyle(
            "TSSmall",
            parent=base["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#4a5568"),
            leading=11,
        ),
        "mono": ParagraphStyle(
            "TSMono",
            parent=base["Normal"],
            fontSize=8,
            fontName="Courier",
            textColor=colors.HexColor("#0e7490"),
            leading=11,
        ),
        "warning": ParagraphStyle(
            "TSWarn",
            parent=base["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#92400e"),
            leading=11,
            backColor=colors.HexColor("#fef3c7"),
            borderPadding=6,
        ),
        "label": ParagraphStyle(
            "TSLabel",
            parent=base["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#64748b"),
            fontName="Helvetica-Bold",
        ),
        "value": ParagraphStyle(
            "TSValue",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#0f172a"),
        ),
    }
    return styles


def _kv_table(rows: list[tuple[str, str]], col_widths=None) -> Table:
    data = [[Paragraph(k, _styles()["label"]), Paragraph(str(v), _styles()["value"])] for k, v in rows]
    t = Table(data, colWidths=col_widths or [45 * mm, 130 * mm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    return t


def generate_forensic_report(
    output_path: str,
    *,
    file_path: str,
    basic_info: dict,
    sha256: Optional[str],
    metadata: dict,
    heuristics: dict,
    ela_result: Optional[dict] = None,
    evidence_map: Optional[dict] = None,
    analyst_note: str = "",
    comparison: Optional[dict] = None,
    stats: Optional[dict] = None,
) -> dict:
    """
    Write a professional PDF report to output_path.

    Returns {"success": True/False, "path": ..., "error": ...}
    """
    result = {"success": False, "path": None, "error": None}

    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title="TrueSnap Forensic Report",
            author="TrueSnap",
        )

        styles = _styles()
        story = []

        # Header
        story.append(Paragraph("TRUESNAP", styles["title"]))
        story.append(Paragraph(
            "Digital Image Forensics & Evidence Integrity Report",
            styles["subtitle"],
        ))
        story.append(HRFlowable(width="100%", thickness=1.5, color=_CYAN, spaceAfter=8))

        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        story.append(Paragraph(f"<b>Generated:</b> {generated}", styles["small"]))
        story.append(Paragraph(
            "<b>Purpose:</b> Contextual forensic indicators for investigation support. "
            "This report does not constitute legal proof of authenticity or manipulation.",
            styles["small"],
        ))
        story.append(Spacer(1, 8))

        # 1. File Identity
        story.append(Paragraph("1. File Identity", styles["h2"]))
        identity_rows = [
            ("File name", basic_info.get("file_name", "—")),
            ("Path", file_path),
            ("Size", basic_info.get("file_size", "—")),
            ("Format", basic_info.get("image_format", "—")),
            ("Dimensions", f"{basic_info.get('width', '—')} × {basic_info.get('height', '—')}"),
            ("Color mode", basic_info.get("color_mode", "—")),
            ("Aspect ratio", basic_info.get("aspect_ratio", "—")),
        ]
        story.append(_kv_table(identity_rows))
        story.append(Spacer(1, 6))

        # Hash
        story.append(Paragraph("Cryptographic Fingerprint (SHA-256)", styles["label"]))
        hash_text = sha256 or "Not computed"
        story.append(Paragraph(hash_text, styles["mono"]))
        story.append(Paragraph(
            "SHA-256 identifies the exact byte content of this file. Any alteration "
            "produces a completely different hash. It does not describe visual content.",
            styles["small"],
        ))

        # 2. Origin Heuristics
        story.append(Paragraph("2. Origin Heuristics (Screenshot vs Camera)", styles["h2"]))
        if heuristics.get("error"):
            story.append(Paragraph(f"Analysis unavailable: {heuristics['error']}", styles["body"]))
        else:
            story.append(_kv_table([
                ("Assessment", heuristics.get("confidence_label", "—")),
                ("Contextual score", f"{heuristics.get('score', 0)} / 100 (indicator only)"),
                ("Summary", heuristics.get("summary", "—")),
            ]))
            signals = heuristics.get("signals") or []
            if signals:
                story.append(Paragraph("Observed signals:", styles["label"]))
                items = [ListItem(Paragraph(s, styles["small"]), leftIndent=10) for s in signals]
                story.append(ListFlowable(items, bulletType="bullet", start="•"))
            recs = heuristics.get("recommendations") or []
            if recs:
                story.append(Paragraph("Suggested next steps:", styles["label"]))
                items = [ListItem(Paragraph(r, styles["small"]), leftIndent=10) for r in recs]
                story.append(ListFlowable(items, bulletType="bullet", start="•"))

        # 3. Metadata
        story.append(Paragraph("3. Embedded Metadata", styles["h2"]))
        if metadata.get("error"):
            story.append(Paragraph(str(metadata["error"]), styles["body"]))
        else:
            meta_rows = []
            for section, key in [
                ("DateTimeOriginal", "datetime"),
                ("DateTime", "datetime"),
                ("Make", "device"),
                ("Model", "device"),
                ("Software", "software"),
            ]:
                bucket = metadata.get(key) or {}
                if section in bucket:
                    meta_rows.append((section, bucket[section]))
            if metadata.get("orientation") is not None:
                meta_rows.append(("Orientation", str(metadata["orientation"])))
            if not meta_rows:
                meta_rows.append(("Status", "No significant EXIF fields recovered"))
            story.append(_kv_table(meta_rows))

            indicators = metadata.get("indicators") or []
            if indicators:
                story.append(Paragraph("Metadata indicators:", styles["label"]))
                items = [ListItem(Paragraph(i, styles["small"]), leftIndent=10) for i in indicators]
                story.append(ListFlowable(items, bulletType="bullet", start="•"))

        # 4. ELA
        story.append(Paragraph("4. Error Level Analysis (ELA)", styles["h2"]))
        if not ela_result or ela_result.get("status") in (None, "error") and not ela_result.get("ela_available"):
            msg = (ela_result or {}).get("error") or (ela_result or {}).get("message") or "ELA was not run or is not applicable (JPEG recommended)."
            story.append(Paragraph(str(msg), styles["body"]))
        else:
            dims = "—"
            if ela_result.get("width") and ela_result.get("height"):
                dims = f"{ela_result['width']} × {ela_result['height']}"
            story.append(_kv_table([
                ("ELA availability", "Yes" if ela_result.get("ela_available") else ela_result.get("status", "—")),
                ("Mean difference", str(ela_result.get("mean_difference", "—"))),
                ("Max difference", str(ela_result.get("max_difference", "—"))),
                ("Dimensions", dims),
            ]))
            obs = ela_result.get("observations") or []
            if obs:
                story.append(Paragraph("Observations:", styles["label"]))
                items = [ListItem(Paragraph(o, styles["small"]), leftIndent=10) for o in obs]
                story.append(ListFlowable(items, bulletType="bullet", start="•"))

            # Embed ELA image if available
            ela_path = ela_result.get("ela_image_path")
            if ela_path and os.path.isfile(ela_path):
                try:
                    story.append(Spacer(1, 6))
                    story.append(Paragraph("ELA visualization:", styles["label"]))
                    img = RLImage(ela_path, width=140 * mm, height=90 * mm, kind="proportional")
                    story.append(img)
                except Exception:
                    pass

        # 5. Evidence Map
        story.append(Paragraph("5. Evidence Map", styles["h2"]))
        if not evidence_map or evidence_map.get("error"):
            msg = (evidence_map or {}).get("error") or "Evidence Map was not generated."
            story.append(Paragraph(msg, styles["body"]))
        else:
            story.append(_kv_table([
                ("Detected regions", str(evidence_map.get("region_count", "—"))),
                ("Affected area", evidence_map.get("affected_percentage", "—")),
                ("Largest region", evidence_map.get("largest_region", "—")),
            ]))
            obs = evidence_map.get("observations") or []
            if obs:
                story.append(Paragraph("Observations:", styles["label"]))
                items = [ListItem(Paragraph(o, styles["small"]), leftIndent=10) for o in obs]
                story.append(ListFlowable(items, bulletType="bullet", start="•"))

            overlay = evidence_map.get("overlay_path")
            if overlay and os.path.isfile(overlay):
                try:
                    story.append(Spacer(1, 6))
                    story.append(Paragraph("Evidence Map overlay:", styles["label"]))
                    img = RLImage(overlay, width=140 * mm, height=90 * mm, kind="proportional")
                    story.append(img)
                except Exception:
                    pass

        # Technical stats
        if stats and not stats.get("error"):
            story.append(Paragraph("Technical Image Profile", styles["h2"]))
            story.append(_kv_table([
                ("Megapixels", str(stats.get("megapixels", "—"))),
                ("Brightness (avg)", str(stats.get("brightness", "—"))),
                ("Mean RGB", str(stats.get("mean_rgb", "—"))),
                ("StdDev RGB", str(stats.get("stddev_rgb", "—"))),
                ("Unique colors (est.)", str(stats.get("unique_colors_est", "—"))),
            ]))
            for n in (stats.get("notes") or [])[:4]:
                story.append(Paragraph(f"• {n}", styles["small"]))

        # Comparison section
        if comparison and comparison.get("status") in ("success", "partial"):
            story.append(Paragraph("Image Comparison", styles["h2"]))
            story.append(_kv_table([
                ("Hashes match", "Yes" if comparison.get("hashes_match") else "No"),
                ("Byte-identical", "Yes" if comparison.get("identical_bytes") else "No"),
                ("Mean pixel difference", str(comparison.get("mean_abs_diff", "—"))),
                ("Changed pixels", f"{comparison.get('changed_pixel_pct')}%" if comparison.get("changed_pixel_pct") is not None else "—"),
            ]))
            if comparison.get("summary"):
                story.append(Paragraph(comparison["summary"], styles["body"]))
            for ind in (comparison.get("indicators") or [])[:5]:
                story.append(Paragraph(f"• {ind}", styles["small"]))
            sbs = comparison.get("side_by_side_path")
            if sbs and os.path.isfile(sbs):
                try:
                    story.append(Spacer(1, 4))
                    story.append(Paragraph("Side-by-side + difference:", styles["label"]))
                    img = RLImage(sbs, width=160 * mm, height=70 * mm, kind="proportional")
                    story.append(img)
                except Exception:
                    pass

        # Analyst note
        if analyst_note.strip():
            story.append(Paragraph("6. Analyst Note", styles["h2"]))
            story.append(Paragraph(analyst_note.strip(), styles["body"]))

        # Disclaimer
        story.append(Spacer(1, 12))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=6))
        story.append(Paragraph(
            "<b>Methodological disclaimer.</b> TrueSnap produces contextual forensic "
            "indicators only. Error Level Analysis highlights recompression differences; "
            "it does not prove that an image is authentic, fake, or edited. Origin "
            "heuristics are statistical signals, not classifications. Always combine "
            "these results with independent corroboration, original device extraction "
            "when available, and qualified human review before drawing conclusions.",
            styles["warning"],
        ))

        story.append(Spacer(1, 10))
        story.append(Paragraph(
            "Generated by TrueSnap — Digital Image Forensics & Evidence Integrity Analyzer",
            styles["small"],
        ))

        doc.build(story)
        result["success"] = True
        result["path"] = output_path

    except Exception as e:
        result["error"] = str(e)

    return result
