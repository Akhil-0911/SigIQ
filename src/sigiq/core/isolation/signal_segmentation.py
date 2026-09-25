import numpy as np

from sigiq.core.pipeline.models import IsolatedSignal


def segment_by_energy(samples: np.ndarray, sample_rate: float, window: int = 256,
                       threshold_db_above_floor: float = 6.0) -> IsolatedSignal:
    """Trim leading/trailing silence using a sliding-window energy envelope."""
    n = len(samples)
    if n < window * 2:
        return IsolatedSignal(samples=samples, sample_rate=sample_rate, segment_start=0, segment_end=n)

    n_windows = n // window
    trimmed = samples[: n_windows * window].reshape(n_windows, window)
    energy_db = 10 * np.log10(np.mean(np.abs(trimmed) ** 2, axis=1) + 1e-15)
    floor = np.median(energy_db)
    active = np.where(energy_db > floor + threshold_db_above_floor)[0]

    if len(active) == 0:
        return IsolatedSignal(samples=samples, sample_rate=sample_rate, segment_start=0, segment_end=n)

    start = active[0] * window
    end = min((active[-1] + 1) * window, n)
    return IsolatedSignal(samples=samples[start:end], sample_rate=sample_rate, segment_start=int(start), segment_end=int(end))
