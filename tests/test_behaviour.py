"""Behavioural checks for the parts of the pipeline that exist to keep results
honest: provenance, verdicts, the re-estimation search, header significance,
recovery evidence and payload output."""
from types import SimpleNamespace

import numpy as np

from sigiq.core.pipeline.models import RawSignal
from sigiq.core.pipeline.pipeline_config import PipelineConfig
from sigiq.core.pipeline.analyzer import run_pipeline, _search_recovery
from sigiq.core.pipeline.reestimation import SearchPoint, coordinate_search
from sigiq.core.scoring.verdict import decide_verdict, DETERMINED, AMBIGUOUS, INSUFFICIENT, USER_SELECTED
from sigiq.core.correlation.header_detection import detect_header, COMMON_SYNC_WORDS
from sigiq.core.correlation.payload_detection import bits_to_hex, bits_to_bytes

from tests.test_accuracy_report import make_signal, _deterministic_seed

FS = 48000.0


def _raw(modulation, snr_db):
    x, _, _ = make_signal(modulation, snr_db=snr_db, seed=_deterministic_seed(modulation, snr_db))
    return RawSignal(samples=x, sample_rate=FS, source_format="iq", filename=f"{modulation}.iq")


def _no_recovery_config(**analysis):
    return PipelineConfig.from_dict({"analysis": analysis,
                                     "deinterleaving": {"enabled": False}, "fec": {"enabled": False}})


# ------------------------------------------------------------------ verdicts
def _hyp(name, score):
    return SimpleNamespace(modulation=name, score=score)


def test_verdicts():
    assert decide_verdict([_hyp("BPSK", 0.9), _hyp("QPSK", 0.5)], False, 0.3, 0.05)[0] == DETERMINED
    assert decide_verdict([_hyp("BPSK", 0.9), _hyp("QPSK", 0.88)], False, 0.3, 0.05)[0] == AMBIGUOUS
    assert decide_verdict([_hyp("BPSK", 0.2)], False, 0.3, 0.05)[0] == INSUFFICIENT
    assert decide_verdict([_hyp("BPSK", 0.2)], True, 0.3, 0.05)[0] == USER_SELECTED
    assert decide_verdict([], False, 0.3, 0.05)[0] == INSUFFICIENT


# ------------------------------------------------------------------ search
def test_search_stops_on_tolerance_and_limit():
    def evaluate(pt):
        return -abs(pt.symbol_rate - 6000.0) / 6000.0, {"prom": 1.0}

    def neighbours(pt):
        return [SearchPoint(pt.symbol_rate + d) for d in (-500.0, 500.0)]

    best, score, _, trace = coordinate_search(SearchPoint(4000.0), evaluate, neighbours,
                                              tolerance=0.001, max_iterations=10)
    assert abs(best.symbol_rate - 6000.0) <= 500.0 and score > -0.09
    assert len(trace) < 10, "must stop once no neighbour improves by the tolerance"
    assert trace[-1]["accepted"] is False

    _, _, _, capped = coordinate_search(SearchPoint(1000.0), evaluate, neighbours,
                                        tolerance=0.001, max_iterations=2)
    assert len(capped) == 2, "must stop at max_iterations"


def test_tie_prefers_higher_rate_only_with_clock_support():
    def evaluate(pt):
        return 0.5, {"prom": 10.0 if pt.symbol_rate == 6000.0 else 1.0}

    def neighbours(pt):
        return [SearchPoint(6000.0)] if pt.symbol_rate == 3000.0 else [SearchPoint(12000.0)]

    supported, _, _, _ = coordinate_search(SearchPoint(3000.0), evaluate, neighbours, 0.005, 3,
                                           tie_support=lambda pl: pl["prom"])
    assert supported.symbol_rate == 6000.0, "tie moves to the higher rate when its clock line is stronger"
    refused, _, _, _ = coordinate_search(SearchPoint(6000.0), evaluate, neighbours, 0.005, 3,
                                         tie_support=lambda pl: pl["prom"])
    assert refused.symbol_rate == 6000.0, "a harmonic with a weaker clock line must be refused"


def test_search_recovers_half_rate_clock():
    result = run_pipeline(_raw("2-FSK", 5.0), _no_recovery_config())
    assert abs(result.estimate.symbol_rate - 6000.0) / 6000.0 < 0.02
    assert any(t["iteration"] > 0 for t in result.reestimation), "the search must actually have run"


