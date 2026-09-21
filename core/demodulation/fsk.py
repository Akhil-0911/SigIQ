import numpy as np

from core.demodulation.synchronization import symbol_decimate


def demodulate_fsk(samples: np.ndarray, sample_rate: float, symbol_rate: float, order: int = 2,
                    snr_db: float = None) -> dict:
    """Non-coherent FSK demod via instantaneous frequency (differentiated phase)."""
    if len(samples) < 2:
        return {"bits": np.array([], dtype=np.uint8), "evm": 1.0, "symbols": np.array([])}

    phase = np.unwrap(np.angle(samples))
    inst_freq = np.diff(phase) * sample_rate / (2 * np.pi)
    inst_freq = np.concatenate([[inst_freq[0]], inst_freq])

    tones = symbol_decimate(inst_freq.astype(np.complex128), sample_rate, symbol_rate).real
    if len(tones) < order:
        return {"bits": np.array([], dtype=np.uint8), "evm": 1.0, "symbols": tones}

    # Compare against FIXED, evenly-spaced ideal tone centers (spanning the
    # 5th-95th percentile of the observed instantaneous frequency, which is
    # robust to outliers but NOT fit to minimize assignment error) -- the
    # same principle PSK/QAM already use (distance to a fixed ideal
    # constellation, never a self-fit one). Earlier versions clustered the
    # data to itself (quantile splits, then k-means), which always finds an
    # apparently-tight partition of ANY data by construction (k-means
    # directly maximizes between/within separation), making evm artificially
    # near-0 even for signals with no real multi-tone structure.
    lo, hi = np.percentile(tones, [5, 95])
    if hi <= lo:
        hi = lo + 1e-6
    ideal_centers = np.linspace(lo, hi, order)
    dists = np.abs(tones[:, None] - ideal_centers[None, :])
    levels = np.argmin(dists, axis=1)
    nearest_dist = np.min(dists, axis=1)

    spacing = (hi - lo) / max(order - 1, 1)
    evm = float(np.clip(np.mean(nearest_dist) / (spacing + 1e-9), 0.0, 1.0))
    tone_centers = ideal_centers

    # Reject the fit outright if the observed tone spread is no larger than
    # what pure AWGN phase noise would produce at the measured SNR -- without
    # this, evm is still ultimately derived from the same noisy data it is
    # judging (percentile range), so on a non-FSK signal it can look
    # "reasonable" purely because clustering-adjacent noise always has SOME
    # spread. This ties the judgment to an independent, theory-grounded
    # expectation (phase-noise variance from Cramer-Rao at the given SNR)
    # instead of trusting the data's own self-reported spread.
    if snr_db is not None:
        snr_linear = 10 ** (snr_db / 10)
        phase_noise_var = 1.0 / (2 * max(snr_linear, 1e-6))          # rad^2, high-SNR approximation
        freq_noise_var = 2 * phase_noise_var                          # differencing two phase samples
        freq_noise_std_hz = np.sqrt(freq_noise_var) * sample_rate / (2 * np.pi)
        expected_noise_range = 3.29 * freq_noise_std_hz               # ~5th-95th percentile range for Gaussian noise
        observed_range = hi - lo
        if observed_range < 1.5 * expected_noise_range:
            evm = 1.0

    bits_per_symbol = int(np.log2(order))
    bits = np.zeros(len(levels) * bits_per_symbol, dtype=np.uint8)
    for i, lvl in enumerate(levels):
        for b in range(bits_per_symbol):
            bits[i * bits_per_symbol + b] = (lvl >> (bits_per_symbol - 1 - b)) & 1

    return {"bits": bits, "evm": evm, "symbols": tones, "order": order, "tone_centers": tone_centers.tolist()}
