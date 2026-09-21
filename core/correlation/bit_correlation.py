import numpy as np


def bit_cross_correlate(bits: np.ndarray, pattern: np.ndarray) -> np.ndarray:
    """Normalized cross-correlation of a bipolar (+/-1) version of the bit
    stream against a known pattern, sliding position by position."""
    if len(bits) < len(pattern) or len(pattern) == 0:
        return np.array([])
    bipolar_bits = bits.astype(np.float64) * 2 - 1
    bipolar_pattern = pattern.astype(np.float64) * 2 - 1
    n = len(bits) - len(pattern) + 1
    scores = np.zeros(n)
    for i in range(n):
        scores[i] = np.dot(bipolar_bits[i:i + len(pattern)], bipolar_pattern) / len(pattern)
    return scores
