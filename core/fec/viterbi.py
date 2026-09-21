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