# ---------------------------------------------------------- manual / provenance
def test_manual_choices_are_labelled_user_provided():
    cfg = PipelineConfig.from_dict({
        "analysis": {"mode": "manual"},
        "manual": {"modulation": "BPSK", "symbol_rate": 6000.0},
        "deinterleaving": {"enabled": False}, "fec": {"enabled": False}})
    result = run_pipeline(_raw("BPSK", 15.0), cfg)
    assert result.provenance["symbol_rate"] == "user-provided"
    assert result.provenance["modulation"] == "user-provided"
    assert result.provenance["sample_rate"] == "user-provided"      # .iq has no header
    assert result.verdict == "user_selected"
    assert result.estimate.symbol_rate == 6000.0, "the analyst's symbol rate must be used, not re-estimated"


def test_automatic_results_are_labelled_inferred():
    result = run_pipeline(_raw("BPSK", 25.0), _no_recovery_config())
    assert result.provenance["symbol_rate"] == "estimated"
    assert result.provenance["modulation"].startswith("candidate-inferred")
    assert result.best_hypothesis.modulation == "BPSK"
    for h in result.hypotheses:
        assert set(h.metrics) == {"constellation_fit", "order_consistency", "timing_fit"}
        assert all(0.0 <= v <= 1.0 for v in h.metrics.values())


# ------------------------------------------------------------ header / payload
def test_header_needs_statistical_significance():
    rng = np.random.default_rng(3)
    random_bits = rng.integers(0, 2, 6000).astype(np.uint8)
    assert detect_header(random_bits)["header_offset"] is None, "chance matches must not count as a header"

    sync = np.array([int(c) for c in COMMON_SYNC_WORDS["CCSDS_ASM"]], dtype=np.uint8)
    stream = random_bits.copy()
    stream[100:100 + len(sync)] = sync
    found = detect_header(stream)
    assert found["header_offset"] == 100 and found["header_pattern"] == "CCSDS_ASM"
    assert found["false_alarm_probability"] < 0.01
    assert found["hamming_similarity"] == 1.0 and found["pattern_length"] == len(sync)


def test_bits_to_hex_and_bytes():
    bits = np.array([0, 1, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], dtype=np.uint8)  # 'A', 0xFF, 1 spare bit
    assert bits_to_bytes(bits) == b"A\xff"
    assert bits_to_hex(bits) == "41 ff"


# ------------------------------------------------------------------- recovery
def test_recovery_reports_undetermined_without_evidence():
    rng = np.random.default_rng(11)
    bits = rng.integers(0, 2, 2000).astype(np.uint8)
    recovered = _search_recovery(bits, PipelineConfig())
    assert recovered.confirmed is False
    assert recovered.deinterleave_method == "undetermined" and recovered.fec_method == "undetermined"
    assert np.array_equal(recovered.bits, bits), "with no evidence the bits must be returned unchanged"


def test_ldpc_encoded_stream_is_recovered_through_the_pipeline_stage():
    from sigiq.core.fec.ldpc import ldpc_encode, K
    rng = np.random.default_rng(2)
    info = rng.integers(0, 2, K * 2).astype(np.uint8)
    coded = ldpc_encode(info)
    cfg = PipelineConfig(deinterleaving_enabled=False, fec_types=["ldpc"])
    recovered = _search_recovery(coded, cfg)
    assert recovered.fec_method == "ldpc" and recovered.confirmed and recovered.fec_success
    assert np.array_equal(recovered.bits[:len(info)], info)


def test_deinterleavers_invert_their_interleavers():
    from sigiq.core.deinterleaving.block import interleave_block, deinterleave_block
    from sigiq.core.deinterleaving.diagonal import interleave_diagonal, deinterleave_diagonal
    from sigiq.core.deinterleaving.convolutional import interleave_convolutional, deinterleave_convolutional
    from sigiq.core.deinterleaving.pseudo_random import interleave_pseudo_random, deinterleave_pseudo_random
    rng = np.random.default_rng(6)
    bits = rng.integers(0, 2, 12 * 20).astype(np.uint8)

    assert np.array_equal(deinterleave_block(interleave_block(bits, 12, 20), 12, 20), bits)
    assert np.array_equal(deinterleave_diagonal(interleave_diagonal(bits, 12, 20), 12, 20), bits)
    assert np.array_equal(deinterleave_pseudo_random(interleave_pseudo_random(bits, 7), 7), bits)
    assert not np.array_equal(interleave_pseudo_random(bits, 7), bits), "interleaving must actually permute"

    # the convolutional pair has a fixed end-to-end delay of (branches-1)*branches*delay_step bits
    n_branches, step = 4, 4
    delay = (n_branches - 1) * n_branches * step
    long_bits = rng.integers(0, 2, 400).astype(np.uint8)
    round_trip = deinterleave_convolutional(interleave_convolutional(long_bits, n_branches, step), n_branches, step)
    assert np.array_equal(round_trip[delay:], long_bits[:len(long_bits) - delay])


