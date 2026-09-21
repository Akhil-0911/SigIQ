from core.isolation.spectrum import power_spectrum
from core.isolation.band_detection import occupied_bandwidth


def estimate_bandwidth(samples, sample_rate: float) -> float:
    freqs, psd_db = power_spectrum(samples, sample_rate)
    bw, _, _ = occupied_bandwidth(freqs, psd_db)
    return bw
