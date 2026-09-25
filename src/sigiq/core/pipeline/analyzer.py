"""Central orchestrator: RawSignal -> AnalysisResult.

This module has no UI knowledge -- it is directly unit-testable and runnable
from a plain Python script (see tests/test_pipeline_smoke.py). UIs call
`run_pipeline()` and receive progress through its callback.

Flow: preprocessing -> isolation -> features -> parameter estimation ->
candidate generation -> candidate-specific processing + evidence scoring ->
(re-estimation search if weak/ambiguous) -> best-supported hypothesis ->
verdict -> joint de-interleaving x FEC search -> known sync-word matching ->
header/payload -> recovered information.
"""
from dataclasses import dataclass

import numpy as np

from sigiq.core.pipeline.models import (
    SignalFeatures, ParameterEstimate, AnalysisResult, RecoveredSignal, BitstreamResult, IsolationInfo,
)
from sigiq.core.pipeline.pipeline_config import PipelineConfig
from sigiq.core.pipeline.stages import Stage, STAGE_PROGRESS
from sigiq.core.pipeline.reestimation import SearchPoint, neighbours, coordinate_search

from sigiq.core.preprocessing.profiles import PREPROCESSING_PROFILES, apply_profile
from sigiq.core.preprocessing.frequency_translation import frequency_translate, lowpass
from sigiq.core.isolation.signal_segmentation import segment_by_energy
from sigiq.core.isolation.channel_detection import strongest_channel
from sigiq.core.isolation.spectrum import power_spectrum, waterfall

from sigiq.core.feature_extraction.spectral_features import extract_spectral_features
from sigiq.core.feature_extraction.temporal_features import extract_temporal_features
from sigiq.core.feature_extraction.signal_statistics import extract_signal_statistics

from sigiq.core.estimation.sample_rate import estimate_sample_rate
from sigiq.core.estimation.symbol_rate import estimate_symbol_rate, timing_fit_at, timing_prominence_at
from sigiq.core.estimation.carrier_frequency import estimate_carrier_offset
from sigiq.core.estimation.snr import estimate_snr

from sigiq.core.hypotheses.generator import generate_hypothesis_space
from sigiq.core.scoring.hypothesis_scorer import score_candidates
from sigiq.core.scoring.verdict import decide_verdict, INSUFFICIENT, AMBIGUOUS

from sigiq.core.deinterleaving.block import deinterleave_block
from sigiq.core.deinterleaving.convolutional import deinterleave_convolutional
from sigiq.core.deinterleaving.diagonal import deinterleave_diagonal
from sigiq.core.deinterleaving.pseudo_random import deinterleave_pseudo_random

from sigiq.core.fec.viterbi import viterbi_decode, viterbi_decode_soft, viterbi_is_significant
from sigiq.core.fec.reed_solomon import rs_decode
from sigiq.core.fec.concatenated import concatenated_decode
from sigiq.core.fec.ldpc import ldpc_decode

from sigiq.core.correlation.header_detection import detect_header
from sigiq.core.correlation.payload_detection import extract_payload

from sigiq.core.preprocessing.resampling import decimate_for_visualization

MAX_RECOVERY_BITS = 6000  # keep the brute-force interleaving x FEC search tractable


def _noop_progress(stage, percent, message):
    pass


# ----------------------------------------------------------------- recovery
def _apply_deinterleave(bits: np.ndarray, method: str, params: dict = None, llr: np.ndarray = None) -> dict:
    """Returns {"bits": ..., "llr": ..., "params": {...}} -- params are the
    ones actually used (defaults filled in), so the analyst can see what was
    applied, not just which method name won. `llr` (if given) is carried
    through the same permutation as the bits, since de-interleaving is just a
    fixed reordering: soft information about a bit stays attached to it."""
    params = params or {}
    n = len(bits)
    has_llr = llr is not None and len(llr) == n

    def both(fn, *args):
        out_bits = fn(bits, *args)
        out_llr = fn(llr, *args) if has_llr else None
        return out_bits, out_llr

    if method == "none":
        return {"bits": bits, "llr": llr if has_llr else None, "params": {}}
    if method == "block":
        cols = params.get("cols") or max(2, int(np.sqrt(n)))
        rows = n // cols or 1
        out_bits, out_llr = both(deinterleave_block, rows, cols)
        return {"bits": out_bits, "llr": out_llr, "params": {"rows": rows, "cols": cols}}
    if method == "diagonal":
        cols = params.get("cols") or max(2, int(np.sqrt(n)))
        rows = n // cols or 1
        out_bits, out_llr = both(deinterleave_diagonal, rows, cols)
        return {"bits": out_bits, "llr": out_llr, "params": {"rows": rows, "cols": cols}}
    if method == "convolutional":
        branches, delay = params.get("num_branches", 4), params.get("delay_step", 4)
        out_bits, out_llr = both(deinterleave_convolutional, branches, delay)
        return {"bits": out_bits, "llr": out_llr, "params": {"num_branches": branches, "delay_step": delay}}
    if method == "pseudo_random":
        seed = params.get("seed", 42)
        out_bits, out_llr = both(deinterleave_pseudo_random, seed)
        return {"bits": out_bits, "llr": out_llr, "params": {"seed": seed}}
    raise ValueError(f"Unknown de-interleaving method '{method}'")


