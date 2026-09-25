import numpy as np


LOCAL_FLOOR_BINS = 32  # neighbourhood (bins each side) that defines the local noise floor of a cyclic line


def _dominant_cyclic_peak(feature_signal: np.ndarray, sample_rate: float,
                           lo_frac: float = 0.001, hi_frac: float = 0.49) -> tuple:
    """FFT the given real-valued feature signal, find its strongest spectral
    line (excluding DC and the extreme high end), refine the bin with a
    parabolic interpolation, and report the line's prominence (peak / local
    median) so callers can judge how trustworthy the estimate is."""
    feature_signal = feature_signal - np.mean(feature_signal)
    spectrum = np.abs(np.fft.rfft(feature_signal))
    freqs = np.fft.rfftfreq(len(feature_signal), d=1 / sample_rate)

    n = len(freqs)
    lo = max(1, int(n * lo_frac))
    hi = int(n * hi_frac)
    if hi <= lo + 1:
        return 0.0, 0.0

    window = spectrum[lo:hi]
    local_peak = int(np.argmax(window))
    peak_idx = lo + local_peak
    peak_val = spectrum[peak_idx]

    # parabolic interpolation across the peak bin's neighbours for sub-bin resolution
    if 0 < peak_idx < len(spectrum) - 1:
        left, center, right = spectrum[peak_idx - 1], spectrum[peak_idx], spectrum[peak_idx + 1]
        denom = (left - 2 * center + right)
        delta = 0.5 * (left - right) / denom if denom != 0 else 0.0
        delta = float(np.clip(delta, -1.0, 1.0))
    else:
        delta = 0.0

    bin_width = freqs[1] - freqs[0] if len(freqs) > 1 else 0.0
    refined_freq = freqs[peak_idx] + delta * bin_width

    median = np.median(window) + 1e-12
    prominence = float(peak_val / median)
    return float(refined_freq), prominence


def _cyclic_feature_signals(samples: np.ndarray) -> list:
    """The three real-valued features whose spectra carry the symbol clock:
    |x|^2, |diff(x)|^2, and diff(instantaneous frequency)^2."""
    mag_sq = np.abs(samples) ** 2

    diff = np.abs(np.diff(samples)) ** 2
    diff = np.concatenate([diff, diff[-1:]]) if len(diff) else np.zeros(1)

    if len(samples) > 2:
        phase = np.unwrap(np.angle(samples))
        inst_freq = np.diff(phase)
        freq_transition = np.diff(inst_freq) ** 2
        freq_transition = np.concatenate([freq_transition, freq_transition[-2:]]) if len(freq_transition) else np.zeros(1)
    else:
        freq_transition = np.zeros(1)
    return [mag_sq, diff, freq_transition]


def line_prominence_at(samples: np.ndarray, sample_rate: float, rate_hz: float) -> float:
    """Prominence (line magnitude / median magnitude) of the strongest of the
    three cyclic features at `rate_hz` (best of the +/-1 nearest FFT bins).
    Unlike the free peak search, this asks whether the specific tested symbol
    rate is supported, so a sub-harmonic of the true clock scores low."""
    best = 0.0
    for feat in _cyclic_feature_signals(samples):
        if len(feat) < 8:
            continue
        feat = feat - np.mean(feat)
        spectrum = np.abs(np.fft.rfft(feat))
        n = len(spectrum)
        bin_hz = sample_rate / len(feat)
        k = int(round(rate_hz / bin_hz))
        lo, hi = max(1, k - 1), min(n - 1, k + 2)
        if hi <= lo:
            continue
        # Compare with the LOCAL floor (neighbouring bins, line excluded), not
        # the global median: a filtered/coloured noise spectrum has a tiny
        # global median, which would make any in-band bin look like a line.
        w = LOCAL_FLOOR_BINS
        neighbours = np.concatenate([spectrum[max(1, k - w):max(1, k - 1)], spectrum[k + 2:min(n, k + w + 2)]])
        if len(neighbours) < 8:
            continue
        best = max(best, float(np.max(spectrum[lo:hi]) / (np.median(neighbours) + 1e-12)))
    return best


def symbol_rate_and_prominence(samples: np.ndarray, sample_rate: float) -> tuple:
    """Estimate symbol rate and the prominence (peak / median) of its line by combining three cyclostationary features and
    keeping whichever shows the more confident (higher-prominence) spectral
    line at the symbol clock:

    1. |signal|^2 envelope -- carries a symbol-rate line for modulations
       whose amplitude varies symbol-to-symbol (QAM, ASK/OOK). It is FLAT
       (no symbol-rate content at all) for constant-envelope modulations
       like unshaped BPSK/QPSK/FSK.
    2. |diff(signal)|^2 transition energy -- for amplitude/phase modulations,
       a symbol boundary is where the complex sample can jump, so transitions
       form a periodic point process locked to the symbol clock. This is
       BLIND to FSK, though: |diff(signal)| for a constant-modulus FSK
       signal tracks |instantaneous frequency|, and symmetric-deviation FSK
       (e.g. +dev/-dev tones) has the same |frequency| on every tone, so this
       feature stays flat across symbol boundaries even though the tone
       actually changed.
    3. diff(instantaneous frequency)^2 -- FSK-specific: the SIGNED
       instantaneous frequency (unlike its magnitude) genuinely jumps at
       every tone change, so its own transition energy has a strong,
       unambiguous line at the symbol clock for FSK regardless of deviation
       symmetry. For PSK/QAM this feature is dominated by phase noise rather
       than a clean symbol-rate line, so it naturally loses out to features
       1/2 there via the prominence comparison.
    """
    features = _cyclic_feature_signals(samples)
    candidates = [_dominant_cyclic_peak(f, sample_rate) if len(f) > 1 else (0.0, 0.0) for f in features]
    best_freq, best_prominence = max(candidates, key=lambda c: c[1])
    return best_freq, best_prominence, len(samples)


def timing_fit_from_prominence(prominence: float, n_samples: int) -> float:
    """Map a cyclic-line prominence (peak / median of the FFT magnitude) to
    [0, 1] by comparing it with what noise alone produces: for Rayleigh-
    distributed bin magnitudes the expected max/median ratio over n bins is
    sqrt(ln(n) / ln(2)). fit = 1 - noise_ratio / prominence, clipped."""
    n_bins = max(n_samples // 2, 2)
    noise_ratio = float(np.sqrt(np.log(n_bins) / np.log(2.0)))
    if prominence <= 0:
        return 0.0
    return float(np.clip(1.0 - noise_ratio / prominence, 0.0, 1.0))
