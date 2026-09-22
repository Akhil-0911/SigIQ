import numpy as np

from core.fec.convolutional import POLY_G1, POLY_G2, CONSTRAINT_LENGTH, _parity


def _build_trellis(poly1: int, poly2: int, constraint_length: int) -> dict:
    n_states = 1 << (constraint_length - 1)
    next_state = np.zeros((n_states, 2), dtype=int)
    output = np.zeros((n_states, 2, 2), dtype=np.uint8)
    for state in range(n_states):
        for bit in (0, 1):
            shift_reg = ((state << 1) | bit) & ((1 << constraint_length) - 1)
            g1 = _parity(shift_reg & poly1)
            g2 = _parity(shift_reg & poly2)
            ns = shift_reg & (n_states - 1)
            next_state[state, bit] = ns
            output[state, bit] = [g1, g2]
    return {"n_states": n_states, "next_state": next_state, "output": output}


def viterbi_decode(received_bits: np.ndarray, poly1: int = POLY_G1, poly2: int = POLY_G2,
                    constraint_length: int = CONSTRAINT_LENGTH) -> dict:
    """Hard-decision Viterbi decoder for the rate-1/2 convolutional code.
    Returns decoded bits plus a success/quality estimate (avg. Hamming
    distance per received pair on the winning path -- lower is better)."""
    trellis = _build_trellis(poly1, poly2, constraint_length)
    n_states = trellis["n_states"]
    next_state = trellis["next_state"]
    output = trellis["output"]

    n_pairs = len(received_bits) // 2
    if n_pairs == 0:
        return {"bits": np.array([], dtype=np.uint8), "avg_hamming": 1.0}
    rx = received_bits[: n_pairs * 2].reshape(n_pairs, 2)

    INF = float("inf")
    decoded = np.zeros(n_pairs, dtype=np.uint8)
    survivors = np.zeros((n_pairs, n_states), dtype=np.int8)  # which input bit (0/1) was chosen
    predecessors = np.zeros((n_pairs, n_states), dtype=int)
    metric = np.full(n_states, INF)
    metric[0] = 0
    for t in range(n_pairs):
        new_metric = np.full(n_states, INF)
        pred = np.full(n_states, 0, dtype=int)
        bitc = np.zeros(n_states, dtype=np.int8)
        for state in range(n_states):
            if metric[state] == INF:
                continue
            for bit in (0, 1):
                ns = next_state[state, bit]
                expected = output[state, bit]
                bm = int(expected[0] != rx[t, 0]) + int(expected[1] != rx[t, 1])
                cost = metric[state] + bm
                if cost < new_metric[ns]:
                    new_metric[ns] = cost
                    pred[ns] = state
                    bitc[ns] = bit
        predecessors[t] = pred
        survivors[t] = bitc
        metric = new_metric

    state = int(np.argmin(metric))
    total_cost = metric[state]
    for t in range(n_pairs - 1, -1, -1):
        decoded[t] = survivors[t, state]
        state = predecessors[t, state]

    avg_hamming = float(total_cost) / (2 * n_pairs)
    return {"bits": decoded, "avg_hamming": avg_hamming}


def viterbi_decode_soft(llrs: np.ndarray, poly1: int = POLY_G1, poly2: int = POLY_G2,
                        constraint_length: int = CONSTRAINT_LENGTH) -> dict:
    """Soft-decision Viterbi: the branch metric uses each coded bit's real LLR
    magnitude (confidence), not just its hard 0/1 sign, so a low-confidence
    disagreement costs less than a confident one.

    LLR convention: positive = evidence for bit 1 (matches the demodulators).
    Branch cost for an expected coded bit e is `L*(1-2*e)` -- e=1 rewards a
    large positive L (cost very negative), e=0 rewards a large negative L --
    so the minimum-cost path is the maximum-likelihood one. `avg_hamming` is
    reported against the LLRs' own hard decision so `viterbi_is_significant`
    (calibrated on hard-decision Hamming distance) still applies unchanged.
    """
    trellis = _build_trellis(poly1, poly2, constraint_length)
    n_states = trellis["n_states"]
    next_state = trellis["next_state"]
    output = trellis["output"]

    n_pairs = len(llrs) // 2
    if n_pairs == 0:
        return {"bits": np.array([], dtype=np.uint8), "avg_hamming": 1.0}
    rx = np.asarray(llrs, dtype=np.float64)[: n_pairs * 2].reshape(n_pairs, 2)

    INF = float("inf")
    decoded = np.zeros(n_pairs, dtype=np.uint8)
    survivors = np.zeros((n_pairs, n_states), dtype=np.int8)
    predecessors = np.zeros((n_pairs, n_states), dtype=int)
    metric = np.full(n_states, INF)
    metric[0] = 0
    for t in range(n_pairs):
        new_metric = np.full(n_states, INF)
        pred = np.full(n_states, 0, dtype=int)
        bitc = np.zeros(n_states, dtype=np.int8)
        for state in range(n_states):
            if metric[state] == INF:
                continue
            for bit in (0, 1):
                ns = next_state[state, bit]
                expected = output[state, bit]
                bm = float(np.sum(rx[t] * (1 - 2 * expected.astype(np.float64))))
                cost = metric[state] + bm
                if cost < new_metric[ns]:
                    new_metric[ns] = cost
                    pred[ns] = state
                    bitc[ns] = bit
        predecessors[t] = pred
        survivors[t] = bitc
        metric = new_metric

    state = int(np.argmin(metric))
    for t in range(n_pairs - 1, -1, -1):
        decoded[t] = survivors[t, state]
        state = predecessors[t, state]

    hard_rx = (rx > 0).astype(np.uint8)  # LLR>0 -> bit 1, matching the coded-bit 0/1 convention
    re_encoded = np.zeros_like(hard_rx)
    state = 0
    for t in range(n_pairs):
        bit = decoded[t]
        re_encoded[t] = output[state, bit]
        state = next_state[state, bit]
    avg_hamming = float(np.sum(re_encoded != hard_rx)) / (2 * n_pairs)
    return {"bits": decoded, "avg_hamming": avg_hamming}


_null_cache = {}


def viterbi_is_significant(avg_hamming: float, n_bits: int, z: float = 4.0) -> bool:
    """Whether a Viterbi decode fits the data better than chance.

    The best trellis path fits ANY bit stream to a nonzero mismatch (about 0.12
    mismatching bits per pair for this code on random data), so a small
    fixed threshold is not evidence. The chance level for this stream length
    is measured on a seeded random stream, and the decode counts only if its
    mismatch is more than z binomial standard deviations below it.
    """
    n_pairs = n_bits // 2
    if n_pairs < 20:
        return False
    if n_pairs not in _null_cache:
        rng = np.random.default_rng(0)
        _null_cache[n_pairs] = viterbi_decode(rng.integers(0, 2, n_pairs * 2).astype(np.uint8))["avg_hamming"]
    null = _null_cache[n_pairs]
    q = min(max(null / 2.0, 1e-6), 1 - 1e-6)                 # per-bit mismatch rate on random data
    sigma_pair = 2.0 * np.sqrt(q * (1 - q) / (2 * n_pairs))   # std of the per-pair average
    return bool(avg_hamming < null - z * sigma_pair)
