"""Decide whether the evidence supports naming a winner at all."""

DETERMINED = "determined"
AMBIGUOUS = "ambiguous"
INSUFFICIENT = "insufficient_evidence"
USER_SELECTED = "user_selected"


def decide_verdict(hypotheses: list, manual_selection: bool, min_score: float, min_margin: float,
                   timing_fit: float = None, min_timing_fit: float = 0.0) -> tuple:
    """Returns (verdict, reason).

    insufficient_evidence: no symbol clock was found (timing_fit < min_timing_fit;
                           pass timing_fit=None when the analyst supplied the rate), or
                           the best score is below min_score.
    ambiguous:             the best and second-best scores differ by < min_margin.
    user_selected:         the analyst chose the modulation, so nothing was inferred.
    """
    if not hypotheses:
        return INSUFFICIENT, "No candidate could be evaluated."
    best = hypotheses[0]
    if manual_selection:
        return USER_SELECTED, f"Modulation {best.modulation} was selected by the analyst (score {best.score:.2f})."
    if timing_fit is not None and timing_fit < min_timing_fit:
        return INSUFFICIENT, (f"No symbol clock found (timing fit {timing_fit:.2f} < {min_timing_fit:.2f}); "
                              f"the signal shows no periodic symbol structure.")
    if best.score < min_score:
        return INSUFFICIENT, (f"Best score {best.score:.2f} ({best.modulation}) is below the "
                              f"minimum {min_score:.2f}.")
    if len(hypotheses) > 1:
        margin = best.score - hypotheses[1].score
        if margin < min_margin:
            return AMBIGUOUS, (f"{best.modulation} ({best.score:.2f}) and {hypotheses[1].modulation} "
                               f"({hypotheses[1].score:.2f}) differ by only {margin:.2f} (< {min_margin:.2f}).")
    return DETERMINED, f"{best.modulation} is best supported (score {best.score:.2f})."
