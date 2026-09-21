import numpy as np
from scipy.signal import butter, sosfiltfilt


def lowpass(samples: np.ndarray, sample_rate: float, cutoff_hz: float, order: int = 6) -> np.ndarray:
    nyq = sample_rate / 2.0
    normal_cutoff = min(cutoff_hz / nyq, 0.999)
    sos = butter(order, normal_cutoff, btype="low", output="sos")
    return sosfiltfilt(sos, samples.real) + 1j * sosfiltfilt(sos, samples.imag) \
        if np.iscomplexobj(samples) else sosfiltfilt(sos, samples)


def bandpass(samples: np.ndarray, sample_rate: float, low_hz: float, high_hz: float, order: int = 6) -> np.ndarray:
    nyq = sample_rate / 2.0
    low = max(low_hz / nyq, 1e-6)
    high = min(high_hz / nyq, 0.999)
    sos = butter(order, [low, high], btype="band", output="sos")
    if np.iscomplexobj(samples):
        return sosfiltfilt(sos, samples.real) + 1j * sosfiltfilt(sos, samples.imag)
    return sosfiltfilt(sos, samples)


def frequency_shift(samples: np.ndarray, sample_rate: float, shift_hz: float) -> np.ndarray:
    """Mix samples by shift_hz -- used to recenter a channel found off-center."""
    n = np.arange(len(samples))
    return samples * np.exp(-1j * 2 * np.pi * shift_hz * n / sample_rate)
