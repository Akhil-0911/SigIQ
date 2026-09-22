from core.feature_extraction.cyclostationary import (
    symbol_rate_and_prominence, line_prominence_at, timing_fit_from_prominence,
)


def timing_prominence_at(samples, sample_rate: float, rate_hz: float) -> float:
    return line_prominence_at(samples, sample_rate, rate_hz)


def estimate_symbol_rate(samples, sample_rate: float) -> float:
    return symbol_rate_and_prominence(samples, sample_rate)[0]


def timing_fit_at(samples, sample_rate: float, rate_hz: float) -> float:
    """0..1 support for `rate_hz` being the symbol clock: how far the cyclic
    line at exactly that rate stands above what noise alone would produce."""
    return timing_fit_from_prominence(line_prominence_at(samples, sample_rate, rate_hz), len(samples))
