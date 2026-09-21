"""Concatenated coding: outer Reed-Solomon + inner convolutional (Viterbi),
the classic deep-space/satellite combination -- decode inner first, then outer."""
from core.fec.viterbi import viterbi_decode
from core.fec.reed_solomon import rs_decode


def concatenated_decode(received_bits, poly1=None, poly2=None, nsym: int = 10) -> dict:
    kwargs = {}
    if poly1 is not None:
        kwargs["poly1"] = poly1
    if poly2 is not None:
        kwargs["poly2"] = poly2
    inner = viterbi_decode(received_bits, **kwargs)
    outer = rs_decode(inner["bits"], nsym=nsym)
    return {
        "bits": outer["bits"],
        "success": outer["success"],
        "inner_avg_hamming": inner["avg_hamming"],
        "outer_errors_corrected": outer.get("errors_corrected"),
    }
