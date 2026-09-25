import numpy as np


def moving_average_denoise(samples: np.ndarray, window: int = 5) -> np.ndarray:
    if window <= 1:
        return samples
    kernel = np.ones(window) / window
    if np.iscomplexobj(samples):
        return np.convolve(samples.real, kernel, mode="same") + 1j * np.convolve(samples.imag, kernel, mode="same")
    return np.convolve(samples, kernel, mode="same")


def spectral_gate(samples: np.ndarray, sample_rate: float, threshold_db: float = -40.0) -> np.ndarray:
    """Zero out FFT bins below a noise-floor threshold relative to the peak, then invert."""
    spectrum = np.fft.fft(samples)
    mag_db = 20 * np.log10(np.abs(spectrum) + 1e-12)
    peak = np.max(mag_db)
    mask = mag_db > (peak + threshold_db)
    return np.fft.ifft(spectrum * mask)