def _apply_fec_decode(bits: np.ndarray, method: str, llr: np.ndarray = None) -> dict:
    has_llr = llr is not None and len(llr) == len(bits)
    if method == "none":
        return {"bits": bits, "success": None, "quality": None, "llr_used": False}
    if method == "convolutional_viterbi":
        result = viterbi_decode_soft(llr) if has_llr else viterbi_decode(bits)
        return {"bits": result["bits"], "success": viterbi_is_significant(result["avg_hamming"], len(bits)),
                "quality": f"Hamming {result['avg_hamming']:.3f}", "llr_used": has_llr}
    if method == "reed_solomon":
        result = rs_decode(bits)
        quality = (f"{result['errors_corrected']} errors fixed" if result["success"]
                   else result.get("error", "decode failed"))
        return {"bits": result["bits"], "success": result["success"], "quality": quality, "llr_used": False}
    if method == "concatenated":
        result = concatenated_decode(bits, llrs=llr if has_llr else None)
        quality = (f"in {result['inner_avg_hamming']:.2f}, "
                   f"out {result['outer_errors_corrected']} fixed")
        return {"bits": result["bits"], "success": result["success"], "quality": quality, "llr_used": has_llr}
    if method == "ldpc":
        result = ldpc_decode(bits, llrs=llr if has_llr else None)
        quality = f"{result['converged_blocks']}/{result['blocks']} blocks ok"
        return {"bits": result["bits"], "success": result["success"], "quality": quality, "llr_used": has_llr}
    raise ValueError(f"Unknown FEC method '{method}'")


def _search_recovery(demod_bits: np.ndarray, config: PipelineConfig, demod_llr: np.ndarray = None) -> RecoveredSignal:
    """Try de-interleaver x FEC combinations and keep the one with the best
    evidence (header correlation + FEC success). A dimension the analyst
    specified in manual mode is fixed; the other is still searched.

    If no combination shows real evidence (an FEC decode that verifies, or a
    statistically significant known sync word), the automatic result is
    reported as 'undetermined' with the demodulated bits unchanged, rather
    than naming a de-interleaver/FEC that nothing supports.

    demod_llr: per-bit soft information from demodulation, same length/order
    as demod_bits when present. FEC decoders that support it (Viterbi, LDPC,
    the Viterbi stage of the concatenated code) use it instead of hard bits."""
    bits = demod_bits[:MAX_RECOVERY_BITS] if len(demod_bits) > MAX_RECOVERY_BITS else demod_bits
    llr = None
    if demod_llr is not None and len(demod_llr) == len(demod_bits):
        llr = demod_llr[:MAX_RECOVERY_BITS] if len(demod_llr) > MAX_RECOVERY_BITS else demod_llr
    manual = config.mode == "manual"

    if manual and config.manual_deinterleave:
        interleave_methods = [config.manual_deinterleave]
    else:
        interleave_methods = (config.deinterleaving_types + ["none"]) if config.deinterleaving_enabled else ["none"]
    if manual and config.manual_fec:
        fec_methods = [config.manual_fec]
    else:
        fec_methods = (config.fec_types + ["none"]) if config.fec_enabled else ["none"]

    best, best_score = None, -1.0
    for i_method in interleave_methods:
        try:
            params = config.manual_deinterleave_params if i_method == config.manual_deinterleave else None
            deint = _apply_deinterleave(bits, i_method, params, llr=llr)
        except Exception:
            continue
        for f_method in fec_methods:
            try:
                fec = _apply_fec_decode(deint["bits"], f_method, llr=deint.get("llr"))
            except Exception:
                continue
            result_bits = fec["bits"]
            if len(result_bits) == 0:
                continue
            header = detect_header(result_bits)
            fec_ok = bool(fec.get("success"))
            header_found = header["header_offset"] is not None
            composite = (header["correlation_peak"] if header_found else 0.0) + (0.3 if fec_ok else 0.0)
            if composite > best_score:
                best_score = composite
                best = RecoveredSignal(
                    bits=result_bits, modulation=None,
                    deinterleave_method=i_method, fec_method=f_method,
                    fec_success=fec.get("success"),
                    confirmed=fec_ok or header_found,
                    llr_used=bool(fec.get("llr_used")),
                    diagnostics={"header_correlation": header["correlation_peak"],
                                "deinterleave_params": deint["params"], "fec_quality": fec.get("quality")},
                )

    if best is None:
        return RecoveredSignal(bits=bits, modulation=None, deinterleave_method="undetermined",
                               fec_method="undetermined", fec_success=None, confirmed=False,
                               diagnostics={"note": "no combination could be evaluated"})

    both_fixed = manual and bool(config.manual_deinterleave) and bool(config.manual_fec)
    if not best.confirmed and not both_fixed:
        best.diagnostics["best_unconfirmed"] = (best.deinterleave_method, best.fec_method)
        best.bits = bits
        best.deinterleave_method = config.manual_deinterleave if manual and config.manual_deinterleave else "undetermined"
        best.fec_method = config.manual_fec if manual and config.manual_fec else "undetermined"
        best.fec_success = None
        best.diagnostics.pop("deinterleave_params", None)
        best.diagnostics.pop("fec_quality", None)
        best.diagnostics["note"] = ("no de-interleaver/FEC combination showed supporting evidence; "
                                    "bits are the demodulated stream, unchanged")
    return best


