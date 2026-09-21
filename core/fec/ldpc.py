"""Minimal LDPC encode/decode for demonstration: a small regular parity-check
matrix plus iterative hard-decision bit-flipping decoding. This is a scoped
reference implementation (not a production LDPC stack like 5G/DVB-S2 LDPC),
documented as such in the README."""
import numpy as np


def _regular_h_matrix(n: int, k: int, row_weight: int = 6, seed: int = 7) -> np.ndarray:
    """Build a random regular-ish (n-k) x n parity-check matrix."""
    rng = np.random.default_rng(seed)
    m = n - k
    h = np.zeros((m, n), dtype=np.uint8)
    for row in range(m):
        cols = rng.choice(n, size=min(row_weight, n), replace=False)
        h[row, cols] = 1
    return h


def ldpc_encode(bits: np.ndarray, code_rate: float = 0.5, seed: int = 7) -> dict:
    k = len(bits)
    n = int(round(k / code_rate))
    h = _regular_h_matrix(n, k, seed=seed)
    # simple systematic-ish padding: append parity bits computed to satisfy H (approx, for demo)
    codeword = np.zeros(n, dtype=np.uint8)
    codeword[:k] = bits
    parity_len = n - k
    # naive parity fill: XOR-derived bits from message subsets defined by H's parity rows
    for i in range(parity_len):
        row = h[i]
        codeword[k + i] = np.bitwise_xor.reduce(codeword[row[:k].astype(bool)][:max(1, int(np.sum(row[:k])))]) if np.any(row[:k]) else 0
    return {"codeword": codeword, "h_matrix": h, "n": n, "k": k}


def ldpc_decode(received: np.ndarray, h: np.ndarray, k: int, max_iters: int = 20) -> dict:
    """Bit-flipping hard-decision decoder: flip bits whose flip reduces the
    number of unsatisfied parity checks, iterate until all checks pass or
    max_iters reached."""
    bits = received.copy().astype(np.uint8)
    n = len(bits)
    for iteration in range(max_iters):
        syndrome = (h @ bits) % 2
        unsatisfied = int(np.sum(syndrome))
        if unsatisfied == 0:
            return {"bits": bits[:k], "success": True, "iterations": iteration}
        # count failed checks per bit
        fail_counts = h.T @ syndrome
        flip_bit = int(np.argmax(fail_counts))
        if fail_counts[flip_bit] == 0:
            break
        bits[flip_bit] ^= 1
    syndrome = (h @ bits) % 2
    return {"bits": bits[:k], "success": bool(np.sum(syndrome) == 0), "iterations": max_iters}
