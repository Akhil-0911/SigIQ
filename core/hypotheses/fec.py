"""FEC candidate list -- what the pipeline will try during recovery."""
FEC_CANDIDATES = ["convolutional_viterbi", "reed_solomon", "concatenated", "ldpc", "none"]


def build_fec_candidates(enabled_types: list = None) -> list:
    if not enabled_types:
        return FEC_CANDIDATES
    return [c for c in FEC_CANDIDATES if c in enabled_types or c == "none"]
