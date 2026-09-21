import numpy as np
from scipy.stats import kurtosis, skew


def extract_signal_statistics(samples: np.ndarray) -> dict:
    mag = np.abs(samples)
    return {
        "kurtosis": float(kurtosis(mag)),
        "skewness": float(skew(mag)),
        "mean_magnitude": float(np.mean(mag)),
        "std_magnitude": float(np.std(mag)),
    }


def estimate_snr_db(samples: np.ndarray, sample_rate: float, signal_bw_fraction: float = 0.3) -> float:
    """Rough SNR estimate: power inside the central band (signal+noise) vs. edges (noise-only)."""
    spectrum = np.fft.fftshift(np.fft.fft(samples))
    power = np.abs(spectrum) ** 2
    n = len(power)
    center = n // 2
    half_signal = int(n * signal_bw_fraction / 2)

    signal_region = power[max(0, center - half_signal): center + half_signal]
    noise_region = np.concatenate([power[: max(0, center - half_signal)], power[center + half_signal:]])

    signal_power = np.mean(signal_region) if len(signal_region) else 0.0
    noise_power = np.mean(noise_region) if len(noise_region) else 1e-12
    noise_power = max(noise_power, 1e-12)

    snr_linear = max(signal_power / noise_power - 1, 1e-6)
    return float(10 * np.log10(snr_linear))