def _framed_coded_signal(interleave, snr_db, seed=4):
    """BPSK carrying: random bits + CCSDS sync word + payload, rate-1/2 convolutionally
    coded and optionally pseudo-randomly interleaved."""
    from sigiq.core.fec.convolutional import convolutional_encode
    from sigiq.core.deinterleaving.pseudo_random import interleave_pseudo_random
    rng = np.random.default_rng(seed)
    sync = np.array([int(c) for c in COMMON_SYNC_WORDS["CCSDS_ASM"]], dtype=np.uint8)
    payload = rng.integers(0, 2, 160).astype(np.uint8)
    info = np.concatenate([rng.integers(0, 2, 40).astype(np.uint8), sync, payload])
    tx = np.asarray(convolutional_encode(info), dtype=np.uint8)
    if interleave:
        tx = interleave_pseudo_random(tx, 42)
    symbols = np.repeat(2.0 * tx - 1.0, 8).astype(np.complex128)
    noise = np.sqrt(0.5 * 10 ** (-snr_db / 10)) * (rng.standard_normal(len(symbols)) + 1j * rng.standard_normal(len(symbols)))
    return RawSignal(samples=symbols + noise, sample_rate=FS, source_format="iq", filename="e2e.iq"), payload


def test_end_to_end_recovery_of_coded_framed_signal():
    """Raw IQ -> BPSK identified -> interleaver and FEC inferred -> sync word found -> payload
    recovered exactly. Nothing about the coding is given to the pipeline."""
    for interleave, expected_deinterleaver in ((False, "none"), (True, "pseudo_random")):
        raw, payload = _framed_coded_signal(interleave, snr_db=12.0)
        result = run_pipeline(raw, PipelineConfig())
        assert result.best_hypothesis.modulation == "BPSK"
        assert result.recovered.deinterleave_method == expected_deinterleaver
        assert result.recovered.fec_method == "convolutional_viterbi" and result.recovered.fec_success
        assert result.recovered.confirmed
        assert result.bitstream.header_pattern == "CCSDS_ASM"
        assert np.array_equal(result.bitstream.payload_bits[:100], payload[:100])
        assert result.provenance["fec"] == "candidate-tested"


def test_inverted_polarity_is_detected_and_corrected():
    sync = np.array([int(c) for c in COMMON_SYNC_WORDS["CCSDS_ASM"]], dtype=np.uint8)
    rng = np.random.default_rng(8)
    stream = rng.integers(0, 2, 500).astype(np.uint8)
    stream[60:60 + len(sync)] = 1 - sync                       # complemented sync word
    found = detect_header(stream)
    assert found["header_offset"] == 60 and found["polarity"] == "inverted"


def test_pure_noise_is_not_classified():
    rng = np.random.default_rng(3)
    noise = rng.standard_normal(4000) + 1j * rng.standard_normal(4000)
    raw = RawSignal(samples=noise, sample_rate=FS, source_format="iq", filename="noise.iq")
    result = run_pipeline(raw, PipelineConfig())
    assert result.verdict == INSUFFICIENT, result.verdict_reason
    assert result.recovered is None and result.bitstream is None, "nothing to recover from noise"
    assert result.provenance["modulation"].startswith("not determined")


def test_coded_streams_are_verified_and_noise_is_not():
    from sigiq.core.fec.convolutional import convolutional_encode
    from sigiq.core.fec.reed_solomon import rs_encode
    from sigiq.core.pipeline.analyzer import _apply_fec_decode
    rng = np.random.default_rng(5)
    info = rng.integers(0, 2, 400).astype(np.uint8)

    coded = np.asarray(convolutional_encode(info), dtype=np.uint8)
    noisy = coded.copy()
    noisy[rng.choice(len(noisy), size=int(0.01 * len(noisy)), replace=False)] ^= 1
    assert _apply_fec_decode(noisy, "convolutional_viterbi")["success"] is True

    rs = rs_encode(info)
    assert _apply_fec_decode(rs, "reed_solomon")["success"] is True

    junk = rng.integers(0, 2, 800).astype(np.uint8)
    assert not _apply_fec_decode(junk, "convolutional_viterbi")["success"]
    assert not _apply_fec_decode(junk, "reed_solomon")["success"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok  ", name)
