import numpy as np

from core.isolation.spectrum import power_spectrum
from core.isolation.band_detection import detect_bands


def strongest_channel(samples: np.ndarray, sample_rate: float) -> dict:
    """Pick the widest/strongest active band and report its center offset + width."""
    freqs, psd_db = power_spectrum(samples, sample_rate)
    bands = detect_bands(freqs, psd_db)
    if not bands:
        return {"center_offset_hz": 0.0, "bandwidth_hz": sample_rate / 2}
    widest = max(bands, key=lambda b: b[1] - b[0])
    center = (widest[0] + widest[1]) / 2
    bw = widest[1] - widest[0]
    return {"center_offset_hz": float(center), "bandwidth_hz": float(bw)}
