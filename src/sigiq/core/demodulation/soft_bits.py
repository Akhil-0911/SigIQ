"""Per-bit LLRs from a demodulated symbol block, shared by PSK/QAM/FSK.

Convention: LLR(b) = log[P(b=1|y) / P(b=0|y)] -- positive means the evidence
favours bit=1, matching each demodulator's own hard-decision rule (nearest
constellation point) at LLR=0.

The noise variance is not a free parameter: it is the same per-symbol nearest-
point residual already computed for EVM (`min_dist`), reused here rather than
re-estimated, so there is exactly one noise measurement per candidate, not two
that could disagree. A circular symmetric complex Gaussian's power splits
evenly between its two real dimensions, hence the /2.
"""
import numpy as np


def bit_labels_for(order: int, code: np.ndarray) -> np.ndarray:
    """code[i] = the bit pattern (MSB first) assigned to constellation index i.
    Shape (order, bits_per_symbol)."""
    bits_per_symbol = int(np.log2(order))
    out = np.zeros((order, bits_per_symbol), dtype=np.uint8)
    for i in range(order):
        v = int(code[i])
        for b in range(bits_per_symbol):
            out[i, b] = (v >> (bits_per_symbol - 1 - b)) & 1
    return out


def compute_llr(symbols: np.ndarray, constellation: np.ndarray, bit_labels: np.ndarray,
                 min_dist: np.ndarray) -> np.ndarray:
    """symbols: decided/corrected symbols (N,). constellation: ideal points (order,).
    bit_labels: (order, bits_per_symbol) from `bit_labels_for`. min_dist: (N,) nearest-
    point residual already computed by the caller's hard-decision fit. Returns a flat
    (N * bits_per_symbol,) LLR array in the same bit order as the hard-decision bits."""
    n = len(symbols)
    bits_per_symbol = bit_labels.shape[1]
    if n == 0 or bits_per_symbol == 0:
        return np.array([])

    sigma2 = float(np.mean(min_dist ** 2)) / 2.0
    sigma2 = max(sigma2, 1e-6)  # a perfect-fit block still needs a finite scale for LLR magnitude

    sq_dist = np.abs(symbols[:, None] - constellation[None, :]) ** 2  # (N, order)
    llr = np.zeros((n, bits_per_symbol))
    for b in range(bits_per_symbol):
        is_one = bit_labels[:, b] == 1
        d0 = sq_dist[:, ~is_one].min(axis=1)
        d1 = sq_dist[:, is_one].min(axis=1)
        llr[:, b] = (d0 - d1) / (2.0 * sigma2)
    return llr.flatten()
