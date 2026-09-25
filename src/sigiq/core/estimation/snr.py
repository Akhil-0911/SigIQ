"""SNR estimation by the second/fourth-moment (M2M4) method.

For a complex signal s plus circular Gaussian noise n, with p = |x|^2:
    M2 = E[p]   = S + N
    M4 = E[p^2] = ka*S^2 + 4*S*N + 2*N^2
where ka = E|s|^4 / (E|s|^2)^2 is the kurtosis of the noise-free signal's
envelope (1 for constant-envelope PSK/FSK, 1.32 for square 16-QAM).
Substituting N = M2 - S gives  S = sqrt((M4 - 2*M2^2) / (ka - 2)).

The result depends on the assumed modulation through ka, so callers pass the
ka of the hypothesis they are evaluating.
"""
import numpy as np

# Moment estimators cannot resolve a noise power far below the sampling error
# of M4, so readings outside this range are clamped rather than reported as
# false precision.
SNR_MIN_DB = -10.0
SNR_MAX_DB = 40.0


def envelope_kurtosis(constellation: np.ndarray) -> float:
    """ka for an ideal constellation with equiprobable points."""
    p = np.abs(np.asarray(constellation)) ** 2
    return float(np.mean(p ** 2) / (np.mean(p) ** 2))


def estimate_snr(samples: np.ndarray, sample_rate: float = None, kurtosis_factor: float = 1.0) -> float:
    x = np.asarray(samples)
    x = x - np.mean(x)
    p = np.abs(x) ** 2
    m2, m4 = float(np.mean(p)), float(np.mean(p ** 2))
    if m2 <= 0 or abs(kurtosis_factor - 2.0) < 1e-6:
        return 0.0
    s_sq = (m4 - 2.0 * m2 ** 2) / (kurtosis_factor - 2.0)
    signal = np.sqrt(max(s_sq, 1e-12))
    noise = max(m2 - signal, 1e-12)
    return float(np.clip(10.0 * np.log10(signal / noise), SNR_MIN_DB, SNR_MAX_DB))
