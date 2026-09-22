import numpy as np
from scipy.stats import binom

from core.correlation.bit_correlation import bit_cross_correlate

# A handful of well-known frame-sync words to try when the user has no
# specific header pattern in mind.
COMMON_SYNC_WORDS = {
    "CCSDS_ASM": "1010011111100000010101110",  # CCSDS attached sync marker (26 bit approx)
    "HDLC_FLAG": "01111110",
    "BARKER_11": "11100010010",
}

# A match counts as a header only if the chance of seeing one this good
# ANYWHERE in the stream, for ANY of the patterns tried, from random bits is
# below this level.
FALSE_ALARM_LEVEL = 0.01


def _to_bits(pattern_str: str) -> np.ndarray:
    return np.array([int(c) for c in pattern_str], dtype=np.uint8)


def detect_header(bits: np.ndarray, patterns: dict = None, threshold: float = 0.85,
                  false_alarm_level: float = FALSE_ALARM_LEVEL) -> dict:
    """Search the bit stream for the best-correlating known sync pattern, in
    normal or inverted polarity.

    The correlation of a bipolar pattern of length L is c = 1 - 2*d_H/L, so a
    window with m = L*(1+c)/2 matching bits has, for random bits, the
    probability P(Bin(L, 1/2) >= m). Multiplying by the number of windows
    and patterns tried (Bonferroni) gives the false-alarm probability of the
    best match; short patterns in long streams therefore cannot qualify.
    """
    patterns = patterns or COMMON_SYNC_WORDS
    best = {"header_offset": None, "header_pattern": None, "correlation_peak": 0.0,
            "pattern_length": 0, "hamming_similarity": 0.0, "false_alarm_probability": 1.0,
            "polarity": "normal"}
    n_bits = len(bits)
    # both polarities are tried (BPSK/QPSK have a 180-degree phase ambiguity,
    # so a correct stream can arrive inverted), which doubles the trials
    n_trials = max(1, 2 * sum(max(0, n_bits - len(p) + 1) for p in patterns.values()))

    for name, pattern_str in patterns.items():
        pattern = _to_bits(pattern_str)
        scores = bit_cross_correlate(bits, pattern)
        if len(scores) == 0:
            continue
        i_pos, i_neg = int(np.argmax(scores)), int(np.argmin(scores))
        if -scores[i_neg] > scores[i_pos]:
            peak_idx, peak_val, polarity = i_neg, float(-scores[i_neg]), "inverted"
        else:
            peak_idx, peak_val, polarity = i_pos, float(scores[i_pos]), "normal"
        if peak_val > best["correlation_peak"]:
            length = len(pattern)
            matches = int(round(length * (1.0 + peak_val) / 2.0))
            p_single = float(binom.sf(matches - 1, length, 0.5))
            best = {"header_offset": peak_idx, "header_pattern": name, "correlation_peak": peak_val,
                    "pattern_length": length,
                    # c = 1 - 2*d_H/N  =>  similarity = 1 - d_H/N = (1 + c)/2
                    "hamming_similarity": (1.0 + peak_val) / 2.0,
                    "false_alarm_probability": min(1.0, p_single * n_trials),
                    "polarity": polarity}
    if best["correlation_peak"] < threshold or best["false_alarm_probability"] >= false_alarm_level:
        best["header_offset"] = None
        best["header_pattern"] = None
        best["pattern_length"] = 0
    return best
