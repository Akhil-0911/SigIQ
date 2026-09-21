"""Signal Analysis Workstation -- native Tkinter desktop app.

Single window: left panel for file input + configuration, right panel for
tabbed analysis output (visualization, parameters, hypotheses, recovery,
results). Calls straight into core/.
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

from gui.style import apply_theme, PANEL, BG, MUTED, TEXT, GOOD, BAD, ACCENT
from gui.plots import AnalysisPlots

IQ_DTYPES = ["int8", "uint8", "int16", "float32", "float64"]


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

        self.tab_viz = ttk.Frame(self.notebook, style="Inner.TFrame")
        self.tab_analysis = ttk.Frame(self.notebook, style="Inner.TFrame", padding=12)
        self.notebook.add(self.tab_viz, text="Visualization")
        self.notebook.add(self.tab_analysis, text="Analysis")

        self.plots = AnalysisPlots(self.tab_viz)
        self._build_analysis_tab()

    def _section(self, parent, row, column, title):
        """A titled cell of the Analysis grid; returns the frame to fill."""
        cell = ttk.Frame(parent, style="Inner.TFrame")
        cell.grid(row=row, column=column, sticky="nsew",
                  padx=(0 if column == 0 else 8, 8 if column == 0 else 0),
                  pady=(0 if row == 0 else 8, 8 if row == 0 else 0))
        ttk.Label(cell, text=title, style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        return cell

    def _build_analysis_tab(self):
        grid = self.tab_analysis
        for i in (0, 1):
            grid.grid_columnconfigure(i, weight=1, uniform="col")
            grid.grid_rowconfigure(i, weight=1, uniform="row")

        params = self._section(grid, 0, 0, "Parameters")
        self.tree_params = self._make_kv_tree(params, height=9)
        self.tree_params.pack(fill="both", expand=True)

        hyp = self._section(grid, 0, 1, "Hypotheses")
        ttk.Button(hyp, text="Export CSV", style="Secondary.TButton",
                   command=self.export_hypotheses_csv).pack(anchor="e", pady=(0, 4))
        cols = ("score", "confidence", "evm", "cluster")
        self.tree_hyp = ttk.Treeview(hyp, columns=cols, show="tree headings", height=6)
        self.tree_hyp.heading("#0", text="Modulation")
        self.tree_hyp.heading("score", text="Score")
        self.tree_hyp.heading("confidence", text="Confidence")
        self.tree_hyp.heading("evm", text="EVM")
        self.tree_hyp.heading("cluster", text="Cluster")
        self.tree_hyp.column("#0", width=90)
        for c in cols:
            self.tree_hyp.column(c, width=70, anchor="center")
        self.tree_hyp.tag_configure("best", foreground=GOOD)
        self.tree_hyp.pack(fill="both", expand=True)

        rec = self._section(grid, 1, 0, "Recovery")
        self.tree_recovery = self._make_kv_tree(rec, height=4)
        self.tree_recovery.pack(fill="x")
        self.text_recovered = self._bits_box(rec, "Recovered bitstream (first 512 bits)")

        res = self._section(grid, 1, 1, "Results")
        self.tree_results = self._make_kv_tree(res, height=3)
        self.tree_results.pack(fill="x")
        self.text_payload = self._bits_box(res, "Payload bits (first 512 bits)")
        ttk.Button(res, text="Export report (.json)", style="Secondary.TButton",
                   command=self.export_report_json).pack(anchor="e", pady=(6, 0))

    def _bits_box(self, parent, label):
        ttk.Label(parent, text=label, style="PanelMuted.TLabel").pack(anchor="w", pady=(8, 2))
        box = scrolledtext.ScrolledText(parent, height=4, wrap="char", font=("Consolas", 9),
                                         bg="#fafbfc", relief="solid", borderwidth=1)
        box.pack(fill="both", expand=True)
        box.configure(state="disabled")
        return box

    def _make_kv_tree(self, parent, height=6):
        tree = ttk.Treeview(parent, columns=("value",), show="tree headings", height=height)
        tree.heading("#0", text="Field")
        tree.heading("value", text="Value")
        tree.column("#0", width=170, anchor="w")
        tree.column("value", width=150, anchor="w")
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
            "input": {"format": raw.source_format, "sample_rate": raw.sample_rate,
                      "center_frequency": raw.center_frequency},
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
        self.output_subtitle.configure(text="Running...")

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
        self.output_subtitle.configure(text=f"Analysis complete — best hypothesis: "
                                             f"{result.best_hypothesis.modulation if result.best_hypothesis else 'none'}")

        self.plots.update(result.visualizations)

        self._fill_kv(self.tree_params, {
            "Sample rate (Hz)": fmt_num(result.estimate.sample_rate),
            "Symbol rate (Hz)": fmt_num(result.estimate.symbol_rate),
            "Carrier frequency (Hz)": fmt_num(result.estimate.carrier_frequency),
            "Bandwidth (Hz)": fmt_num(result.estimate.bandwidth),
            "SNR (dB)": fmt_num(result.estimate.snr_db),
            "PAPR (dB)": fmt_num(result.features.papr_db),
            "Spectral flatness": fmt_num(result.features.spectral_flatness),
            "Kurtosis": fmt_num(result.features.kurtosis),
            "Skewness": fmt_num(result.features.skewness),
        })

        self.tree_hyp.delete(*self.tree_hyp.get_children())
        for i, h in enumerate(result.hypotheses):
            tags = ("best",) if i == 0 else ()
            self.tree_hyp.insert("", "end", text=h.modulation, tags=tags, values=(
                fmt_num(h.score), f"{h.confidence}%", fmt_num(h.evidence.get("evm")),
                h.evidence.get("matched_cluster_order"),
            ))

        if result.recovered:
            self._fill_kv(self.tree_recovery, {
                "Modulation": result.recovered.modulation,
                "De-interleave method": result.recovered.deinterleave_method,
                "FEC method": result.recovered.fec_method,
                "FEC success": str(result.recovered.fec_success),
            })
            self._set_text(self.text_recovered, self._bits_preview(result.recovered.bits))

        if result.bitstream:
            self._fill_kv(self.tree_results, {
                "Header pattern": result.bitstream.header_pattern or "not found",
                "Header offset (bits)": result.bitstream.header_offset,
                "Correlation peak": fmt_num(result.bitstream.correlation_peak),
            })
            self._set_text(self.text_payload, self._bits_preview(result.bitstream.payload_bits))

    def _fill_kv(self, tree, data: dict):
        tree.delete(*tree.get_children())
        for k, v in data.items():
            tree.insert("", "end", text=k, values=(v,))

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
            writer.writerow(["Modulation", "Score", "Confidence", "EVM", "Cluster order"])
            for h in self.result.hypotheses:
                writer.writerow([h.modulation, h.score, h.confidence, h.evidence.get("evm"),
                                  h.evidence.get("matched_cluster_order")])
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
