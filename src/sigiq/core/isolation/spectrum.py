import numpy as np
from scipy.signal import welch, spectrogram


def power_spectrum(samples: np.ndarray, sample_rate: float, nperseg: int = 1024) -> tuple:
    """Welch PSD estimate. Returns (freqs_hz, psd_db)."""
    nperseg = min(nperseg, len(samples))
    freqs, psd = welch(samples, fs=sample_rate, nperseg=nperseg, return_onesided=not np.iscomplexobj(samples))
    freqs = np.fft.fftshift(freqs) if np.iscomplexobj(samples) else freqs
    psd = np.fft.fftshift(psd) if np.iscomplexobj(samples) else psd
    psd_db = 10 * np.log10(psd + 1e-15)
    return freqs, psd_db


def waterfall(samples: np.ndarray, sample_rate: float, nperseg: int = 256, noverlap: int = 128) -> tuple:
    """Spectrogram (time-frequency) for the waterfall view.

    Returns (freqs_hz, times_sec, sxx_db) with sxx_db shape (n_times, n_freqs).
    """
    nperseg = min(nperseg, max(16, len(samples) // 4))
    noverlap = min(noverlap, nperseg - 1)
    freqs, times, sxx = spectrogram(
        samples, fs=sample_rate, nperseg=nperseg, noverlap=noverlap,
        return_onesided=not np.iscomplexobj(samples), mode="psd",
    )
    if np.iscomplexobj(samples):
        freqs = np.fft.fftshift(freqs)
        sxx = np.fft.fftshift(sxx, axes=0)
    sxx_db = 10 * np.log10(sxx.T + 1e-15)
    return freqs, times, sxx_db
