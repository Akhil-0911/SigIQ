"""Embedded matplotlib plots for the Visualization tab: waveform, spectrum,
waterfall and constellation, styled to match the app's light theme."""
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from gui.style import PANEL, BORDER, ACCENT, MUTED, TEXT


class AnalysisPlots:
    def __init__(self, parent):
        self.fig = Figure(figsize=(5, 4), dpi=100, facecolor=PANEL)
        gs = self.fig.add_gridspec(3, 2, height_ratios=[0.85, 0.85, 1.4], hspace=0.7, wspace=0.3,
                                    left=0.07, right=0.98, top=0.96, bottom=0.07)

        self.ax_waveform = self.fig.add_subplot(gs[0, :])
        self.ax_spectrum = self.fig.add_subplot(gs[1, :])
        self.ax_waterfall = self.fig.add_subplot(gs[2, 0])
        self.ax_constellation = self.fig.add_subplot(gs[2, 1])

        for ax in (self.ax_waveform, self.ax_spectrum, self.ax_waterfall, self.ax_constellation):
            self._style_axes(ax)

        self.ax_waveform.set_title("Waveform (magnitude)", fontsize=9, color=TEXT, loc="left")
        self.ax_spectrum.set_title("Spectrum (PSD)", fontsize=9, color=TEXT, loc="left")
        self.ax_waterfall.set_title("Waterfall", fontsize=9, color=TEXT, loc="left")
        self.ax_constellation.set_title("Constellation", fontsize=9, color=TEXT, loc="left")

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        widget = self.canvas.get_tk_widget()
        widget.configure(bg=PANEL, highlightthickness=0)
        widget.pack(fill="both", expand=True, padx=10, pady=10)

        # matplotlib's Tk backend rescales the figure DPI (device pixel ratio)
        # only after the window is mapped, without re-fitting the figure to
        # the widget -- on a scaled Windows display that leaves the rendered
        # image larger than its widget, clipping the right/bottom edges. These
        # handlers run after matplotlib's own and re-sync figure size to the
        # widget using whatever DPI is current.
        widget.bind("<Configure>", lambda e: self._fit(e.width, e.height), add="+")
        widget.bind("<Map>", lambda e: self._fit(widget.winfo_width(), widget.winfo_height()), add="+")
        self.canvas.draw()

    def _fit(self, width_px, height_px):
        if width_px < 20 or height_px < 20:
            return
        dpi = self.fig.dpi
        self.fig.set_size_inches(width_px / dpi, height_px / dpi, forward=False)
        self.canvas.draw_idle()

    def _style_axes(self, ax):
        ax.set_facecolor("#fafbfc")
        for spine in ax.spines.values():
            spine.set_color(BORDER)
        ax.tick_params(colors=MUTED, labelsize=7)
        ax.grid(True, color=BORDER, linewidth=0.5, alpha=0.6)

    def clear(self):
        for ax in (self.ax_waveform, self.ax_spectrum, self.ax_waterfall, self.ax_constellation):
            ax.cla()
            self._style_axes(ax)
        self.canvas.draw_idle()

    def update(self, viz: dict):
        self.clear()

        waveform = viz.get("waveform") or []
        if waveform:
            mag = [np.hypot(p[0], p[1]) for p in waveform]
            self.ax_waveform.plot(mag, color=ACCENT, linewidth=0.8)
        self.ax_waveform.set_title("Waveform (magnitude)", fontsize=9, color=TEXT, loc="left")

        freqs = viz.get("spectrum_freqs") or []
        psd_db = viz.get("spectrum_db") or []
        if freqs and psd_db:
            self.ax_spectrum.plot(freqs, psd_db, color="#5b8cff", linewidth=0.9)
            self.ax_spectrum.set_xlabel("Hz", fontsize=7, color=MUTED)
            self.ax_spectrum.set_ylabel("dB", fontsize=7, color=MUTED)
        self.ax_spectrum.set_title("Spectrum (PSD)", fontsize=9, color=TEXT, loc="left")

        wf_freqs = viz.get("waterfall_freqs") or []
        wf_times = viz.get("waterfall_times") or []
        wf_db = viz.get("waterfall_db") or []
        if wf_freqs and wf_times and wf_db:
            arr = np.array(wf_db)  # shape (n_times, n_freqs)
            self.ax_waterfall.imshow(
                arr.T, aspect="auto", origin="lower", cmap="inferno",
                extent=[wf_times[0], wf_times[-1], wf_freqs[0], wf_freqs[-1]],
            )
            self.ax_waterfall.set_xlabel("s", fontsize=7, color=MUTED)
            self.ax_waterfall.set_ylabel("Hz", fontsize=7, color=MUTED)
        self.ax_waterfall.set_title("Waterfall", fontsize=9, color=TEXT, loc="left")

        constellation = viz.get("constellation") or []
        if constellation:
            re = [p[0] for p in constellation]
            im = [p[1] for p in constellation]
            self.ax_constellation.scatter(re, im, s=6, color=ACCENT, alpha=0.7)
            self.ax_constellation.axhline(0, color=BORDER, linewidth=0.6)
            self.ax_constellation.axvline(0, color=BORDER, linewidth=0.6)
            self.ax_constellation.set_aspect("equal", adjustable="box")
        self.ax_constellation.set_title("Constellation", fontsize=9, color=TEXT, loc="left")

        self.canvas.draw_idle()
