from core.feature_extraction.cyclostationary import symbol_rate_from_cyclic_spectrum


def estimate_symbol_rate(samples, sample_rate: float) -> float:
    return symbol_rate_from_cyclic_spectrum(samples, sample_rate)
