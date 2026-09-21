import numpy as np

from core.isolation.spectrum import power_spectrum


def estimate_carrier_frequency(samples: np.ndarray, sample_rate: float, center_frequency: float = 0.0) -> float:
    """Absolute carrier estimate = tuner center frequency + strongest baseband offset."""
    freqs, psd_db = power_spectrum(samples, sample_rate)
    peak_offset = float(freqs[np.argmax(psd_db)])
    return center_frequency + peak_offset
