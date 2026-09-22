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
