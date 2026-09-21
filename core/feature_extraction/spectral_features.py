import numpy as np

from core.isolation.spectrum import power_spectrum
from core.isolation.band_detection import occupied_bandwidth


def extract_spectral_features(samples: np.ndarray, sample_rate: float) -> dict:
    freqs, psd_db = power_spectrum(samples, sample_rate)
    bw, f_low, f_high = occupied_bandwidth(freqs, psd_db)

    psd_linear = 10 ** (psd_db / 10)
    peak_idx = np.argsort(psd_linear)[::-1][:5]
    peaks = sorted(float(freqs[i]) for i in peak_idx)

    # spectral flatness: geometric mean / arithmetic mean of PSD (0=tonal, 1=noise-like)
    psd_pos = psd_linear[psd_linear > 0]
    if len(psd_pos):
        geo_mean = np.exp(np.mean(np.log(psd_pos)))
        arith_mean = np.mean(psd_pos)
        flatness = float(geo_mean / arith_mean) if arith_mean > 0 else 0.0
    else:
        flatness = 0.0

    center_freq = (f_low + f_high) / 2
    return {
        "bandwidth": bw,
        "center_frequency": center_freq,
        "spectral_peaks": peaks,
        "spectral_flatness": flatness,
        "freqs": freqs,
        "psd_db": psd_db,
    }