# --------------------------------------------------- analysis of one profile
@dataclass
class _Prepared:
    samples: np.ndarray
    profile_name: str
    features: SignalFeatures
    isolation: IsolationInfo
    symbol_rate: float
    timing_fit: float
    offset_estimate: float


def _prepare(raw_signal, config: PipelineConfig, profile, report) -> _Prepared:
    """Preprocessing, isolation, feature extraction and initial parameter estimation."""
    samples = apply_profile(raw_signal.samples, raw_signal.sample_rate, profile)
    report(Stage.PREPROCESSING, f"[{profile.name}] DC removal + power normalization"
           + (f" + {profile.denoise}" if profile.denoise else ""))

    total_samples = len(samples)
    isolated = segment_by_energy(samples, raw_signal.sample_rate, threshold_db_above_floor=profile.segment_threshold_db)
    samples = isolated.samples
    channel = strongest_channel(samples, raw_signal.sample_rate)
    isolation = IsolationInfo(
        segment_start=isolated.segment_start, segment_end=isolated.segment_end,
        total_samples=total_samples, sample_rate=raw_signal.sample_rate,
        channel_offset_hz=channel["center_offset_hz"], channel_bandwidth_hz=channel["bandwidth_hz"],
        preprocessing_profile=profile.name,
    )
    report(Stage.SIGNAL_ISOLATION, f"Active segment [{isolated.segment_start}:{isolated.segment_end}]")

    spectral = extract_spectral_features(samples, raw_signal.sample_rate)
    temporal = extract_temporal_features(samples)
    stats = extract_signal_statistics(samples)
    report(Stage.FEATURE_EXTRACTION, "Spectral, temporal and statistical features computed")

    estimated_rate = estimate_symbol_rate(samples, raw_signal.sample_rate)
    rate_locked = config.mode == "manual" and bool(config.manual_symbol_rate)
    symbol_rate = float(config.manual_symbol_rate) if rate_locked else estimated_rate
    timing_fit = timing_fit_at(samples, raw_signal.sample_rate, symbol_rate)
    offset_estimate = estimate_carrier_offset(samples, raw_signal.sample_rate)

    features = SignalFeatures(
        bandwidth=spectral["bandwidth"],
        center_frequency=spectral["center_frequency"],
        spectral_peaks=spectral["spectral_peaks"],
        estimated_symbol_rate=symbol_rate,
        papr_db=temporal["papr_db"],
        kurtosis=stats["kurtosis"],
        skewness=stats["skewness"],
        spectral_flatness=spectral["spectral_flatness"],
        extra={"envelope_variation": temporal["envelope_variation"]},
    )
    report(Stage.PARAMETER_ESTIMATION,
           f"symbol_rate~{symbol_rate:.1f}Hz carrier_offset~{offset_estimate:.1f}Hz timing_fit={timing_fit:.2f}")
    return _Prepared(samples, profile.name, features, isolation, symbol_rate, timing_fit, offset_estimate)


