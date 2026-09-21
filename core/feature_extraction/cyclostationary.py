import numpy as np


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


def symbol_rate_from_cyclic_spectrum(samples: np.ndarray, sample_rate: float) -> float:
    """Estimate symbol rate by combining three cyclostationary features and
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
    mag_sq = np.abs(samples) ** 2
    f_envelope, prom_envelope = _dominant_cyclic_peak(mag_sq, sample_rate)

    diff = np.abs(np.diff(samples)) ** 2
    if len(diff) == 0:
        f_transition, prom_transition = 0.0, 0.0
    else:
        diff = np.concatenate([diff, diff[-1:]])
        f_transition, prom_transition = _dominant_cyclic_peak(diff, sample_rate)

    if len(samples) > 2:
        phase = np.unwrap(np.angle(samples))
        inst_freq = np.diff(phase) * sample_rate / (2 * np.pi)
        freq_transition = np.diff(inst_freq) ** 2
        freq_transition = np.concatenate([freq_transition, freq_transition[-2:]]) if len(freq_transition) else np.array([0.0])
        f_freq_transition, prom_freq_transition = _dominant_cyclic_peak(freq_transition, sample_rate)
    else:
        f_freq_transition, prom_freq_transition = 0.0, 0.0

    candidates = [
        (f_envelope, prom_envelope),
        (f_transition, prom_transition),
        (f_freq_transition, prom_freq_transition),
    ]
    best_freq, _ = max(candidates, key=lambda c: c[1])
    return best_freq
