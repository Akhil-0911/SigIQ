def confidence_from_scores(scores: list) -> list:
    """Convert raw candidate scores into relative confidence percentages
    (softmax-like normalization so the best candidate's confidence reflects
    how much it beat the runner-up, not an absolute claim)."""
    if not scores:
        return []
    total = sum(scores) or 1e-9
    return [round(100 * s / total, 1) for s in scores]