def _evaluate(prep: _Prepared, point: SearchPoint, sample_rate: float, config: PipelineConfig):
    """Candidate generation and scoring at one parameter point. Returns
    (best_score, payload) where payload carries what is needed afterwards."""
    n_symbols = len(prep.samples) * point.symbol_rate / sample_rate
    if point.symbol_rate <= 0 or sample_rate / point.symbol_rate < 2 or n_symbols < config.min_symbols:
        # too few symbols for EVM to mean anything (e.g. a spurious low "rate" from noise)
        return -1.0, {"samples": prep.samples, "hypotheses": [], "point": point,
                      "timing_fit": 0.0, "timing_prominence": 0.0}

    x_unfiltered = frequency_translate(prep.samples, sample_rate, point.carrier_offset)
    x = lowpass(x_unfiltered, sample_rate, point.lowpass_hz) if point.lowpass_hz else x_unfiltered

    space = generate_hypothesis_space(sample_rate, point.symbol_rate, {
        "modulations": ([config.manual_modulation] if config.mode == "manual" and config.manual_modulation
                        else config.modulations),
        "fec": {"types": config.fec_types},
        "deinterleaving": {"types": config.deinterleaving_types},
    })
    # timing support is measured at THIS point's symbol rate, so a sub-harmonic
    # of the true clock (which demodulates to equally clean symbols) loses out
    # (measured at the rate the integer samples-per-symbol timing recovery
    # actually uses, sample_rate / round(sample_rate / symbol_rate))
    effective_rate = sample_rate / max(1, int(round(sample_rate / point.symbol_rate)))
    timing_fit = timing_fit_at(x, sample_rate, effective_rate)
    hypotheses = score_candidates(space["modulation_candidates"], x, timing_fit=timing_fit,
                                  spectrum_samples=x_unfiltered)
    score = hypotheses[0].score if hypotheses else -1.0
    return score, {"samples": x, "hypotheses": hypotheses, "point": point, "timing_fit": timing_fit,
                   "timing_prominence": timing_prominence_at(x, sample_rate, effective_rate)}


def _is_weak(payload: dict, config: PipelineConfig, manual_selection: bool) -> bool:
    """Weak evidence = low best score, an ambiguous top two, or poor support
    for the symbol rate itself (a high EVM alone cannot expose a sub-harmonic
    symbol clock)."""
    hypotheses = payload["hypotheses"]
    if not hypotheses:
        return True
    if payload["timing_fit"] < config.re_estimate_timing_threshold and not config.manual_symbol_rate:
        return True
    if hypotheses[0].score < config.re_estimate_score_threshold:
        return True
    if not manual_selection and len(hypotheses) > 1:
        return hypotheses[0].score - hypotheses[1].score < config.ambiguity_margin
    return False


