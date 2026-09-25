"""Frequency translation and low-pass filtering used to bring a selected
signal to baseband:  x_bb[n] = x[n] * exp(-j*2*pi*f_shift*n/Fs)."""
import numpy as np
from scipy.signal import butter, sosfiltfilt


def frequency_translate(samples: np.ndarray, sample_rate: float, shift_hz: float) -> np.ndarray:
    if shift_hz == 0.0:
        return samples
    n = np.arange(len(samples))
    return samples * np.exp(-2j * np.pi * shift_hz * n / sample_rate)


def lowpass(samples: np.ndarray, sample_rate: float, cutoff_hz: float, order: int = 6) -> np.ndarray:
    """Zero-phase Butterworth low-pass (passband -cutoff..+cutoff on complex baseband)."""
    nyquist = sample_rate / 2.0
    if cutoff_hz <= 0 or cutoff_hz >= nyquist * 0.98:
        return samples
    sos = butter(order, cutoff_hz / nyquist, btype="low", output="sos")
    return sosfiltfilt(sos, samples)
