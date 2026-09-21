"""Turns raw candidate evidence into a normalized [0,1] evidence score.
No hardcoded per-modulation branches -- the same formula runs for every
candidate, driven by measured EVM against each candidate's FIXED reference
constellation/tone grid."""


def score_from_evidence(evidence: dict) -> float:
    evm = evidence.get("evm", 1.0)
    order_match = evidence.get("expected_order") == evidence.get("matched_cluster_order")

    evm_score = max(0.0, 1.0 - min(evm, 1.0))

    # order_match comes from an independent k-means clustering
    # (constellation_features) that is NOT compared against a fixed
    # reference -- unlike evm, it can look deceptively good on ANY data
    # (k-means always finds a locally-optimal partition), so it is kept as
    # a small tie-breaking nudge rather than a primary scoring signal.
    return float(0.9 * evm_score + 0.1 * (1.0 if order_match else 0.0))
