import numpy as np


def remove_dc(samples: np.ndarray) -> np.ndarray:
    return samples - np.mean(samples)


def normalize_power(samples: np.ndarray) -> np.ndarray:
    """Scale so mean signal power is 1.0 (unit average energy per sample)."""
    power = np.mean(np.abs(samples) ** 2)
    if power == 0:
        return samples
    return samples / np.sqrt(power)
