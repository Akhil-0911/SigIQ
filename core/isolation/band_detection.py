import numpy as np


def occupied_bandwidth(freqs: np.ndarray, psd_db: np.ndarray, fraction: float = 0.99) -> tuple:
    """Bandwidth containing `fraction` of total power. Returns (bw_hz, f_low, f_high)."""
    psd_linear = 10 ** (psd_db / 10)
    total = np.sum(psd_linear)
    if total == 0:
        return 0.0, freqs[0], freqs[-1]
    cumulative = np.cumsum(psd_linear) / total
    low_idx = int(np.searchsorted(cumulative, (1 - fraction) / 2))
    high_idx = int(np.searchsorted(cumulative, 1 - (1 - fraction) / 2))
    high_idx = min(high_idx, len(freqs) - 1)
    f_low, f_high = freqs[low_idx], freqs[high_idx]
    return float(f_high - f_low), float(f_low), float(f_high)


def detect_bands(freqs: np.ndarray, psd_db: np.ndarray, threshold_db_above_floor: float = 10.0) -> list:
    """Find contiguous frequency bands sitting above the noise floor."""
    floor = np.median(psd_db)
    active = psd_db > (floor + threshold_db_above_floor)
    bands = []
    start = None
    for i, is_active in enumerate(active):
        if is_active and start is None:
            start = i
        elif not is_active and start is not None:
            bands.append((float(freqs[start]), float(freqs[i - 1])))
            start = None
    if start is not None:
        bands.append((float(freqs[start]), float(freqs[-1])))
    return bands
