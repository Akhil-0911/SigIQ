"""LDPC coding using the IEEE 802.11n quasi-cyclic code (n=648, rate 3/4,
lifting size Z=27). The prototype matrix below is the standard's; the parity-
check matrix H is its Z-lifted expansion (entry s >= 0 is the identity shifted
right by s, -1 is the all-zero block).

Decoding is normalized min-sum message passing seeded with hard-decision
inputs. Only this one code is supported; a stream that is not encoded with it
will not satisfy the parity checks, so the decoder reports failure honestly.
"""
import numpy as np

Z = 27
N = 648
K = 486
M = N - K  # 162 parity checks

PROTOTYPE = np.array([
    [16, 17, 22, 24, 9, 3, 14, -1, 4, 2, 7, -1, 26, -1, 2, -1, 21, -1, 1, 0, -1, -1, -1, -1],
    [25, 12, 12, 3, 3, 26, 6, 21, -1, 15, 22, -1, 15, -1, 4, -1, -1, 16, -1, 0, 0, -1, -1, -1],
    [25, 18, 26, 16, 22, 23, 9, -1, 0, -1, 4, -1, 4, -1, 8, 23, 11, -1, -1, -1, 0, 0, -1, -1],
    [9, 7, 0, 1, 17, -1, -1, 7, 3, -1, 3, 23, -1, 16, -1, -1, 21, -1, 0, -1, -1, 0, 0, -1],
    [24, 5, 26, 7, 1, -1, -1, 15, 24, 15, -1, 8, -1, 13, -1, 13, -1, 11, -1, -1, -1, -1, 0, 0],
    [2, 2, 19, 14, 24, 1, 15, 19, -1, 21, -1, 2, -1, 24, -1, 3, -1, 2, 1, -1, -1, -1, -1, 0],
], dtype=int)

_cache = {}


def parity_check_matrix() -> np.ndarray:
    if "H" not in _cache:
        rows, cols = PROTOTYPE.shape
        h = np.zeros((rows * Z, cols * Z), dtype=np.uint8)
        idx = np.arange(Z)
        for r in range(rows):
            for c in range(cols):
                s = PROTOTYPE[r, c]
                if s >= 0:
                    h[r * Z + idx, c * Z + (idx + s) % Z] = 1
        _cache["H"] = h
    return _cache["H"]


def _gf2_inverse(a: np.ndarray) -> np.ndarray:
    n = a.shape[0]
    aug = np.concatenate([a.copy() % 2, np.eye(n, dtype=np.uint8)], axis=1).astype(np.uint8)
    for col in range(n):
        pivot = next((r for r in range(col, n) if aug[r, col]), None)
        if pivot is None:
            raise ValueError("matrix is singular over GF(2)")
        if pivot != col:
            aug[[col, pivot]] = aug[[pivot, col]]
        for r in range(n):
            if r != col and aug[r, col]:
                aug[r] ^= aug[col]
    return aug[:, n:]


def ldpc_encode(info_bits: np.ndarray) -> np.ndarray:
    """Systematic encode: codeword = [info (486) | parity (162)] per block.
    The input is zero-padded to a whole number of 486-bit blocks."""
    h = parity_check_matrix()
    if "Hp_inv" not in _cache:
        _cache["Hp_inv"] = _gf2_inverse(h[:, K:])
    hs, hp_inv = h[:, :K].astype(np.int64), _cache["Hp_inv"].astype(np.int64)

    info = np.asarray(info_bits, dtype=np.uint8)
    pad = (-len(info)) % K
    info = np.concatenate([info, np.zeros(pad, dtype=np.uint8)])
    out = []
    for i in range(0, len(info), K):
        s = info[i:i + K].astype(np.int64)
        parity = (hp_inv @ ((hs @ s) % 2)) % 2
        out.append(np.concatenate([s, parity]).astype(np.uint8))
    return np.concatenate(out) if out else np.array([], dtype=np.uint8)


def _check_index() -> tuple:
    """Padded (M, W) array of the variable indices in each check, and its mask."""
    if "idx" not in _cache:
        h = parity_check_matrix()
        rows = [np.flatnonzero(h[r]) for r in range(h.shape[0])]
        width = max(len(r) for r in rows)
        idx = np.zeros((len(rows), width), dtype=np.int64)
        mask = np.zeros((len(rows), width), dtype=bool)
        for r, cols in enumerate(rows):
            idx[r, :len(cols)] = cols
            mask[r, :len(cols)] = True
        _cache["idx"], _cache["mask"] = idx, mask
    return _cache["idx"], _cache["mask"]


