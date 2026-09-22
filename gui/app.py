"""Signal Analysis Workstation -- native Tkinter desktop app.

Single window: left panel for file input + configuration, right panel with
tabs matching the pipeline stages -- Signal Isolation, Evidence Extraction,
Hypothesis & Demodulation, and Recovery Information. Each tab carries its own
plots (waveform/waterfall, spectrum, constellation) alongside its data, rather
than a separate Visualization tab. Calls straight into core/.
"""
import os
import sys
import csv
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.io.iq_reader import read_iq
from core.io.wav_reader import read_wav
from core.io.metadata_parser import parse_metadata
from core.pipeline.pipeline_config import PipelineConfig
from core.pipeline.analyzer import run_pipeline
from core.hypotheses.modulation_candidates import CANDIDATE_REGISTRY
from core.hypotheses.fec_candidates import FEC_CANDIDATES
from core.hypotheses.interleaving_candidates import INTERLEAVING_CANDIDATES
from core.correlation.payload_detection import bits_to_hex

from gui.style import apply_theme, MUTED, TEXT, GOOD, BAD, ACCENT
from gui.plots import WaveformWaterfallPlots, SpectrumPlot, ConstellationPlot

IQ_DTYPES = ["int8", "uint8", "int16", "float32", "float64"]

VERDICT_COLORS = {"determined": GOOD, "user_selected": ACCENT, "ambiguous": "#b26a00",
                  "insufficient_evidence": BAD}
VERDICT_TITLES = {"determined": "Determined", "user_selected": "User-selected", "ambiguous": "Ambiguous",
                  "insufficient_evidence": "Insufficient evidence"}


def to_jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if hasattr(obj, "__dict__"):
        return {k: to_jsonable(v) for k, v in vars(obj).items()}
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj


def fmt_num(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.1f}" if abs(v) >= 1000 else f"{v:.3f}"
    return str(v)


class SignalAnalysisApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Signal Analysis Workstation")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        width, height = min(1500, int(sw * 0.94)), min(980, int(sh * 0.92))
        self.geometry(f"{width}x{height}+{(sw - width) // 2}+{max(0, (sh - height) // 2 - 20)}")
        self.minsize(1000, 640)
        try:
            self.state("zoomed")  # open maximized (Windows); falls back to the sized geometry above elsewhere
        except tk.TclError:
            pass
        apply_theme(self)

        self.file_path = None
        self.format_var = tk.StringVar(value="")
        self.samplerate_var = tk.StringVar()
        self.dtype_var = tk.StringVar(value="float32")
        self.centerfreq_var = tk.StringVar(value="0")
        self.mode_var = tk.StringVar(value="automatic")

        self.manual_mod_var = tk.StringVar()
        self.manual_symrate_var = tk.StringVar()
        self.manual_deint_var = tk.StringVar(value="none")
        self.manual_fec_var = tk.StringVar(value="none")

        self.mod_vars = {}
        self.deint_vars = {}
        self.fec_vars = {}

        self.result = None
        self.msg_queue = queue.Queue()

        self._build_header()
        self._build_body()
        self.after(100, self._poll_queue)

    # ---------------------------------------------------------------- header
    def _build_header(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(20, 14))
        header.pack(fill="x")
        left = ttk.Frame(header, style="Header.TFrame")
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text="Signal Analysis Workstation", style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="Load a .iq/.wav file, configure the analysis, and run the pipeline.",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Label(header, text="◈ SIGNAL CORE", style="Brand.TLabel").pack(side="right")
        tk.Frame(self, bg="#d7dade", height=1).pack(fill="x")

    # ------------------------------------------------------------------ body
    def _build_body(self):
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Panel.TFrame", padding=16, width=380)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        left.grid_propagate(False)
        self._build_left_panel(left)

        right = ttk.Frame(body, style="Panel.TFrame", padding=16)
        right.grid(row=0, column=1, sticky="nsew")
        self._build_right_panel(right)

    # -------------------------------------------------------------- left ui
    def _build_left_panel(self, parent):
        # Run button + progress are packed FIRST at the bottom so they stay
        # visible no matter how much configuration content is above them.
        bottom = ttk.Frame(parent, style="Inner.TFrame")
        bottom.pack(side="bottom", fill="x")
        ttk.Separator(bottom).pack(fill="x", pady=(0, 8))
        self.run_button = ttk.Button(bottom, text="Run Analysis", style="Accent.TButton",
                                      command=self.run_analysis, state="disabled")
        self.run_button.pack(fill="x")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(bottom, variable=self.progress_var, maximum=100,
                                             style="Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", pady=(8, 3))
        self.status_label = ttk.Label(bottom, text="Idle", style="PanelMuted.TLabel", wraplength=330)
        self.status_label.pack(anchor="w", fill="x")

        ttk.Label(parent, text="1. Input file", style="SectionHeading.TLabel").pack(anchor="w")
        ttk.Button(parent, text="Browse .iq / .wav...", style="Secondary.TButton",
                   command=self.browse_file).pack(anchor="w", pady=(6, 3), fill="x")
        self.file_info_label = ttk.Label(parent, text="No file selected.", style="PanelMuted.TLabel",
                                          wraplength=330, justify="left")
        self.file_info_label.pack(anchor="w", pady=(0, 6), fill="x")

        ttk.Separator(parent).pack(fill="x", pady=4)

        ttk.Label(parent, text="2. Configuration", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))

        grid = ttk.Frame(parent, style="Inner.TFrame")
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, weight=1)

        self._grid_row(grid, 0, "Format", ttk.Entry(grid, textvariable=self.format_var, state="readonly"))
        self.samplerate_entry = ttk.Entry(grid, textvariable=self.samplerate_var)
        self._grid_row(grid, 1, "Sample rate (Hz)", self.samplerate_entry)
        self.dtype_combo = ttk.Combobox(grid, textvariable=self.dtype_var, values=IQ_DTYPES, state="readonly")
        self._grid_row(grid, 2, "IQ sample format", self.dtype_combo)
        self._grid_row(grid, 3, "Center frequency (Hz)", ttk.Entry(grid, textvariable=self.centerfreq_var))

        ttk.Separator(parent).pack(fill="x", pady=6)

        mode_frame = ttk.Frame(parent, style="Inner.TFrame")
        mode_frame.pack(fill="x")
        ttk.Radiobutton(mode_frame, text="Automatic (try all candidates)", variable=self.mode_var,
                         value="automatic", command=self._on_mode_change).pack(anchor="w")
        ttk.Radiobutton(mode_frame, text="Manual (specify parameters)", variable=self.mode_var,
                         value="manual", command=self._on_mode_change).pack(anchor="w", pady=(2, 4))

        self.manual_frame = ttk.Frame(parent, style="Inner.TFrame")
        mgrid = ttk.Frame(self.manual_frame, style="Inner.TFrame")
        mgrid.pack(fill="x")
        mgrid.grid_columnconfigure(1, weight=1)
        modulations = [c.name for c in CANDIDATE_REGISTRY]
        deint_types = [t for t in INTERLEAVING_CANDIDATES if t != "none"]
        fec_types = [f for f in FEC_CANDIDATES if f != "none"]
        self._grid_row(mgrid, 0, "Modulation", ttk.Combobox(mgrid, textvariable=self.manual_mod_var,
                                                              values=modulations, state="readonly"))
        self._grid_row(mgrid, 1, "Symbol rate (Hz)", ttk.Entry(mgrid, textvariable=self.manual_symrate_var))
        self._grid_row(mgrid, 2, "De-interleaving", ttk.Combobox(mgrid, textvariable=self.manual_deint_var,
                                                                   values=["none"] + deint_types, state="readonly"))
        self._grid_row(mgrid, 3, "FEC", ttk.Combobox(mgrid, textvariable=self.manual_fec_var,
                                                       values=["none"] + fec_types, state="readonly"))

        self.auto_frame = ttk.Frame(parent, style="Inner.TFrame")
        self._checkbox_group(self.auto_frame, "Modulations to try", modulations, self.mod_vars, columns=3)
        self._checkbox_group(self.auto_frame, "De-interleaving types", deint_types, self.deint_vars, columns=2)
        self._checkbox_group(self.auto_frame, "FEC types", fec_types, self.fec_vars, columns=2)

        self.auto_frame.pack(fill="x")

    def _grid_row(self, grid, row, label, widget):
        ttk.Label(grid, text=label, style="PanelMuted.TLabel").grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
        widget.grid(row=row, column=1, sticky="ew", pady=2)

    def _checkbox_group(self, parent, title, values, var_dict, columns=3):
        ttk.Label(parent, text=title, style="PanelMuted.TLabel").pack(anchor="w", pady=(4, 1))
        wrap = ttk.Frame(parent, style="Inner.TFrame")
        wrap.pack(fill="x")
        for i, v in enumerate(values):
            var = tk.BooleanVar(value=True)
            var_dict[v] = var
            cb = ttk.Checkbutton(wrap, text=v, variable=var)
            cb.grid(row=i // columns, column=i % columns, sticky="w", padx=(0, 8), pady=0)

    def _on_mode_change(self):
        if self.mode_var.get() == "manual":
            self.auto_frame.pack_forget()
            self.manual_frame.pack(fill="x")
        else:
            self.manual_frame.pack_forget()
            self.auto_frame.pack(fill="x")

    # ------------------------------------------------------------- right ui
    def _build_right_panel(self, parent):
        top = ttk.Frame(parent, style="Inner.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="Analysis Output", style="SectionHeading.TLabel").pack(anchor="w")
        self.output_subtitle = ttk.Label(top, text="Select a file and click Run Analysis.",
                                          style="PanelMuted.TLabel")
        self.output_subtitle.pack(anchor="w", pady=(2, 10))

        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)

        self.tab_isolation = ttk.Frame(self.notebook, style="Inner.TFrame", padding=12)
        self.tab_evidence = ttk.Frame(self.notebook, style="Inner.TFrame", padding=12)
        self.tab_hypothesis = ttk.Frame(self.notebook, style="Inner.TFrame", padding=12)
        self.tab_recovery = ttk.Frame(self.notebook, style="Inner.TFrame", padding=12)
        self.notebook.add(self.tab_isolation, text="Signal Isolation")
        self.notebook.add(self.tab_evidence, text="Evidence Extraction")
        self.notebook.add(self.tab_hypothesis, text="Hypothesis & Demodulation")
        self.notebook.add(self.tab_recovery, text="Recovery Information")

        self._build_isolation_tab()
        self._build_evidence_tab()
        self._build_hypothesis_tab()
        self._build_recovery_tab()

    def _section(self, parent, title, side=None, **pack_kwargs):
        """A titled block within a tab; returns the frame to fill."""
        cell = ttk.Frame(parent, style="Inner.TFrame")
        cell.pack(side=side, fill=pack_kwargs.pop("fill", "both"), expand=pack_kwargs.pop("expand", True),
                  **pack_kwargs)
        ttk.Label(cell, text=title, style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        return cell

    # Tab 1 -- Signal Isolation: which part of the recording and which
    # channel the rest of the pipeline analyses (core/isolation/), plus the
    # waveform/waterfall views of that isolated segment.
    def _build_isolation_tab(self):
        tab = self.tab_isolation
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        section = ttk.Frame(tab, style="Inner.TFrame")
        section.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(section, text="Signal Isolation", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        self.tree_isolation = self._make_kv_tree(section, height=8)
        self.tree_isolation.pack(fill="x")

        plot_frame = ttk.Frame(tab, style="Inner.TFrame")
        plot_frame.grid(row=1, column=0, sticky="nsew")
        self.plots_isolation = WaveformWaterfallPlots(plot_frame)

    # Tab 2 -- Evidence Extraction: feature extraction + parameter
    # estimation, plus the re-estimation search that refines them.
    def _build_evidence_tab(self):
        grid = self.tab_evidence
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_rowconfigure(0, weight=1)
        grid.grid_rowconfigure(1, weight=1)

        params = ttk.Frame(grid, style="Inner.TFrame")
        params.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(params, text="Estimated Parameters", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        self.tree_evidence = self._make_kv_tree(params, height=13)
        self.tree_evidence.pack(fill="both", expand=True)

        side = ttk.Frame(grid, style="Inner.TFrame")
        side.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Label(side, text="Spectral Peaks (Hz)", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        self.text_peaks = self._bits_box(side, "", height=3)
        ttk.Label(side, text="Re-estimation Search", style="SectionHeading.TLabel").pack(anchor="w", pady=(10, 4))
        cols = ("profile", "rate", "offset", "lowpass", "score", "kept")
        headings = {"profile": "Profile", "rate": "Rate (Hz)", "offset": "Offset (Hz)",
                    "lowpass": "Low-pass", "score": "Score", "kept": "Kept?"}
        self.tree_search = ttk.Treeview(side, columns=cols, show="headings", height=6)
        for c in cols:
            self.tree_search.heading(c, text=headings[c])
            self.tree_search.column(c, width=70, anchor="center")
        self.tree_search.pack(fill="both", expand=True)

        spectrum = ttk.Frame(grid, style="Inner.TFrame")
        spectrum.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        self.plot_spectrum = SpectrumPlot(spectrum)

    # Tab 3 -- Candidate generation, evidence scoring, best-supported
    # hypothesis selection, and (per candidate) demodulation.
    def _build_hypothesis_tab(self):
        tab = self.tab_hypothesis
        best = self._section(tab, "Best-Supported Hypothesis", side="top", fill="x", expand=False, pady=(0, 10))
        self.tree_best = self._make_kv_tree(best, height=7)
        self.tree_best.pack(fill="x")

        # Shrink "Best-Supported Hypothesis" above so this section -- and the
        # constellation inside it -- gets most of the tab's vertical room:
        # a full-width plot squeezed into a short leftover strip renders as a
        # small square (equal-aspect data can't use width it has no height
        # to match), which is the opposite of what a "make it bigger" ask
        # wants. A side-by-side split lets both the table and the
        # constellation claim the tab's full height, not just its width.
        hyp = self._section(tab, "Candidate Hypotheses (demodulated + scored)")
        hyp_body = ttk.Frame(hyp, style="Inner.TFrame")
        hyp_body.pack(fill="both", expand=True)
        hyp_body.grid_columnconfigure(0, weight=1)
        hyp_body.grid_columnconfigure(1, weight=0)
        hyp_body.grid_rowconfigure(1, weight=1)
        ttk.Button(hyp_body, text="Export CSV", style="Secondary.TButton",
                   command=self.export_hypotheses_csv).grid(row=0, column=0, sticky="e", pady=(0, 4))
        cols = ("score", "confidence", "constellation", "order", "timing", "evm")
        headings = {"score": "Score", "confidence": "Conf.", "constellation": "Constell.",
                    "order": "Order", "timing": "Timing", "evm": "EVM"}
        self.tree_hyp = ttk.Treeview(hyp_body, columns=cols, show="tree headings", height=5)
        self.tree_hyp.heading("#0", text="Modulation")
        self.tree_hyp.column("#0", width=90)
        for c in cols:
            self.tree_hyp.heading(c, text=headings[c])
            self.tree_hyp.column(c, width=65, anchor="center")
        self.tree_hyp.tag_configure("best", foreground=GOOD)
        self.tree_hyp.grid(row=1, column=0, sticky="nsew", padx=(0, 8))

        const_frame = ttk.Frame(hyp_body, style="Inner.TFrame", width=560)
        const_frame.grid(row=1, column=1, sticky="ns")
        const_frame.grid_propagate(False)
        self.plot_constellation = ConstellationPlot(const_frame)

    # Tab 4 -- de-interleaving, FEC decoding, bit correlation and
    # header/payload identification: the recovered information.
    def _build_recovery_tab(self):
        grid = self.tab_recovery
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_rowconfigure(0, weight=1)

        rec = ttk.Frame(grid, style="Inner.TFrame")
        rec.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(rec, text="De-interleaving + FEC", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        self.tree_recovery = self._make_kv_tree(rec, height=8)
        self.tree_recovery.pack(fill="x")
        self.text_recovered = self._bits_box(rec, "Recovered bitstream (first 512 bits)")

        res = ttk.Frame(grid, style="Inner.TFrame")
        res.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Button(res, text="Export report (.json)", style="Secondary.TButton",
                   command=self.export_report_json).pack(side="bottom", anchor="e", pady=(6, 0))
        ttk.Label(res, text="Header / Payload", style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        self.tree_results = self._make_kv_tree(res, height=8)
        self.tree_results.pack(fill="x")
        self.text_payload = self._bits_box(res, "Payload (hex, then first 512 bits)")

    def _bits_box(self, parent, label, height=4):
        if label:
            ttk.Label(parent, text=label, style="PanelMuted.TLabel").pack(anchor="w", pady=(8, 2))
        box = scrolledtext.ScrolledText(parent, height=height, wrap="char", font=("Consolas", 9),
                                         bg="#fafbfc", relief="solid", borderwidth=1)
        box.pack(fill="both", expand=True)
        box.configure(state="disabled")
        return box

    def _make_kv_tree(self, parent, height=6):
        # minwidth guarantees the Field column can't be squeezed below a
        # readable size by ttk's stretch-proportion layout in narrow
        # (two-column) tabs; value/source are fixed so Field gets any
        # leftover space.
        tree = ttk.Treeview(parent, columns=("value", "source"), show="tree headings", height=height)
        tree.heading("#0", text="Field")
        tree.heading("value", text="Value")
        tree.heading("source", text="Source")
        tree.column("#0", width=150, minwidth=150, anchor="w", stretch=True)
        tree.column("value", width=120, minwidth=120, anchor="w", stretch=True)
        tree.column("source", width=150, minwidth=150, anchor="w", stretch=True)
        return tree

    # ------------------------------------------------------------- actions
    def browse_file(self):
        path = filedialog.askopenfilename(
            title="Select a signal file",
            filetypes=[("Signal files", "*.iq *.wav"), ("IQ files", "*.iq"), ("WAV files", "*.wav")],
        )
        if not path:
            return
        self.file_path = path
        ext = os.path.splitext(path)[1].lower()
        fmt = "wav" if ext == ".wav" else "iq"
        self.format_var.set(fmt)

        try:
            meta = parse_metadata(path, sample_rate=None, dtype_name=self.dtype_var.get())
        except Exception as e:
            meta = {"error": str(e)}

        is_wav = fmt == "wav"
        self.samplerate_entry.configure(state="disabled" if is_wav else "normal")
        self.dtype_combo.configure(state="disabled" if is_wav else "readonly")
        if is_wav and "sample_rate" in meta:
            self.samplerate_var.set(str(meta["sample_rate"]))
        elif not is_wav:
            self.samplerate_var.set("")

        self.file_info_label.configure(text=self._format_file_info(path, fmt, meta))

        self.run_button.configure(state="normal")

    @staticmethod
    def _format_file_info(path, fmt, meta):
        parts = []
        if "sample_rate" in meta:
            parts.append(f"{meta['sample_rate']} Hz")
        if "channels" in meta:
            parts.append(f"{meta['channels']} ch")
        if "num_frames" in meta:
            parts.append(f"{meta['num_frames']} frames")
        if "num_samples" in meta:
            parts.append(f"{meta['num_samples']} samples")
        if "duration_sec" in meta:
            parts.append(f"{meta['duration_sec']:.2f} s")
        if "size_bytes" in meta:
            parts.append(f"{meta['size_bytes'] / 1024:.1f} KB")
        if "error" in meta:
            parts.append(f"error: {meta['error']}")
        return f"{os.path.basename(path)}  ({fmt.upper()})\n" + "  |  ".join(parts)

    def _collect_config(self, raw):
        mode = self.mode_var.get()
        if mode == "manual":
            manual_mod = self.manual_mod_var.get() or None
            symrate_text = self.manual_symrate_var.get().strip()
            manual_symrate = float(symrate_text) if symrate_text else None
            manual_deint = self.manual_deint_var.get()
            manual_deint = None if manual_deint in ("", "none") else manual_deint
            manual_fec = self.manual_fec_var.get()
            manual_fec = None if manual_fec in ("", "none") else manual_fec
            modulations, deint_types, fec_types = None, None, None
            deint_enabled = fec_enabled = True
        else:
            manual_mod = manual_symrate = manual_deint = manual_fec = None
            modulations = [name for name, var in self.mod_vars.items() if var.get()]
            deint_types = [name for name, var in self.deint_vars.items() if var.get()]
            fec_types = [name for name, var in self.fec_vars.items() if var.get()]
            deint_enabled = len(deint_types) > 0
            fec_enabled = len(fec_types) > 0

        return PipelineConfig.from_dict({
            "analysis": {"mode": mode},
            "modulations": modulations or ["BPSK", "QPSK", "16-QAM", "2-FSK", "4-FSK"],
            "deinterleaving": {"enabled": deint_enabled,
                                "types": deint_types or ["block", "convolutional", "diagonal", "pseudo_random"]},
            "fec": {"enabled": fec_enabled,
                    "types": fec_types or ["convolutional_viterbi", "reed_solomon", "concatenated", "ldpc"]},
            "manual": {"modulation": manual_mod, "symbol_rate": manual_symrate,
                       "deinterleave": manual_deint, "fec": manual_fec},
        })

    def run_analysis(self):
        if not self.file_path:
            return
        fmt = self.format_var.get()
        try:
            center_freq = float(self.centerfreq_var.get() or 0)
        except ValueError:
            messagebox.showerror("Invalid input", "Center frequency must be a number.")
            return

        try:
            if fmt == "iq":
                sr_text = self.samplerate_var.get().strip()
                if not sr_text:
                    messagebox.showwarning("Sample rate required", "Sample rate is required for .iq files.")
                    return
                sample_rate = float(sr_text)
                raw = read_iq(self.file_path, sample_rate=sample_rate, center_frequency=center_freq,
                              dtype_name=self.dtype_var.get())
            else:
                raw = read_wav(self.file_path, center_frequency=center_freq)
        except Exception as e:
            messagebox.showerror("Failed to load file", str(e))
            return

        try:
            config = self._collect_config(raw)
        except ValueError as e:
            messagebox.showerror("Invalid configuration", str(e))
            return

        self.run_button.configure(state="disabled")
        self.progress_var.set(0)
        self.status_label.configure(text="Starting...")
        self.output_subtitle.configure(text="Running...", foreground=MUTED)

        thread = threading.Thread(target=self._worker, args=(raw, config), daemon=True)
        thread.start()

    def _worker(self, raw, config):
        try:
            def progress_cb(stage, percent, message):
                self.msg_queue.put(("progress", stage, percent, message))
            result = run_pipeline(raw, config, progress_cb=progress_cb)
            self.msg_queue.put(("done", result))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    def _poll_queue(self):
        try:
            while True:
                item = self.msg_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, stage, percent, message = item
                    self.progress_var.set(percent)
                    self.status_label.configure(text=f"{stage}: {message}")
                elif kind == "done":
                    self._on_result(item[1])
                elif kind == "error":
                    messagebox.showerror("Analysis failed", item[1])
                    self.status_label.configure(text="Error")
                    self.run_button.configure(state="normal")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------- results
    def _on_result(self, result):
        self.result = result
        self.run_button.configure(state="normal")
        self.status_label.configure(text="Complete")
        self._clear_results()

        verdict = result.verdict
        self.output_subtitle.configure(
            text=f"{VERDICT_TITLES.get(verdict, verdict)} - {result.verdict_reason}",
            foreground=VERDICT_COLORS.get(verdict, TEXT))

        self.plots_isolation.update(result.visualizations)
        self.plot_spectrum.update(result.visualizations)
        self.plot_constellation.update(result.visualizations)
        prov = result.provenance
        est, feat, iso = result.estimate, result.features, result.isolation

        # ---- Tab 1: Signal Isolation ----
        duration = (iso.segment_end - iso.segment_start) / iso.sample_rate if iso.sample_rate else 0.0
        isolated_pct = (100.0 * (iso.segment_end - iso.segment_start) / iso.total_samples
                        if iso.total_samples else 0.0)
        profiles_tried = {t["profile"] for t in result.reestimation}
        profile_source = "re-estimation search" if len(profiles_tried) > 1 else "default"
        self._fill_kv(self.tree_isolation, {
            "Active segment (samples)": (f"{iso.segment_start}:{iso.segment_end}", "isolation (energy segmentation)"),
            "Segment duration (s)": (fmt_num(duration), "isolation"),
            "Total samples": (iso.total_samples, "loaded"),
            "Isolated fraction": (f"{isolated_pct:.1f}%", "isolation"),
            "Active channel offset (Hz)": (fmt_num(iso.channel_offset_hz), "isolation (band detection)"),
            "Active channel bandwidth (Hz)": (fmt_num(iso.channel_bandwidth_hz), "isolation (band detection)"),
            "Preprocessing profile used": (iso.preprocessing_profile, profile_source),
        })

        # ---- Tab 2: Evidence Extraction ----
        self._fill_kv(self.tree_evidence, {
            "Sample rate (Hz)": (fmt_num(est.sample_rate), prov.get("sample_rate")),
            "Center freq (Hz)": (fmt_num(est.carrier_frequency - est.carrier_offset), prov.get("center_frequency")),
            "Carrier offset (Hz)": (fmt_num(est.carrier_offset), prov.get("carrier_offset")),
            "Symbol rate (Hz)": (fmt_num(est.symbol_rate), prov.get("symbol_rate")),
            "Timing fit": (fmt_num(est.timing_fit), "estimated"),
            "Bandwidth (Hz)": (fmt_num(est.bandwidth), prov.get("bandwidth")),
            "Samples per symbol": (est.samples_per_symbol or "-", "sample rate / symbol rate"),
            "SNR (dB)": (fmt_num(est.snr_db), "estimated (M2M4)"),
            "PAPR (dB)": (fmt_num(feat.papr_db), "measured"),
            "Spectral flatness": (fmt_num(feat.spectral_flatness), "measured"),
            "Kurtosis": (fmt_num(feat.kurtosis), "measured"),
            "Skewness": (fmt_num(feat.skewness), "measured"),
        })
        self._set_text(self.text_peaks, ", ".join(fmt_num(p) for p in feat.spectral_peaks) or "(none)")
        for t in result.reestimation:
            tags = ("best",) if t["accepted"] and t is result.reestimation[-1] else ()
            self.tree_search.insert("", "end", tags=tags, values=(
                t["profile"], fmt_num(t["symbol_rate"]), fmt_num(t["carrier_offset_hz"]),
                fmt_num(t["lowpass_hz"]) if t["lowpass_hz"] else "-", fmt_num(t["score"]),
                "yes" if t["accepted"] else "no",
            ))
        self.tree_search.tag_configure("best", foreground=GOOD)

        # ---- Tab 3: Hypothesis selection + demodulation ----
        best = result.best_hypothesis
        order = best.evidence.get("expected_order") if best else None
        data_rate = est.symbol_rate * np.log2(order) if order and order > 1 else None
        self._fill_kv(self.tree_best, {
            "Modulation": (best.modulation if best else "-", prov.get("modulation")),
            "Score": (fmt_num(best.score) if best else "-", "evidence scoring"),
            "Confidence": (f"{best.confidence}%" if best else "-", "relative to runner-up"),
            "Verdict": (VERDICT_TITLES.get(result.verdict, result.verdict), "verdict rule"),
            "Demodulated bits": (len(best.demodulation_result) if best and best.demodulation_result is not None
                                  else "-", "demodulation"),
            "EVM": (fmt_num(best.evidence.get("evm")) if best else "-", "demodulation"),
            "Data rate (bps)": (fmt_num(data_rate) if data_rate else "-", "symbol rate x bits/symbol"),
        })
        for i, h in enumerate(result.hypotheses):
            tags = ("best",) if i == 0 else ()
            m = h.metrics
            self.tree_hyp.insert("", "end", text=h.modulation, tags=tags, values=(
                fmt_num(h.score), f"{h.confidence}%", fmt_num(m.get("constellation_fit")),
                fmt_num(m.get("order_consistency")), fmt_num(m.get("timing_fit")), fmt_num(h.evidence.get("evm")),
            ))

        # ---- Tab 4: Recovery Information ----
        rec = result.recovered
        if rec:
            deint_params = rec.diagnostics.get("deinterleave_params") or {}
            params_str = ", ".join(f"{k}={v}" for k, v in deint_params.items()) or "-"
            self._fill_kv(self.tree_recovery, {
                "De-interleaving": (rec.deinterleave_method, prov.get("de-interleaving")),
                "De-interleave params": (params_str, "used during recovery search"),
                "FEC": (rec.fec_method, prov.get("fec")),
                "FEC verified": ("-" if rec.fec_success is None else str(rec.fec_success), "decoded"),
                "FEC quality": (rec.diagnostics.get("fec_quality") or "-", "decoder diagnostics"),
                "FEC input": ("soft (per-bit LLR)" if rec.llr_used else "hard bits",
                              "demodulation" if rec.llr_used else "no soft info for this method"),
                "Evidence": ("supported" if rec.confirmed else "none", "correlation / FEC"),
                "Recovered bit count": (len(rec.bits), "de-interleaving + FEC output"),
            })
            self._set_text(self.text_recovered, self._bits_preview(rec.bits))
        else:
            self._fill_kv(self.tree_recovery, {"Recovery": ("not run", "insufficient evidence for a modulation")})
            self._set_text(self.text_recovered, "(recovery not run: insufficient evidence for a modulation)")

        bs = result.bitstream
        if bs:
            region = "-" if bs.payload_start is None else f"{bs.payload_start}..{bs.payload_end}"
            payload_len = len(bs.payload_bits) if bs.payload_bits is not None else 0
            self._fill_kv(self.tree_results, {
                "Header pattern": (bs.header_pattern or "not found", prov.get("header")),
                "Header offset (bits)": (bs.header_offset if bs.header_offset is not None else "-", "correlation"),
                "Pattern length": (bs.pattern_length or "-", "correlation"),
                "Polarity": (bs.polarity if bs.header_pattern else "-", "correlation"),
                "Similarity": (fmt_num(bs.hamming_similarity) if bs.header_pattern else "-", "1 - d_H/N"),
                "False-alarm p": (f"{bs.false_alarm_probability:.2g}", "binomial null"),
                "Payload region": (region, "after header"),
                "Payload length": (f"{payload_len} bits ({payload_len // 8} bytes)" if payload_len else "-",
                                    "after header"),
            })
            payload = bs.payload_bits
            if payload is not None and len(payload):
                self._set_text(self.text_payload,
                               "HEX  " + bits_to_hex(payload) + "\n\nBIN  " + self._bits_preview(payload))
            else:
                self._set_text(self.text_payload, "(no header found, so no payload region identified)")
        else:
            self._fill_kv(self.tree_results, {})
            self._set_text(self.text_payload, "")

    def _clear_results(self):
        for tree in (self.tree_isolation, self.tree_evidence, self.tree_search, self.tree_best,
                     self.tree_hyp, self.tree_recovery, self.tree_results):
            tree.delete(*tree.get_children())
        self._set_text(self.text_peaks, "")
        self._set_text(self.text_recovered, "")
        self._set_text(self.text_payload, "")

    def _fill_kv(self, tree, data: dict):
        tree.delete(*tree.get_children())
        for k, (value, source) in data.items():
            tree.insert("", "end", text=k, values=(value, source or ""))

    def _set_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _bits_preview(self, bits):
        if bits is None or len(bits) == 0:
            return "(none)"
        return "".join(str(int(b)) for b in bits[:512])

    # ------------------------------------------------------------- exports
    def export_hypotheses_csv(self):
        if not self.result or not self.result.hypotheses:
            messagebox.showinfo("Nothing to export", "Run an analysis first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Modulation", "Score", "Confidence", "Constellation fit", "Order consistency",
                             "Timing fit", "EVM"])
            for h in self.result.hypotheses:
                writer.writerow([h.modulation, h.score, h.confidence, h.metrics.get("constellation_fit"),
                                 h.metrics.get("order_consistency"), h.metrics.get("timing_fit"),
                                 h.evidence.get("evm")])
        messagebox.showinfo("Exported", f"Saved to {path}")

    def export_report_json(self):
        if not self.result:
            messagebox.showinfo("Nothing to export", "Run an analysis first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "w") as f:
            json.dump(to_jsonable(self.result), f, indent=2)
        messagebox.showinfo("Exported", f"Saved to {path}")


def enable_dpi_awareness():
    """Without this, Windows bitmap-scales the whole window on high-DPI
    displays, making text and plots look blurry."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main():
    enable_dpi_awareness()
    app = SignalAnalysisApp()
    app.mainloop()


if __name__ == "__main__":
    main()
