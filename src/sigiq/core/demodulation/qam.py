import numpy as np

from sigiq.core.demodulation.synchronization import symbol_decimate, decision_directed_phase_correct, min_constellation_spacing
from sigiq.core.demodulation.soft_bits import bit_labels_for, compute_llr


def qam_constellation(order: int) -> np.ndarray:
    """Square QAM constellation (order must be a perfect square, e.g. 16, 64)."""
    side = int(round(np.sqrt(order)))
    levels = np.arange(side) * 2 - (side - 1)
    i, q = np.meshgrid(levels, levels)
    points = (i + 1j * q).flatten()
    return points / np.sqrt(np.mean(np.abs(points) ** 2))  # unit average power


def _fit(symbols: np.ndarray, order: int) -> tuple:
    symbols = symbols / (np.sqrt(np.mean(np.abs(symbols) ** 2)) + 1e-12)
    constellation = qam_constellation(order)
    symbols = decision_directed_phase_correct(symbols, constellation, symmetry_order=4)  # square QAM: 4-fold symmetry
    dists = np.abs(symbols[:, None] - constellation[None, :])
    nearest = np.argmin(dists, axis=1)
    errors = np.min(dists, axis=1)
    evm = float(np.sqrt(np.mean(errors ** 2)) / (min_constellation_spacing(constellation) + 1e-12))
    return symbols, nearest, errors, evm


def demodulate_qam(samples: np.ndarray, sample_rate: float, symbol_rate: float, order: int = 16) -> dict:
    symbols = symbol_decimate(samples, sample_rate, symbol_rate)
    if len(symbols) == 0:
        return {"bits": np.array([], dtype=np.uint8), "llr": np.array([]), "evm": 1.0, "symbols": symbols}

    symbols, nearest, errors, evm = _fit(symbols, order)

    bits_per_symbol = int(np.log2(order))
    bits = np.zeros(len(nearest) * bits_per_symbol, dtype=np.uint8)
    for i, sym_idx in enumerate(nearest):
        for b in range(bits_per_symbol):
            bits[i * bits_per_symbol + b] = (sym_idx >> (bits_per_symbol - 1 - b)) & 1

    labels = bit_labels_for(order, np.arange(order))  # natural binary, matching the hard-decision mapping above
    llr = compute_llr(symbols, qam_constellation(order), labels, errors)

    return {"bits": bits, "llr": llr, "evm": evm, "symbols": symbols, "order": order}
