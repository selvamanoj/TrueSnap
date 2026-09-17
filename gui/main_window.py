"""
TrueSnap — complete UI redesign.

Layout philosophy (from scratch):
- Large hero image area (primary focus)
- Right intelligence report (scrollable cards)
- Bottom mode switcher (single image / compare)
- High-contrast surfaces, clear typography
- Enlarge on click always available
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional, List

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageEnhance

from forensic.file_info import get_basic_file_info, is_supported_image
from forensic.metadata import get_metadata
from forensic.hashing import compute_sha256, compare_hashes
from forensic.image_forensics import analyze_image_forensics
from forensic.evidence_map import create_evidence_map
from forensic.heuristics import analyze_origin_heuristics
from forensic.compare import compare_images
from forensic.stats import compute_image_stats
from forensic.intelligence import build_image_report
from forensic.report import generate_forensic_report


# ── Fresh palette ──────────────────────────────────────────────────────────
BG = "#0b0f14"
PANEL = "#12181f"
CARD = "#171e28"
CARD2 = "#1c2430"
LINE = "#2a3444"
CYAN = "#2ee6a6"
CYAN_D = "#1aa87a"
TEXT = "#eef3f8"
MUTED = "#8b9aab"
DIM = "#5c6b7a"
WARN = "#ffc14d"
BAD = "#ff6b6b"
OK = "#3dde8c"

FT = ("Segoe UI Semibold", 16)
FH = ("Segoe UI Semibold", 11)
FB = ("Segoe UI", 10)
FS = ("Segoe UI", 9)
FX = ("Segoe UI", 8)
FM = ("Consolas", 9)


class TrueSnapApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TrueSnap")
        self.geometry("1360x700")
        self.minsize(1120, 640)
        self.configure(bg=BG)

        self.path: Optional[str] = None
        self.path_b: Optional[str] = None
        self.report: dict = {}
        self.cmp: dict = {}
        self.ela: dict = {}
        self.emap: dict = {}
        self.notes = ""
        self.mode = "single"  # single | compare
        self._photo = None
        self._photo_b = None
        self._cmp_photo = None

        self._style()
        self._build()
        self._setup_bindings()
        self._show_welcome()
        self._status("Open an image to generate a full intelligence report")

    def _style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("Go.TButton", background=CYAN_D, foreground="#062018", font=("Segoe UI Semibold", 9),
                    padding=(14, 7), borderwidth=0)
        s.map("Go.TButton", background=[("active", CYAN)])
        s.configure("Soft.TButton", background=CARD2, foreground=TEXT, font=("Segoe UI Semibold", 9),
                    padding=(12, 7), borderwidth=0)
        s.map("Soft.TButton", background=[("active", LINE)])
        s.configure("Vertical.TScrollbar", background=CARD2, troughcolor=PANEL, arrowcolor=DIM, width=10)

    def _setup_bindings(self):
        self.bind("<Control-o>", lambda e: self.open_image())
        self.bind("<Control-e>", lambda e: self.export_pdf())
        self.bind("<Control-j>", lambda e: self.export_json())

    def _status(self, msg, err=False):
        self.status_lbl.config(text=msg, fg=BAD if err else MUTED)

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        left = tk.Frame(hdr, bg=BG)
        left.pack(side="left", padx=18, pady=10)
        tk.Label(left, text="TRUESNAP", font=FT, fg=TEXT, bg=BG).pack(side="left")
        tk.Label(left, text="  Image Intelligence", font=FS, fg=DIM, bg=BG).pack(side="left", pady=(4, 0))

        right = tk.Frame(hdr, bg=BG)
        right.pack(side="right", padx=18)
        ttk.Button(right, text="Open image", style="Go.TButton", command=self.open_image).pack(side="left", padx=3)
        ttk.Button(right, text="Compare mode", style="Soft.TButton", command=self.toggle_compare).pack(side="left", padx=3)
        ttk.Button(right, text="PDF report", style="Soft.TButton", command=self.export_pdf).pack(side="left", padx=3)
        ttk.Button(right, text="JSON", style="Soft.TButton", command=self.export_json).pack(side="left", padx=3)

        # Main split
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        # LEFT: hero media
        self.left = tk.Frame(main, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        media_bar = tk.Frame(self.left, bg=PANEL)
        media_bar.pack(fill="x", padx=12, pady=(10, 4))
        self.media_title = tk.Label(media_bar, text="Preview", font=FH, fg=TEXT, bg=PANEL)
        self.media_title.pack(side="left")
        ttk.Button(media_bar, text="View full size", style="Soft.TButton", command=self.enlarge_main).pack(side="right")

        self.hero = tk.Label(self.left, bg="#0a0e13", fg=DIM, text="Open an image to begin",
                             font=FB, cursor="hand2")
        self.hero.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.hero.bind("<Double-Button-1>", lambda e: self.enlarge_main())
        self.hero.bind("<Button-1>", lambda e: self.enlarge_main())

        # RIGHT: intelligence report
        self.right = tk.Frame(main, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        self.right.grid(row=0, column=1, sticky="nsew")

        rb = tk.Frame(self.right, bg=PANEL)
        rb.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(rb, text="Intelligence report", font=FH, fg=TEXT, bg=PANEL).pack(side="left")
        ttk.Button(rb, text="Run ELA", style="Soft.TButton", command=self.run_ela).pack(side="right", padx=2)
        ttk.Button(rb, text="Auto notes", style="Soft.TButton", command=self.fill_notes).pack(side="right", padx=2)

        # Scroll report
        wrap = tk.Frame(self.right, bg=PANEL)
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas = tk.Canvas(wrap, bg=PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.report_host = tk.Frame(self.canvas, bg=PANEL)
        self.report_host.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.report_host, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        # Status
        st = tk.Frame(self, bg=CARD, height=22)
        st.pack(fill="x", side="bottom")
        st.pack_propagate(False)
        self.status_lbl = tk.Label(st, text="", font=FX, fg=MUTED, bg=CARD, anchor="w")
        self.status_lbl.pack(fill="x", padx=14, pady=2)

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _clear_report(self):
        for w in self.report_host.winfo_children():
            w.destroy()

    def _card(self, title: str) -> tk.Frame:
        box = tk.Frame(self.report_host, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        box.pack(fill="x", pady=4, padx=2)
        tk.Label(box, text=title, font=FH, fg=CYAN, bg=CARD).pack(anchor="w", padx=10, pady=(8, 2))
        body = tk.Frame(box, bg=CARD)
        body.pack(fill="x", padx=10, pady=(0, 8))
        return body

    def _line(self, parent, label, value, bold=False):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=1)
        tk.Label(row, text=label, font=FX, fg=DIM, bg=CARD, width=14, anchor="w").pack(side="left")
        tk.Label(row, text=str(value) if value not in (None, "") else "—",
                 font=FM if bold else FS, fg=CYAN if bold else TEXT, bg=CARD,
                 anchor="w", wraplength=280, justify="left").pack(side="left", fill="x", expand=True)

    def _para(self, parent, text, color=TEXT):
        tk.Label(parent, text=text, font=FS, fg=color, bg=CARD, wraplength=300, justify="left",
                 anchor="w").pack(anchor="w", pady=1)

    def _show_welcome(self):
        self._clear_report()
        b = self._card("Get started")
        self._para(b, "1. Open an image — TrueSnap builds a full intelligence report.")
        self._para(b, "2. Read origin, technical details, use-case notes, and AI-tool signals.")
        self._para(b, "3. Use Compare mode to analyze differences between two files in writing.")
        self._para(b, "4. Export PDF or JSON for your case file.")
        self._para(b, "Click the preview anytime to open a large viewer.", MUTED)

    # ── Image load & report ────────────────────────────────────────────────
    def open_image(self):
        p = filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp")])
        if not p:
            return
        if not is_supported_image(p):
            messagebox.showwarning("Format", "Use JPG, PNG, BMP, or WebP.")
            return
        self.path = p
        self.mode = "single"
        self._status("Building intelligence report…")
        self.update_idletasks()
        self.report = build_image_report(p)
        self.notes = self.report.get("auto_notes") or ""
        self.ela = {}
        self.emap = {}
        self._render_hero(p)
        self._render_report()
        self._status(f"Report ready · {os.path.basename(p)}")

    def _boost(self, im: Image.Image) -> Image.Image:
        """Slightly increase contrast/brightness so preview is easier to see."""
        im = ImageEnhance.Contrast(im).enhance(1.12)
        im = ImageEnhance.Brightness(im).enhance(1.06)
        return im

    def _render_hero(self, path: str, secondary: str = None):
        try:
            im = Image.open(path).convert("RGB")
            im = self._boost(im)
            # Large hero fit
            im.thumbnail((720, 480), Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(im)
            self.hero.config(image=self._photo, text="")
            self.media_title.config(text=os.path.basename(path))
        except Exception as e:
            self.hero.config(image="", text=f"Could not preview\n{e}")

    def _render_report(self):
        self._clear_report()
        r = self.report
        if not r:
            self._show_welcome()
            return

        basic = r.get("basic") or {}
        stats = r.get("stats") or {}
        heur = r.get("heuristics") or {}
        ai = r.get("ai") or {}
        meta = r.get("metadata") or {}

        # Identity
        c = self._card("File identity")
        self._line(c, "Name", basic.get("file_name"))
        self._line(c, "Format", basic.get("image_format"))
        self._line(c, "Size", basic.get("file_size"))
        self._line(c, "Dimensions", f"{basic.get('width')} × {basic.get('height')}")
        self._line(c, "Megapixels", stats.get("megapixels"))
        self._line(c, "SHA-256", (r.get("sha256") or "")[:28] + "…", bold=True)

        # Narrative summary
        c = self._card("Summary")
        for line in (r.get("narrative") or [])[:6]:
            self._para(c, "• " + line)

        # Origin
        c = self._card("Origin (screenshot vs camera)")
        self._line(c, "Assessment", heur.get("confidence_label"))
        self._line(c, "Score", f"{heur.get('score', 0)}/100")
        self._para(c, heur.get("summary") or "")
        for s in (heur.get("signals") or [])[:4]:
            self._para(c, "▸ " + s, MUTED)

        # Source / app hints
        c = self._card("Possible source / app")
        for h in (r.get("source_hints") or []):
            self._para(c, "• " + h.replace("**", ""))

        # What it can be used for
        c = self._card("What this image may be used for")
        for u in (r.get("use_cases") or []):
            self._para(c, "• " + u)

        # AI signals
        c = self._card("AI-generation signals (soft only)")
        self._line(c, "Level", ai.get("label"))
        self._line(c, "Score", f"{ai.get('score', 0)}/100")
        self._para(c, ai.get("summary") or "")
        for cl in (ai.get("clues") or [])[:4]:
            self._para(c, "▸ " + cl, MUTED)

        # Technical
        c = self._card("Technical profile")
        self._line(c, "Brightness", stats.get("brightness"))
        self._line(c, "Mean RGB", stats.get("mean_rgb"))
        self._line(c, "Colors (est.)", stats.get("unique_colors_est"))
        self._line(c, "Color mode", basic.get("color_mode") or stats.get("mode"))
        for n in (stats.get("notes") or [])[:3]:
            self._para(c, "▸ " + n, MUTED)

        # Metadata highlights
        c = self._card("Metadata highlights")
        dt = meta.get("datetime") or {}
        dev = meta.get("device") or {}
        soft = meta.get("software") or {}
        if dt:
            for k, v in list(dt.items())[:3]:
                self._line(c, k, v)
        if dev:
            for k, v in list(dev.items())[:3]:
                self._line(c, k, v)
        if soft:
            for k, v in list(soft.items())[:2]:
                self._line(c, k, v)
        if not (dt or dev or soft):
            self._para(c, "No significant EXIF fields recovered.")
        for ind in (meta.get("indicators") or [])[:3]:
            self._para(c, "⚠ " + ind, WARN)

        # ELA snippet if run
        if self.ela:
            c = self._card("ELA (if run)")
            self._line(c, "Status", self.ela.get("status"))
            self._line(c, "Mean Δ", self.ela.get("mean_difference"))
            for o in (self.ela.get("observations") or [])[:3]:
                self._para(c, "• " + o, MUTED)

        # Compare section if available
        if self.cmp and self.mode == "compare":
            self._render_compare_section()

        # Notes box
        c = self._card("Case notes (editable)")
        self.notes_box = tk.Text(c, height=5, bg=CARD2, fg=TEXT, insertbackground=TEXT,
                                 font=FS, relief="flat", wrap="word")
        self.notes_box.pack(fill="x", pady=2)
        self.notes_box.insert("1.0", self.notes)

    def _render_compare_section(self):
        cmp = self.cmp
        c = self._card("Comparison — written differences")
        if cmp.get("identical_bytes"):
            self._para(c, "RESULT: The two files are byte-for-byte identical. No content difference.", OK)
        else:
            self._para(c, "RESULT: The two files are different.", WARN)
        self._line(c, "Changed pixels", f"{cmp.get('changed_pixel_pct')}%")
        self._line(c, "Mean pixel Δ", cmp.get("mean_abs_diff"))
        self._line(c, "Max channel Δ", cmp.get("max_channel_diff"))
        self._para(c, "Detailed explanation:", CYAN)
        for exp in (cmp.get("explanations") or []):
            self._para(c, "• " + exp)
        if cmp.get("metadata_deltas"):
            self._para(c, "Metadata fields that differ:", CYAN)
            for d in cmp["metadata_deltas"][:6]:
                self._para(c, f"  {d['field']}: {d['a']} → {d['b']}", MUTED)
        for n in (cmp.get("ai_notes") or [])[:2]:
            self._para(c, n, MUTED)

    # ── Compare mode ───────────────────────────────────────────────────────
    def toggle_compare(self):
        if not self.path:
            messagebox.showinfo("Open image first", "Open Image A first, then choose Image B.")
            return
        b = filedialog.askopenfilename(title="Select second image (B)",
                                       filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp")])
        if not b or not is_supported_image(b):
            return
        self.path_b = b
        self.mode = "compare"
        self._status("Comparing images and writing difference report…")
        self.update_idletasks()
        self.cmp = compare_images(self.path, self.path_b)
        if self.cmp.get("auto_notes"):
            self.notes = (self.notes + "\n\n" if self.notes else "") + self.cmp["auto_notes"]
        # Hero shows side-by-side if available
        sbs = self.cmp.get("side_by_side_path")
        if sbs and os.path.isfile(sbs):
            try:
                im = Image.open(sbs)
                im = self._boost(im)
                im.thumbnail((780, 420), Image.Resampling.LANCZOS)
                self._cmp_photo = ImageTk.PhotoImage(im)
                self.hero.config(image=self._cmp_photo, text="")
                self.media_title.config(text="Comparison · A | B | Difference")
            except Exception:
                self._render_hero(self.path)
        else:
            self._render_hero(self.path)
        self._render_report()
        self._status("Comparison complete — read written differences in the report panel")

    # ── ELA ────────────────────────────────────────────────────────────────
    def run_ela(self):
        if not self.path:
            return
        self._status("Running Error Level Analysis…")
        self.update_idletasks()
        self.ela = analyze_image_forensics(self.path)
        if self.ela.get("status") == "success" and self.ela.get("ela_image_path"):
            try:
                im = Image.open(self.ela["ela_image_path"])
                im = self._boost(im)
                im.thumbnail((720, 420), Image.Resampling.LANCZOS)
                self._photo = ImageTk.PhotoImage(im)
                self.hero.config(image=self._photo, text="")
                self.media_title.config(text="ELA visualization (brighter = higher difference)")
            except Exception:
                pass
        self._render_report()
        st = self.ela.get("status")
        self._status("ELA finished" if st == "success" else self.ela.get("message") or st or "ELA done")

    def fill_notes(self):
        if self.report.get("auto_notes"):
            self.notes = self.report["auto_notes"]
            if self.cmp.get("auto_notes"):
                self.notes += "\n\n" + self.cmp["auto_notes"]
            self._render_report()
            self._status("Case notes filled from analysis")
        else:
            messagebox.showinfo("No report", "Open an image first.")

    def enlarge_main(self):
        path = None
        if self.mode == "compare" and self.cmp.get("side_by_side_path"):
            path = self.cmp["side_by_side_path"]
        elif self.ela.get("ela_image_path") and "ELA" in (self.media_title.cget("text") or ""):
            path = self.ela["ela_image_path"]
        else:
            path = self.path
        if not path:
            return
        win = tk.Toplevel(self)
        win.title("Full size view")
        win.configure(bg=BG)
        win.geometry("1000x720")
        try:
            im = Image.open(path).convert("RGB")
            im = self._boost(im)
            im.thumbnail((960, 680), Image.Resampling.LANCZOS)
            ph = ImageTk.PhotoImage(im)
            lbl = tk.Label(win, image=ph, bg=BG)
            lbl.image = ph
            lbl.pack(expand=True, padx=10, pady=10)
        except Exception as e:
            tk.Label(win, text=str(e), fg=BAD, bg=BG).pack(padx=20, pady=20)

    # ── Export ─────────────────────────────────────────────────────────────
    def _grab_notes(self):
        if hasattr(self, "notes_box"):
            try:
                self.notes = self.notes_box.get("1.0", "end").strip()
            except Exception:
                pass

    def export_pdf(self):
        if not self.path:
            messagebox.showinfo("No image", "Open an image first.")
            return
        self._grab_notes()
        out = filedialog.asksaveasfilename(defaultextension=".pdf",
                                           initialfile=f"TrueSnap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                           filetypes=[("PDF", "*.pdf")])
        if not out:
            return
        r = self.report
        res = generate_forensic_report(
            out,
            file_path=self.path,
            basic_info=r.get("basic") or get_basic_file_info(self.path),
            sha256=r.get("sha256"),
            metadata=r.get("metadata") or {},
            heuristics=r.get("heuristics") or {},
            ela_result=self.ela or None,
            evidence_map=self.emap or None,
            analyst_note=self.notes,
            comparison=self.cmp or None,
            stats=r.get("stats"),
        )
        if res.get("success"):
            self._status(f"PDF saved · {out}")
            messagebox.showinfo("Saved", out)
        else:
            self._status(res.get("error", "PDF failed"), err=True)

    def export_json(self):
        if not self.path:
            messagebox.showinfo("No image", "Open an image first.")
            return
        self._grab_notes()
        out = filedialog.asksaveasfilename(defaultextension=".json",
                                           initialfile=f"TrueSnap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                                           filetypes=[("JSON", "*.json")])
        if not out:
            return
        payload = {
            "generated": datetime.now().isoformat(timespec="seconds"),
            "intelligence_report": self.report,
            "comparison": self.cmp or None,
            "ela": self.ela or None,
            "case_notes": self.notes,
            "disclaimer": "Contextual indicators only. Not proof of authenticity, source app, or AI generation.",
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
        self._status(f"JSON saved · {out}")


# entrypoint name expected by main.py
MainWindow = TrueSnapApp

if __name__ == "__main__":
    TrueSnapApp().mainloop()
