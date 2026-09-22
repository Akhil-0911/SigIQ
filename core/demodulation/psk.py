import numpy as np

from core.demodulation.synchronization import symbol_decimate, decision_directed_phase_correct, min_constellation_spacing
from core.demodulation.soft_bits import bit_labels_for, compute_llr


def psk_constellation(order: int) -> np.ndarray:
    angles = 2 * np.pi * np.arange(order) / order
    return np.exp(1j * angles)


def _gray_code(order: int) -> np.ndarray:
    idx = np.arange(order)
    return idx ^ (idx >> 1)


def _fit(symbols: np.ndarray, order: int) -> tuple:
    """Normalize, phase-correct against the ideal constellation, decide.
    EVM = RMS distance to the nearest ideal point, divided by the
    constellation's minimum point spacing so orders are comparable (a denser
    grid must not look better just because its points are closer)."""
    symbols = symbols / (np.mean(np.abs(symbols)) + 1e-12)
    constellation = psk_constellation(order)
    symbols = decision_directed_phase_correct(symbols, constellation, symmetry_order=order)
    dists = np.abs(symbols[:, None] - constellation[None, :])
    nearest = np.argmin(dists, axis=1)
    errors = np.min(dists, axis=1)
    evm = float(np.sqrt(np.mean(errors ** 2)) / (min_constellation_spacing(constellation) + 1e-12))
    return symbols, nearest, errors, evm


def demodulate_psk(samples: np.ndarray, sample_rate: float, symbol_rate: float, order: int = 2) -> dict:
    """order=2 -> BPSK, order=4 -> QPSK, etc. Returns bits + evidence for scoring,
    plus per-bit LLRs (soft information) for FEC decoders that can use them."""
    symbols = symbol_decimate(samples, sample_rate, symbol_rate)
    if len(symbols) == 0:
        return {"bits": np.array([], dtype=np.uint8), "llr": np.array([]), "evm": 1.0, "symbols": symbols}

    symbols, nearest, errors, evm = _fit(symbols, order)

    gray = _gray_code(order)
    bits_per_symbol = int(np.log2(order))
    bits = np.zeros(len(nearest) * bits_per_symbol, dtype=np.uint8)
    for i, sym_idx in enumerate(nearest):
        g = gray[sym_idx]
        for b in range(bits_per_symbol):
            bits[i * bits_per_symbol + b] = (g >> (bits_per_symbol - 1 - b)) & 1

    labels = bit_labels_for(order, gray)
    llr = compute_llr(symbols, psk_constellation(order), labels, errors)

    return {"bits": bits, "llr": llr, "evm": evm, "symbols": symbols, "order": order}
