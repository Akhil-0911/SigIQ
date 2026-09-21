import numpy as np
from scipy.signal import resample_poly
from math import gcd


def resample_to(samples: np.ndarray, orig_rate: float, target_rate: float) -> np.ndarray:
    if orig_rate == target_rate:
        return samples
    g = gcd(int(orig_rate), int(target_rate))
    up = int(target_rate) // g
    down = int(orig_rate) // g
    if np.iscomplexobj(samples):
        return resample_poly(samples.real, up, down) + 1j * resample_poly(samples.imag, up, down)
    return resample_poly(samples, up, down)


def decimate_for_visualization(samples: np.ndarray, max_points: int = 4000) -> np.ndarray:
    """Downsample (min/max envelope) purely for sending to the browser."""
    n = len(samples)
    if n <= max_points:
        return samples
    step = n // max_points
    trimmed = samples[: step * max_points]
    reshaped = trimmed.reshape(max_points, step)
    return reshaped[:, 0]