# ------------------------------------------------------------------ pipeline
def run_pipeline(raw_signal, config: PipelineConfig, progress_cb=None) -> AnalysisResult:
    progress_cb = progress_cb or _noop_progress
    fs = raw_signal.sample_rate

    def report(stage: Stage, message: str = ""):
        progress_cb(stage.value, STAGE_PROGRESS[stage], message)

    report(Stage.LOADING, f"Loaded {len(raw_signal.samples)} samples @ {fs} Hz")

    manual = config.mode == "manual"
    manual_selection = manual and bool(config.manual_modulation)
    rate_locked = manual and bool(config.manual_symbol_rate)
    n_profiles = max(1, config.re_estimate_max_attempts) if config.re_estimate_enabled else 1
    profiles = PREPROCESSING_PROFILES[:n_profiles]

    best = None      # (score, prep, payload)
    trace = []

    for attempt, profile in enumerate(profiles, start=1):
        if attempt > 1:
            report(Stage.RE_ESTIMATING, f"Attempt {attempt}/{len(profiles)}: previous best "
                   f"{best[0]:.2f} still weak -> profile '{profile.name}'")
        prep = _prepare(raw_signal, config, profile, report)
        start = SearchPoint(symbol_rate=prep.symbol_rate)
        cur_score, cur_payload = _evaluate(prep, start, fs, config)
        trace.append({"attempt": attempt, "iteration": 0, "profile": profile.name,
                      "symbol_rate": start.symbol_rate, "carrier_offset_hz": start.carrier_offset,
                      "lowpass_hz": start.lowpass_hz, "score": cur_score, "accepted": True,
                      "note": "initial estimate"})
        first = cur_payload["hypotheses"][0].modulation if cur_payload["hypotheses"] else "none"
        report(Stage.CANDIDATE_SCORING, f"[{profile.name}] best={first} score={cur_score:.2f}")

        if config.re_estimate_enabled and _is_weak(cur_payload, config, manual_selection):
            def on_iter(i, pt, sc, accepted, _name=profile.name):
                report(Stage.RE_ESTIMATING, f"[{_name}] iteration {i}: score {sc:.3f} "
                       f"(Rs={pt.symbol_rate:.1f}Hz, offset={pt.carrier_offset:.1f}Hz, "
                       f"lowpass={pt.lowpass_hz}) {'accepted' if accepted else 'no improvement'}")

            _, cur_score, cur_payload, search_trace = coordinate_search(
                start,
                evaluate=lambda pt, _p=prep: _evaluate(_p, pt, fs, config),
                neighbours_fn=lambda pt, _p=prep: neighbours(pt, fs, _p.offset_estimate, rate_locked),
                tolerance=config.re_estimate_tolerance,
                max_iterations=config.re_estimate_max_iterations,
                on_iteration=on_iter,
                tie_support=lambda pl: pl["timing_prominence"],
            )
            for t in search_trace:
                trace.append({"attempt": attempt, "iteration": t["iteration"], "profile": profile.name,
                              "symbol_rate": t["point"].symbol_rate,
                              "carrier_offset_hz": t["point"].carrier_offset,
                              "lowpass_hz": t["point"].lowpass_hz, "score": t["score"],
                              "accepted": t["accepted"], "note": t["note"]})

        if best is None or cur_score > best[0]:
            best = (cur_score, prep, cur_payload)
        if not _is_weak(cur_payload, config, manual_selection):
            break

    _, prep, payload = best
    samples_bb = payload["samples"]
    hypotheses = payload["hypotheses"]
    point = payload["point"]
    best_hypothesis = hypotheses[0] if hypotheses else None

    verdict, verdict_reason = decide_verdict(
        hypotheses, manual_selection, config.insufficient_evidence_score, config.ambiguity_margin,
        timing_fit=None if rate_locked else payload["timing_fit"], min_timing_fit=config.min_timing_fit)
    report(Stage.BEST_HYPOTHESIS,
           f"Best-supported hypothesis: {best_hypothesis.modulation} (score {best_hypothesis.score:.2f}), "
           f"verdict: {verdict}" if best_hypothesis else "No supported hypothesis")

    # SNR reported for the winning hypothesis, using that modulation's envelope kurtosis
    kurt = best_hypothesis.parameters["envelope_kurtosis"] if best_hypothesis else 1.0
    snr_db = estimate_snr(samples_bb, fs, kurtosis_factor=kurt)
    prep.features.snr_db = snr_db

    sr_est = estimate_sample_rate(fs, raw_signal.source_format)
    estimate = ParameterEstimate(
        sample_rate=sr_est["sample_rate"],
        symbol_rate=point.symbol_rate,
        carrier_frequency=raw_signal.center_frequency + prep.offset_estimate,
        carrier_offset=prep.offset_estimate,
        bandwidth=prep.features.bandwidth,
        snr_db=snr_db,
        timing_fit=payload["timing_fit"],
        samples_per_symbol=int(round(fs / point.symbol_rate)) if point.symbol_rate > 0 else 0,
    )
    prep.features.estimated_symbol_rate = point.symbol_rate

    # Every candidate was demodulated during scoring (EVM needs its symbols);
    # only the best-supported hypothesis's bits continue into recovery. With
    # insufficient evidence there is nothing to recover from.
    recovered = None
    if (best_hypothesis is not None and verdict != INSUFFICIENT
            and best_hypothesis.demodulation_result is not None and len(best_hypothesis.demodulation_result)):
        recovered = _search_recovery(best_hypothesis.demodulation_result, config,
                                     demod_llr=best_hypothesis.demodulation_llr)
        recovered.modulation = best_hypothesis.modulation
    report(Stage.DEINTERLEAVING, f"Selected: {recovered.deinterleave_method}" if recovered else "skipped")
    report(Stage.FEC_DECODING, f"Selected: {recovered.fec_method}" if recovered else "skipped")

    bitstream = None
    if recovered is not None and len(recovered.bits):
        header = detect_header(recovered.bits)
        if header["header_offset"] is not None and header["polarity"] == "inverted":
            recovered.bits = (1 - recovered.bits).astype(np.uint8)
            recovered.diagnostics["polarity"] = "inverted; corrected because the sync word matched the complement"
        payload_bits, payload_start, payload_end = None, None, None
        if header["header_offset"] is not None:
            payload_bits = extract_payload(recovered.bits, header["header_offset"], header["pattern_length"])
            payload_start = header["header_offset"] + header["pattern_length"]
            payload_end = payload_start + len(payload_bits)
        bitstream = BitstreamResult(
            header_offset=header["header_offset"], header_pattern=header["header_pattern"],
            payload_bits=payload_bits, correlation_peak=header["correlation_peak"],
            pattern_length=header["pattern_length"], hamming_similarity=header["hamming_similarity"],
            false_alarm_probability=header["false_alarm_probability"], polarity=header["polarity"],
            payload_start=payload_start, payload_end=payload_end,
        )
    report(Stage.BITSTREAM_CORRELATION, "Known sync-word search complete")

    provenance = _build_provenance(config, sr_est, rate_locked, manual_selection, verdict, recovered, bitstream)

    # Visualization data comes from the isolated signal (before any search
    # translation) so the spectrum shows where the signal really sits; the
    # constellation is the best hypothesis's own symbols.
    freqs, psd_db = power_spectrum(prep.samples, fs)
    wf_freqs, wf_times, wf_db = waterfall(prep.samples, fs)
    waveform_viz = decimate_for_visualization(prep.samples)
    viz = {
        "waveform": [[float(s.real), float(s.imag)] for s in waveform_viz],
        "spectrum_freqs": freqs.tolist(),
        "spectrum_db": psd_db.tolist(),
        "waterfall_freqs": wf_freqs.tolist(),
        "waterfall_times": wf_times.tolist(),
        "waterfall_db": wf_db.tolist(),
        "constellation": best_hypothesis.diagnostics.get("symbols", []) if best_hypothesis else [],
    }
    report(Stage.COMPLETE, "Analysis complete")

    return AnalysisResult(
        file_id=raw_signal.filename,
        isolation=prep.isolation,
        features=prep.features,
        estimate=estimate,
        hypotheses=hypotheses,
        best_hypothesis=best_hypothesis,
        recovered=recovered,
        bitstream=bitstream,
        visualizations=viz,
        verdict=verdict,
        verdict_reason=verdict_reason,
        provenance=provenance,
        reestimation=trace,
    )