def _syndrome_weight(bits: np.ndarray) -> int:
    idx, mask = _check_index()
    return int(np.sum((bits[idx] * mask).sum(axis=1) % 2))


def _min_sum_decode_block(hard: np.ndarray, max_iters: int = 30, llr_mag: float = 4.0,
                           alpha: float = 0.8, channel_llr: np.ndarray = None) -> tuple:
    """Flooding normalized min-sum over all checks at once.

    channel_llr: real per-bit LLR from the demodulator, positive = evidence
    for bit 1 (the demodulators' convention). This decoder's internal sign is
    the opposite (positive = evidence for bit 0), so it is negated here. When
    not supplied, a fixed-magnitude LLR is synthesized from the hard bits
    (the only option when the caller has no soft information)."""
    idx, mask = _check_index()
    rows = np.arange(idx.shape[0])
    if channel_llr is not None:
        channel = -np.asarray(channel_llr, dtype=np.float64)
    else:
        channel = np.where(hard == 0, llr_mag, -llr_mag).astype(np.float64)
    c2v = np.zeros(idx.shape)
    posterior = channel.copy()

    for it in range(max_iters):
        hard_now = (posterior < 0).astype(np.uint8)
        if _syndrome_weight(hard_now) == 0:
            return hard_now, True, it
        v2c = posterior[idx] - c2v
        sign = np.where(v2c < 0, -1.0, 1.0)
        sign[~mask] = 1.0
        mag = np.abs(v2c)
        mag[~mask] = np.inf
        arg1 = mag.argmin(axis=1)
        min1 = mag[rows, arg1]
        mag[rows, arg1] = np.inf
        min2 = mag.min(axis=1)
        new_mag = np.where(np.arange(idx.shape[1])[None, :] == arg1[:, None], min2[:, None], min1[:, None])
        c2v = alpha * sign.prod(axis=1, keepdims=True) * sign * new_mag
        c2v[~mask] = 0.0
        posterior = channel + np.bincount(idx[mask], weights=c2v[mask], minlength=len(channel))
    hard_now = (posterior < 0).astype(np.uint8)
    return hard_now, _syndrome_weight(hard_now) == 0, max_iters


def _best_alignment(bits: np.ndarray) -> tuple:
    """Codeword boundary offset (0..N-1) whose first block has the lowest
    parity-check syndrome weight, evaluated for every offset at once."""
    idx, mask = _check_index()
    windows = np.lib.stride_tricks.sliding_window_view(bits.astype(np.int64), N)[:N]
    weights = ((windows[:, idx] * mask).sum(axis=2) % 2).sum(axis=1)
    off = int(np.argmin(weights))
    return off, int(weights[off])


def ldpc_decode(received_bits: np.ndarray, max_blocks: int = 20, llrs: np.ndarray = None) -> dict:
    """Decode a bit stream as consecutive 648-bit codewords. success is True
    only when every decoded block satisfies all 162 parity checks (a random
    stream does so with probability ~2^-162 per block).

    llrs: optional real per-bit LLRs (same length/alignment as received_bits,
    demodulator convention: positive = bit 1) from soft demodulation. When
    given, they drive the decoder directly instead of a fixed-magnitude LLR
    synthesized from the hard bits."""
    bits = np.asarray(received_bits, dtype=np.uint8)
    if len(bits) < N + 1:
        return {"bits": bits, "success": False, "blocks": 0, "converged_blocks": 0, "offset": 0}
    llrs = np.asarray(llrs, dtype=np.float64) if llrs is not None else None
    if llrs is not None and len(llrs) != len(bits):
        llrs = None  # misaligned soft info is worse than none; fall back to hard bits

    offset, _ = _best_alignment(bits[:N * 2])
    info_out, converged, blocks = [], 0, 0
    for i in range(offset, len(bits) - N + 1, N):
        if blocks >= max_blocks:
            break
        block_llr = llrs[i:i + N] if llrs is not None else None
        decoded, ok, _ = _min_sum_decode_block(bits[i:i + N], channel_llr=block_llr)
        info_out.append(decoded[:K])
        converged += int(ok)
        blocks += 1
        if not ok and blocks == 1:
            break   # the first block did not decode: not this code, stop early

    return {
        "bits": np.concatenate(info_out) if info_out else bits,
        "success": blocks > 0 and converged == blocks,
        "blocks": blocks,
        "converged_blocks": converged,
        "offset": offset,
    }
