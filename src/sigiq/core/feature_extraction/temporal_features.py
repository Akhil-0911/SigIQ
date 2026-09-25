import numpy as np


def extract_temporal_features(samples: np.ndarray) -> dict:
    envelope = np.abs(samples)
    mean_power = np.mean(envelope ** 2)
    peak_power = np.max(envelope ** 2)
    papr_db = 10 * np.log10(peak_power / mean_power) if mean_power > 0 else 0.0

    # envelope variance is high for AM/ASK/QAM, near-zero for constant-envelope (FM/FSK/PSK)
    envelope_std = float(np.std(envelope) / (np.mean(envelope) + 1e-12))

    return {
        "papr_db": float(papr_db),
        "envelope_variation": envelope_std,
    }
