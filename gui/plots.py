"""Embedded matplotlib plots for the pipeline-stage tabs: waveform + waterfall
(Signal Isolation), spectrum (Evidence Extraction), constellation (Hypothesis
& Demodulation) -- styled to match the app's light theme."""
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from gui.style import PANEL, BORDER, ACCENT, MUTED, TEXT


class _PlotPanel:
    """Common Figure/canvas setup and the high-DPI resize fix, shared by
    every per-tab plot widget below."""

    def __init__(self, parent, figsize):
        self.fig = Figure(figsize=figsize, dpi=100, facecolor=PANEL)
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        widget = self.canvas.get_tk_widget()
        widget.configure(bg=PANEL, highlightthickness=0)
        widget.pack(fill="both", expand=True)

        # matplotlib's Tk backend rescales the figure DPI (device pixel ratio)
        # only after the window is mapped, without re-fitting the figure to
        # the widget -- on a scaled Windows display that leaves the rendered
        # image larger than its widget, clipping the right/bottom edges. These
        # handlers run after matplotlib's own and re-sync figure size to the
        # widget using whatever DPI is current.
        widget.bind("<Configure>", lambda e: self._fit(e.width, e.height), add="+")
        widget.bind("<Map>", lambda e: self._fit(widget.winfo_width(), widget.winfo_height()), add="+")

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


class WaveformWaterfallPlots(_PlotPanel):
    """Signal Isolation tab: time-domain envelope and time/frequency view of
    the isolated segment -- how the analyst can see what was isolated."""

    def __init__(self, parent):
        super().__init__(parent, figsize=(5, 4))
        gs = self.fig.add_gridspec(2, 1, height_ratios=[1, 1.3], hspace=0.55,
                                    left=0.09, right=0.98, top=0.93, bottom=0.1)
        self.ax_waveform = self.fig.add_subplot(gs[0])
        self.ax_waterfall = self.fig.add_subplot(gs[1])
        for ax in (self.ax_waveform, self.ax_waterfall):
            self._style_axes(ax)
        self.ax_waveform.set_title("Waveform (magnitude)", fontsize=9, color=TEXT, loc="left")
        self.ax_waterfall.set_title("Waterfall", fontsize=9, color=TEXT, loc="left")
        self.canvas.draw()

    def clear(self):
        for ax in (self.ax_waveform, self.ax_waterfall):
            ax.cla()
            self._style_axes(ax)

    def update(self, viz: dict):
        self.clear()

        waveform = viz.get("waveform") or []
        if waveform:
            mag = [np.hypot(p[0], p[1]) for p in waveform]
            self.ax_waveform.plot(mag, color=ACCENT, linewidth=0.8)
        self.ax_waveform.set_title("Waveform (magnitude)", fontsize=9, color=TEXT, loc="left")

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

        self.canvas.draw_idle()


class SpectrumPlot(_PlotPanel):
    """Evidence Extraction tab: the PSD that spectral feature extraction and
    parameter estimation (bandwidth, center frequency) are measured from."""

    def __init__(self, parent):
        super().__init__(parent, figsize=(5, 2.2))
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(left=0.09, right=0.98, top=0.85, bottom=0.22)
        self._style_axes(self.ax)
        self.ax.set_title("Spectrum (PSD)", fontsize=9, color=TEXT, loc="left")
        self.canvas.draw()

    def update(self, viz: dict):
        self.ax.cla()
        self._style_axes(self.ax)
        freqs = viz.get("spectrum_freqs") or []
        psd_db = viz.get("spectrum_db") or []
        if freqs and psd_db:
            self.ax.plot(freqs, psd_db, color="#5b8cff", linewidth=0.9)
            self.ax.set_xlabel("Hz", fontsize=7, color=MUTED)
            self.ax.set_ylabel("dB", fontsize=7, color=MUTED)
        self.ax.set_title("Spectrum (PSD)", fontsize=9, color=TEXT, loc="left")
        self.canvas.draw_idle()


class ConstellationPlot(_PlotPanel):
    """Hypothesis & Demodulation tab: the best-supported hypothesis's own
    demodulated symbols."""

    def __init__(self, parent):
        super().__init__(parent, figsize=(4.4, 4.4))
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(left=0.14, right=0.97, top=0.93, bottom=0.09)
        self._style_axes(self.ax)
        self.ax.set_title("Constellation", fontsize=9, color=TEXT, loc="left")
        self.canvas.draw()

    def update(self, viz: dict):
        self.ax.cla()
        self._style_axes(self.ax)
        constellation = viz.get("constellation") or []
        if constellation:
            re = [p[0] for p in constellation]
            im = [p[1] for p in constellation]
            # Small, low-alpha markers so overlapping symbols build up a
            # visible density gradient (cluster shape/spread) instead of
            # rendering as one flat, solid-colored blob.
            self.ax.scatter(re, im, s=4, color=ACCENT, alpha=0.35, linewidths=0)
            self.ax.axhline(0, color=BORDER, linewidth=0.6)
            self.ax.axvline(0, color=BORDER, linewidth=0.6)
            # Zoom to the actual symbol spread (plus a margin) instead of a
            # fixed range, so a tight cluster (e.g. high-SNR BPSK sitting near
            # +-1 with almost no spread) fills the plot instead of looking
            # like a speck inside empty space. Symmetric limits on both axes
            # before locking the aspect keep it equal without matplotlib
            # having to shrink the plot's box to force a 1:1 ratio.
            half_span = max(max(abs(min(re)), abs(max(re)), abs(min(im)), abs(max(im))), 1e-3) * 1.2
            self.ax.set_xlim(-half_span, half_span)
            self.ax.set_ylim(-half_span, half_span)
            self.ax.set_aspect("equal", adjustable="box")
        self.ax.set_title("Constellation", fontsize=9, color=TEXT, loc="left")
        self.canvas.draw_idle()
