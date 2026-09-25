import numpy as np


def symbol_decimate(samples: np.ndarray, sample_rate: float, symbol_rate: float) -> np.ndarray:
    """Simple timing recovery: decimate to one sample per symbol at the
    estimated best phase (the phase whose samples have max average energy)."""
    if symbol_rate <= 0:
        return samples
    sps = sample_rate / symbol_rate  # samples per symbol
    if sps < 1:
        return samples
    sps_int = max(1, int(round(sps)))

    best_phase, best_energy = 0, -1.0
    for phase in range(sps_int):
        candidate = samples[phase::sps_int]
        if len(candidate) == 0:
            continue
        energy = np.mean(np.abs(candidate) ** 2)
        if energy > best_energy:
            best_energy, best_phase = energy, phase
    return samples[best_phase::sps_int]


def min_constellation_spacing(constellation: np.ndarray) -> float:
    """Minimum distance between any two distinct points in a constellation.
    Used to normalize EVM as a fraction of symbol margin rather than an
    absolute distance -- without this, higher-order constellations (denser
    point grids, e.g. 16-QAM vs BPSK) get a systematically smaller raw EVM
    for the same actual demodulation quality, biasing candidate comparison
    toward higher order regardless of fit."""
    if len(constellation) < 2:
        return 1.0
    dists = np.abs(constellation[:, None] - constellation[None, :])
    np.fill_diagonal(dists, np.inf)
    return float(np.min(dists))


def decision_directed_phase_correct(symbols: np.ndarray, constellation: np.ndarray,
                                     symmetry_order: int, search_points: int = 64) -> np.ndarray:
    """Residual-phase correction via brute-force decision-directed search:
    try evenly spaced rotations over the constellation's rotational symmetry
    interval (2*pi/symmetry_order) and keep whichever minimizes total
    squared distance to the nearest ideal constellation point.

    This replaces the classic M-th-power ("Costas") method, which only works
    for constant-modulus constellations (M-PSK). Applying it to QAM (where
    amplitude varies symbol-to-symbol) does NOT cleanly strip the data
    modulation -- raising varying-amplitude symbols to the 4th power leaves a
    large data-dependent bias, which showed up as a large *spurious* phase
    rotation (tens of degrees) even on a signal with zero actual carrier
    offset, inflating EVM for otherwise-correct QAM demodulation. Comparing
    directly against the ideal constellation (as done here) works for any
    constellation shape, constant-modulus or not.
    """
    if len(symbols) == 0:
        return symbols
    best_phase, best_error = 0.0, np.inf
    ambiguity = 2 * np.pi / symmetry_order
    for phase in np.linspace(0, ambiguity, search_points, endpoint=False):
        rotated = symbols * np.exp(-1j * phase)
        nearest_dist = np.min(np.abs(rotated[:, None] - constellation[None, :]), axis=1)
        error = float(np.mean(nearest_dist ** 2))
        if error < best_error:
            best_error, best_phase = error, phase
    return symbols * np.exp(-1j * best_phase)
