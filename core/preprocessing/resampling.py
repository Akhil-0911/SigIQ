import numpy as np


def decimate_for_visualization(samples: np.ndarray, max_points: int = 4000) -> np.ndarray:
    """Downsample (min/max envelope) purely for plotting."""
    n = len(samples)
    if n <= max_points:
        return samples
    step = n // max_points
    trimmed = samples[: step * max_points]
    reshaped = trimmed.reshape(max_points, step)
    return reshaped[:, 0]
