from core.feature_extraction.signal_statistics import estimate_snr_db


def estimate_snr(samples, sample_rate: float) -> float:
    return estimate_snr_db(samples, sample_rate)
