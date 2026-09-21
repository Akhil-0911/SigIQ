import numpy as np

from core.correlation.bit_correlation import bit_cross_correlate

# A handful of well-known frame-sync words to try when the user has no
# specific header pattern in mind.
COMMON_SYNC_WORDS = {
    "CCSDS_ASM": "1010011111100000010101110",  # CCSDS attached sync marker (26 bit approx)
    "HDLC_FLAG": "01111110",
    "BARKER_11": "11100010010",
}


def _to_bits(pattern_str: str) -> np.ndarray:
    return np.array([int(c) for c in pattern_str], dtype=np.uint8)


def detect_header(bits: np.ndarray, patterns: dict = None, threshold: float = 0.85) -> dict:
    """Search the bit stream for the best-correlating known sync pattern."""
    patterns = patterns or COMMON_SYNC_WORDS
    best = {"header_offset": None, "header_pattern": None, "correlation_peak": 0.0}
    for name, pattern_str in patterns.items():
        pattern = _to_bits(pattern_str)
        scores = bit_cross_correlate(bits, pattern)
        if len(scores) == 0:
            continue
        peak_idx = int(np.argmax(scores))
        peak_val = float(scores[peak_idx])
        if peak_val > best["correlation_peak"]:
            best = {"header_offset": peak_idx, "header_pattern": name, "correlation_peak": peak_val}
    if best["correlation_peak"] < threshold:
        best["header_offset"] = None
        best["header_pattern"] = None
    return best
