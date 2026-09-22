"""Parameter re-estimation: a bounded coordinate search.

theta = (symbol rate, carrier offset, low-pass cutoff). The objective is the
best candidate's evidence score S(H, theta). Starting from the initial
estimate, each iteration evaluates every single-coordinate neighbour of the
current point and moves to the best one if it improves the objective by more
than `tolerance`. The search stops when no neighbour improves by that much or
after `max_iterations`.

Symbol-rate neighbours respect the integer samples-per-symbol timing recovery:
sps +/- 1, and the harmonic alternatives Rs/2 and 2*Rs (a cyclic-spectrum line
can lock onto a harmonic of the true clock).

Tie-break: demodulating at a sub-harmonic of the true clock keeps only every
k-th symbol and scores about as well as the true rate, so when a higher-rate
neighbour scores within `tolerance` of the current point (not worse by more),
the higher rate is preferred -- it recovers more of the transmitted symbols --
provided its clock line is MEANINGFULLY more prominent (HARMONIC_TIE_MARGIN),
not just numerically >=. For an unshaped (rectangular-pulse) signal, sampling
at an exact integer multiple of the true rate reproduces each real symbol
several times in a row, which EVM cannot tell apart from the true rate at
all -- and the cyclic-spectrum line at that multiple can end up marginally
stronger than the true line from measurement noise alone (observed on a real
capture: 2x line 103.7 vs true line 103.4, a ~0.3% gap). Requiring a real
margin avoids jumping to a harmonic on noise-level differences while still
correcting genuine sub-harmonic locks, where the gap is large (observed: a
half-rate lock's own line at 4.2 vs the true rate's line at 2.5 -- the true
rate wins there on SCORE, before this tie-break path is even reached).
"""
from dataclasses import dataclass, replace
from typing import Callable, Optional

HARMONIC_TIE_MARGIN = 0.10  # a higher-rate tie candidate must beat the current point's clock-line support by this fraction


@dataclass(frozen=True)
class SearchPoint:
    symbol_rate: float
    carrier_offset: float = 0.0
    lowpass_hz: Optional[float] = None


def neighbours(point: SearchPoint, sample_rate: float, offset_estimate: float,
               rate_locked: bool = False) -> list:
    out = []
    if not rate_locked and point.symbol_rate > 0:
        base_sps = int(round(sample_rate / point.symbol_rate))
        rates = {sample_rate / s for s in (base_sps - 1, base_sps + 1) if s >= 2}
        for r in (point.symbol_rate / 2.0, point.symbol_rate * 2.0):
            if sample_rate / r >= 2.0:
                rates.add(r)
        out += [replace(point, symbol_rate=r) for r in sorted(rates)
                if abs(r - point.symbol_rate) > 1e-9]
    if abs(point.carrier_offset - offset_estimate) > 1e-9:
        out.append(replace(point, carrier_offset=offset_estimate))
    for k in (1.0, 1.5):
        cutoff = k * point.symbol_rate
        if point.lowpass_hz != cutoff and cutoff < sample_rate / 2.0:
            out.append(replace(point, lowpass_hz=cutoff))
    return out


def coordinate_search(start: SearchPoint, evaluate: Callable, neighbours_fn: Callable,
                      tolerance: float, max_iterations: int, on_iteration: Callable = None,
                      tie_support: Callable = None) -> tuple:
    """evaluate(point) -> (score, payload). Returns (point, score, payload, trace).

    tie_support(payload) -> float: evidence that the point's symbol rate is the
    real clock (line prominence). A higher-rate tie is only taken when its support
    is at least the current point's, so a harmonic above the true clock is refused.
    """
    cache = {}

    def ev(pt):
        if pt not in cache:
            cache[pt] = evaluate(pt)
        return cache[pt]

    current = start
    score, payload = ev(current)
    trace = []
    for iteration in range(1, max_iterations + 1):
        candidates = [(ev(p)[0], p) for p in neighbours_fn(current)]
        if not candidates:
            trace.append({"iteration": iteration, "point": current, "score": score, "accepted": False,
                          "note": "no neighbours"})
            break
        best_score, best_point = max(candidates, key=lambda c: c[0])
        note = f"best neighbour {best_score:.3f} vs current {score:.3f}"
        improved = best_score - score > tolerance
        if not improved:
            def supported(p):
                return tie_support is None or tie_support(ev(p)[1]) >= tie_support(payload) * (1 + HARMONIC_TIE_MARGIN)

            higher = [(s, p) for s, p in candidates
                      if p.symbol_rate > current.symbol_rate * (1 + 1e-9) and s >= score - tolerance
                      and supported(p)]
            if higher:
                best_score, best_point = max(higher, key=lambda c: c[0])
                improved = True
                note = f"tie -> higher symbol rate {best_point.symbol_rate:.1f} Hz ({best_score:.3f} vs {score:.3f})"
        trace.append({"iteration": iteration, "point": best_point if improved else current,
                      "score": best_score if improved else score, "accepted": improved, "note": note})
        if on_iteration:
            on_iteration(iteration, best_point if improved else current, best_score if improved else score, improved)
        if not improved:
            break
        current, (score, payload) = best_point, cache[best_point]
    return current, score, payload, trace
