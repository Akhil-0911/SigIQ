import numpy as np
from scipy.signal import find_peaks
from scipy.stats import chi2

from sigiq.core.isolation.spectrum import power_spectrum
from sigiq.core.demodulation.synchronization import symbol_decimate
from sigiq.core.demodulation.soft_bits import bit_labels_for, compute_llr

# tone peaks must lie within this many dB of the strongest one (data-dependent
# imbalance is allowed, a -13 dB sinc sidelobe is not)
TONE_PEAK_WINDOW_DB = 6.0
# a tone peak must exceed what the largest of the PSD's bins would reach by
# chance in white noise, at this per-analysis false-alarm level
PEAK_FALSE_ALARM = 0.01
NOISE_FLOOR_QUANTILE = 0.2


def spectral_tone_centers(samples: np.ndarray, sample_rate: float, symbol_rate: float, order: int):
    """Locate `order` FSK tones as spectral peaks. Returns sorted centers in Hz,
    or None if the PSD does not show `order` comparable, resolvable peaks.

    The reference grid comes from the frequency domain, independent of the
    time-domain tone samples that are later judged against it -- so noise in
    those samples cannot manufacture its own reference (percentile or
    k-means grids did exactly that). A PSK/QAM spectrum has one main lobe,
    so it yields no valid M-tone grid."""
    freqs, psd_db = power_spectrum(samples, sample_rate)
    bin_hz = freqs[1] - freqs[0]

    # Welch averages K segments, so each noise bin is chi-square(2K)/(2K)
    # distributed. Noise floor = a low quantile of the PSD (robust to the
    # signal occupying part of the band); a genuine tone must exceed the
    # floor by the ratio that the max of n_bins noise bins would reach.
    nperseg = min(1024, len(samples))
    k_segments = max(1, (len(samples) - nperseg) // max(1, nperseg // 2) + 1)
    dof = 2 * k_segments
    ratio = chi2.ppf(1 - PEAK_FALSE_ALARM / len(freqs), dof) / chi2.ppf(NOISE_FLOOR_QUANTILE, dof)
    floor_db = np.quantile(psd_db, NOISE_FLOOR_QUANTILE)
    significance_db = floor_db + 10.0 * np.log10(ratio)

    min_sep_bins = max(1, int(round(0.5 * symbol_rate / bin_hz)))
    peaks, _ = find_peaks(psd_db, distance=min_sep_bins, height=significance_db)
    if len(peaks) < order:
        return None
    strongest = peaks[np.argsort(psd_db[peaks])[::-1][:order]]
    if psd_db[strongest].min() < psd_db[strongest].max() - TONE_PEAK_WINDOW_DB:
        return None
    return np.sort(freqs[strongest])


def demodulate_fsk(samples: np.ndarray, sample_rate: float, symbol_rate: float, order: int = 2,
                   spectrum_samples: np.ndarray = None) -> dict:
    """Non-coherent FSK demod via instantaneous frequency (differentiated phase).

    spectrum_samples: the signal before any search filtering. Tone centers are
    located in ITS spectrum, because low-pass filtering reshapes a PSK/QAM
    lobe into ripples that could pass as tone peaks."""
    empty = {"bits": np.array([], dtype=np.uint8), "llr": np.array([]), "evm": 1.0, "symbols": np.array([]), "order": order}
    if len(samples) < 2:
        return empty

    phase = np.unwrap(np.angle(samples))
    inst_freq = np.diff(phase) * sample_rate / (2 * np.pi)
    inst_freq = np.concatenate([[inst_freq[0]], inst_freq])

    tones = symbol_decimate(inst_freq.astype(np.complex128), sample_rate, symbol_rate).real
    if len(tones) < order:
        return {**empty, "symbols": tones}

    ref = samples if spectrum_samples is None else spectrum_samples
    centers = spectral_tone_centers(ref, sample_rate, symbol_rate, order)
    if centers is None:
        # Low modulation-index FSK (h < ~1) has a unimodal PSD with no
        # resolvable per-tone humps, so this signal is not recognized as
        # FSK. A time-domain fallback was tried and rejected: forcing a
        # k-means split of the instantaneous-frequency samples into `order`
        # groups looks "statistically significant" by an ANOVA F-test on
        # almost ANY modulation (even clean BPSK), because bisecting a large
        # unimodal sample always produces substantial between/within
        # variance -- that is a property of forced clustering, not evidence
        # of real tone separation, so it cannot be used to discriminate FSK
        # from PSK/QAM's own instantaneous-frequency transition noise.
        return {**empty, "symbols": tones}

    dists = np.abs(tones[:, None] - centers[None, :])
    levels = np.argmin(dists, axis=1)
    nearest_dist = np.min(dists, axis=1)
    spacing = float(np.min(np.diff(centers))) if order > 1 else 1.0
    evm = float(np.clip(np.mean(nearest_dist) / (spacing + 1e-9), 0.0, 1.0))

    bits_per_symbol = int(np.log2(order))
    bits = np.zeros(len(levels) * bits_per_symbol, dtype=np.uint8)
    for i, lvl in enumerate(levels):
        for b in range(bits_per_symbol):
            bits[i * bits_per_symbol + b] = (lvl >> (bits_per_symbol - 1 - b)) & 1

    labels = bit_labels_for(order, np.arange(order))  # natural binary, matching the hard-decision mapping above
    llr = compute_llr(tones, centers, labels, nearest_dist)

    return {"bits": bits, "llr": llr, "evm": evm, "symbols": tones, "order": order, "tone_centers": centers.tolist()}