def _build_provenance(config, sr_est, rate_locked, manual_selection, verdict, recovered, bitstream) -> dict:
    prov = {
        "sample_rate": "metadata-derived" if sr_est["source"] == "file_header" else "user-provided",
        "center_frequency": "user-provided",
        "carrier_offset": "estimated",
        "carrier_frequency": "user-provided center + estimated offset",
        "symbol_rate": "user-provided" if rate_locked else "estimated",
        "bandwidth": "estimated",
        "snr": "estimated",
    }
    if verdict == INSUFFICIENT:
        prov["modulation"] = "not determined (insufficient evidence)"
    elif manual_selection:
        prov["modulation"] = "user-provided"
    else:
        prov["modulation"] = "candidate-inferred" + (" (ambiguous)" if verdict == AMBIGUOUS else "")

    manual = config.mode == "manual"

    def recovery_source(user_value, chosen):
        if recovered is None:
            return "not run"
        if manual and user_value:
            return "user-provided"
        if chosen == "undetermined":
            return "not determined"
        return "candidate-tested"

    if recovered is not None:
        prov["de-interleaving"] = recovery_source(config.manual_deinterleave, recovered.deinterleave_method)
        prov["fec"] = recovery_source(config.manual_fec, recovered.fec_method)
    else:
        prov["de-interleaving"] = prov["fec"] = "not run"
    prov["header"] = "known sync word" if bitstream and bitstream.header_pattern else "not found"
    return prov
