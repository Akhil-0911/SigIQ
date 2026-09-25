"""De-interleaving candidate list."""
INTERLEAVING_CANDIDATES = ["block", "convolutional", "diagonal", "pseudo_random", "none"]


def build_interleaving_candidates(enabled_types: list = None) -> list:
    if not enabled_types:
        return INTERLEAVING_CANDIDATES
    return [c for c in INTERLEAVING_CANDIDATES if c in enabled_types or c == "none"]
