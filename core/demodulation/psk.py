import numpy as np

from core.demodulation.synchronization import symbol_decimate, decision_directed_phase_correct, min_constellation_spacing


def _psk_constellation(order: int) -> np.ndarray:
    angles = 2 * np.pi * np.arange(order) / order
    return np.exp(1j * angles)


def demodulate_psk(samples: np.ndarray, sample_rate: float, symbol_rate: float, order: int = 2) -> dict:
    """order=2 -> BPSK, order=4 -> QPSK, etc. Returns bits + evidence for scoring."""
    symbols = symbol_decimate(samples, sample_rate, symbol_rate)
    if len(symbols) == 0:
        return {"bits": np.array([], dtype=np.uint8), "evm": 1.0, "symbols": symbols}

    symbols = symbols / (np.mean(np.abs(symbols)) + 1e-12)
    constellation = _psk_constellation(order)
    symbols = decision_directed_phase_correct(symbols, constellation, symmetry_order=order)
    dists = np.abs(symbols[:, None] - constellation[None, :])
    nearest = np.argmin(dists, axis=1)

    # EVM: RMS distance from nearest ideal constellation point, normalized by
    # the constellation's own minimum point spacing so it's comparable
    # across orders (a denser grid shouldn't look "better fit" just because
    # its points are closer together)
    errors = np.min(dists, axis=1)
    spacing = min_constellation_spacing(constellation)
    evm = float(np.sqrt(np.mean(errors ** 2)) / (spacing + 1e-12))

    bits_per_symbol = int(np.log2(order))
    bits = np.zeros(len(nearest) * bits_per_symbol, dtype=np.uint8)
    for i, sym_idx in enumerate(nearest):
        gray = sym_idx ^ (sym_idx >> 1)  # gray-code mapping
        for b in range(bits_per_symbol):
            bits[i * bits_per_symbol + b] = (gray >> (bits_per_symbol - 1 - b)) & 1

    return {"bits": bits, "evm": evm, "symbols": symbols, "order": order}
