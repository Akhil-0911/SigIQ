"""Per-candidate evidence metrics and the composite score.

Every candidate is judged by the same formula, so there are no per-modulation
branches. Each metric lies in [0, 1] and is kept separately in the result.

    constellation_fit  = 1 - min(EVM, 1). EVM is the RMS distance of the
                         demodulated symbols from the candidate's FIXED ideal
                         constellation / tone grid, divided by that grid's
                         minimum point spacing (so dense grids get no
                         advantage). This is the discriminating metric.
    order_consistency  = 1 if an independent k-means clustering of the symbols
                         finds the candidate's order, else 0. K-means can
                         partition any data, so this is only a tie-breaker.
    timing_fit         = strength of the symbol-clock spectral line above the
                         noise expectation (see timing_fit_from_prominence).
                         It is measured once per pass and is the same for
                         every candidate, so it scales scores but cannot change
                         the ranking.

Weights (constellation 0.8, order 0.1, timing 0.1) sum to 1. They were chosen
so the constellation fit dominates, and validated with
tests/test_accuracy_report.py, which must not regress when they change.
"""

WEIGHTS = {"constellation_fit": 0.8, "order_consistency": 0.1, "timing_fit": 0.1}


def metrics_from_evidence(evidence: dict) -> dict:
    evm = evidence.get("evm", 1.0)
    order_match = evidence.get("expected_order") == evidence.get("matched_cluster_order")
    return {
        "constellation_fit": max(0.0, 1.0 - min(evm, 1.0)),
        "order_consistency": 1.0 if order_match else 0.0,
        "timing_fit": float(evidence.get("timing_fit", 0.0)),
    }


def score_from_metrics(metrics: dict) -> float:
    return float(sum(WEIGHTS[name] * metrics[name] for name in WEIGHTS))
