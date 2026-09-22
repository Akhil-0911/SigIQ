import numpy as np

from core.isolation.spectrum import power_spectrum


def estimate_carrier_offset(samples: np.ndarray, sample_rate: float) -> float:
    """Offset of the signal's spectral centre of mass from baseband DC, Hz.

    Uses the power-weighted centroid of the PSD after subtracting twice the
    median (noise-floor) level, so a suppressed-carrier or multi-tone spectrum
    (BPSK, FSK) is located by where its power sits, not by a single peak.
    """
    freqs, psd_db = power_spectrum(samples, sample_rate)
    psd = 10 ** (psd_db / 10)
    weights = np.clip(psd - 2.0 * np.median(psd), 0.0, None)
    total = float(np.sum(weights))
    if total <= 0:
        return 0.0
    return float(np.sum(freqs * weights) / total)
