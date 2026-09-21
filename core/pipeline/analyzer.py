"""Central orchestrator: RawSignal -> AnalysisResult.

This module has no UI knowledge -- it is directly unit-testable and runnable
from a plain Python script (see tests/test_pipeline_smoke.py). UIs call
`run_pipeline()` and receive progress through its callback.
"""
import numpy as np

from core.pipeline.models import (
    SignalFeatures, ParameterEstimate, AnalysisResult, RecoveredSignal, BitstreamResult,
)
from core.pipeline.pipeline_config import PipelineConfig
from core.pipeline.stages import Stage, STAGE_PROGRESS

from core.preprocessing.profiles import PREPROCESSING_PROFILES, apply_profile
from core.isolation.signal_segmentation import segment_by_energy
from core.isolation.channel_detection import strongest_channel
from core.isolation.spectrum import power_spectrum, waterfall

from core.feature_extraction.spectral_features import extract_spectral_features
from core.feature_extraction.temporal_features import extract_temporal_features
from core.feature_extraction.signal_statistics import extract_signal_statistics

from core.estimation.sample_rate import estimate_sample_rate
from core.estimation.symbol_rate import estimate_symbol_rate
from core.estimation.carrier_frequency import estimate_carrier_frequency
from core.estimation.snr import estimate_snr

from core.hypotheses.generator import generate_hypothesis_space
from core.scoring.hypothesis_scorer import score_candidates

from core.deinterleaving.block import deinterleave_block
from core.deinterleaving.convolutional import deinterleave_convolutional
from core.deinterleaving.diagonal import deinterleave_diagonal
from core.deinterleaving.pseudo_random import deinterleave_pseudo_random

from core.fec.viterbi import viterbi_decode
from core.fec.reed_solomon import rs_decode
from core.fec.concatenated import concatenated_decode
from core.fec.ldpc import ldpc_decode, _regular_h_matrix

from core.correlation.header_detection import detect_header
from core.correlation.payload_detection import extract_payload

from core.preprocessing.resampling import decimate_for_visualization

MAX_RECOVERY_BITS = 6000  # keep the brute-force interleaving x FEC search tractable in-request


def _noop_progress(stage, percent, message):
    pass


def _apply_deinterleave(bits: np.ndarray, method: str, params: dict = None) -> np.ndarray:
    params = params or {}
    n = len(bits)
    if method == "none":
        return bits
    if method == "block":
        cols = params.get("cols") or max(2, int(np.sqrt(n)))
        rows = n // cols or 1
        return deinterleave_block(bits, rows, cols)
    if method == "diagonal":
        cols = params.get("cols") or max(2, int(np.sqrt(n)))
        rows = n // cols or 1
        return deinterleave_diagonal(bits, rows, cols)
    if method == "convolutional":
        return deinterleave_convolutional(bits, params.get("num_branches", 4), params.get("delay_step", 4))
    if method == "pseudo_random":
        return deinterleave_pseudo_random(bits, params.get("seed", 42))
    raise ValueError(f"Unknown de-interleaving method '{method}'")


def _apply_fec_decode(bits: np.ndarray, method: str) -> dict:
    if method == "none":
        return {"bits": bits, "success": None}
    if method == "convolutional_viterbi":
        result = viterbi_decode(bits)
        return {"bits": result["bits"], "success": result["avg_hamming"] < 0.15, "quality": result["avg_hamming"]}
    if method == "reed_solomon":
        result = rs_decode(bits)
        return {"bits": result["bits"], "success": result["success"]}
    if method == "concatenated":
        result = concatenated_decode(bits)
        return {"bits": result["bits"], "success": result["success"]}
    if method == "ldpc":
        k = max(1, int(len(bits) * 0.5))
        h = _regular_h_matrix(len(bits), k)
        result = ldpc_decode(bits, h, k)
        return {"bits": result["bits"], "success": result["success"]}
    raise ValueError(f"Unknown FEC method '{method}'")


def _search_recovery(demod_bits: np.ndarray, config: PipelineConfig) -> RecoveredSignal:
    bits = demod_bits[:MAX_RECOVERY_BITS] if len(demod_bits) > MAX_RECOVERY_BITS else demod_bits

    if config.mode == "manual" and config.manual_deinterleave and config.manual_fec:
        deint = _apply_deinterleave(bits, config.manual_deinterleave, config.manual_deinterleave_params)
        fec = _apply_fec_decode(deint, config.manual_fec)
        return RecoveredSignal(
            bits=fec["bits"], modulation=None,
            deinterleave_method=config.manual_deinterleave, fec_method=config.manual_fec,
            fec_success=fec.get("success"),
        )

    interleave_methods = (config.deinterleaving_types + ["none"]) if config.deinterleaving_enabled else ["none"]
    fec_methods = (config.fec_types + ["none"]) if config.fec_enabled else ["none"]

    best = None
    best_score = -1.0
    for i_method in interleave_methods:
        try:
            deint = _apply_deinterleave(bits, i_method)
        except Exception:
            continue
        for f_method in fec_methods:
            try:
                fec = _apply_fec_decode(deint, f_method)
            except Exception:
                continue
            result_bits = fec["bits"]
            if len(result_bits) == 0:
                continue
            header = detect_header(result_bits)
            composite = header["correlation_peak"] + (0.3 if fec.get("success") else 0.0)
            if composite > best_score:
                best_score = composite
                best = RecoveredSignal(
                    bits=result_bits, modulation=None,
                    deinterleave_method=i_method, fec_method=f_method,
                    fec_success=fec.get("success"),
                    diagnostics={"header_correlation": header["correlation_peak"]},
                )

    if best is None:
        best = RecoveredSignal(bits=bits, modulation=None, deinterleave_method="none", fec_method="none", fec_success=None)
    return best


def _run_pass(raw_signal, config: PipelineConfig, profile, report) -> dict:
    """One preprocessing -> isolation -> feature extraction -> parameter
    estimation -> candidate scoring pass, using the given preprocessing
    profile. Returns everything the rest of the pipeline needs, plus the
    profile name for diagnostics."""
    samples = apply_profile(raw_signal.samples, raw_signal.sample_rate, profile)
    report(Stage.PREPROCESSING, f"[{profile.name}] DC removal + power normalization"
           + (f" + {profile.denoise}" if profile.denoise else ""))

    isolated = segment_by_energy(samples, raw_signal.sample_rate, threshold_db_above_floor=profile.segment_threshold_db)
    samples = isolated.samples
    channel = strongest_channel(samples, raw_signal.sample_rate)
    report(Stage.SIGNAL_ISOLATION, f"Active segment [{isolated.segment_start}:{isolated.segment_end}]")

    spectral = extract_spectral_features(samples, raw_signal.sample_rate)
    temporal = extract_temporal_features(samples)
    stats = extract_signal_statistics(samples)
    report(Stage.FEATURE_EXTRACTION, "Spectral, temporal and statistical features computed")

    sr_est = estimate_sample_rate(raw_signal.sample_rate, raw_signal.source_format)
    symbol_rate = estimate_symbol_rate(samples, raw_signal.sample_rate)
    carrier = estimate_carrier_frequency(samples, raw_signal.sample_rate, raw_signal.center_frequency)
    snr_db = estimate_snr(samples, raw_signal.sample_rate)

    features = SignalFeatures(
        bandwidth=spectral["bandwidth"],
        center_frequency=spectral["center_frequency"],
        spectral_peaks=spectral["spectral_peaks"],
        estimated_symbol_rate=symbol_rate,
        snr_db=snr_db,
        papr_db=temporal["papr_db"],
        kurtosis=stats["kurtosis"],
        skewness=stats["skewness"],
        spectral_flatness=spectral["spectral_flatness"],
        extra={"envelope_variation": temporal["envelope_variation"], "channel": channel, "preprocessing_profile": profile.name},
    )
    estimate = ParameterEstimate(
        sample_rate=sr_est["sample_rate"], symbol_rate=symbol_rate,
        carrier_frequency=carrier, bandwidth=spectral["bandwidth"], snr_db=snr_db,
    )
    report(Stage.PARAMETER_ESTIMATION, f"symbol_rate~{symbol_rate:.1f}Hz snr~{snr_db:.1f}dB")

    hyp_space = generate_hypothesis_space(raw_signal.sample_rate, symbol_rate, {
        "modulations": [config.manual_modulation] if config.mode == "manual" and config.manual_modulation else config.modulations,
        "fec": {"types": config.fec_types},
        "deinterleaving": {"types": config.deinterleaving_types},
    }, snr_db=snr_db)
    report(Stage.CANDIDATE_GENERATION, f"{len(hyp_space['modulation_candidates'])} modulation candidates")

    hypotheses = score_candidates(hyp_space["modulation_candidates"], samples)
    best_hypothesis = hypotheses[0] if hypotheses else None
    report(Stage.CANDIDATE_SCORING, f"[{profile.name}] best={best_hypothesis.modulation if best_hypothesis else 'none'} "
           f"score={best_hypothesis.score:.2f}" if best_hypothesis else f"[{profile.name}] no candidates scored")

    return {
        "samples": samples, "features": features, "estimate": estimate,
        "hypotheses": hypotheses, "best_hypothesis": best_hypothesis, "profile": profile.name,
    }


def run_pipeline(raw_signal, config: PipelineConfig, progress_cb=None) -> AnalysisResult:
    progress_cb = progress_cb or _noop_progress

    def report(stage: Stage, message: str = ""):
        progress_cb(stage.value, STAGE_PROGRESS[stage], message)

    report(Stage.LOADING, f"Loaded {len(raw_signal.samples)} samples @ {raw_signal.sample_rate} Hz")

    # --- re-estimation loop: retry with a different preprocessing profile
    # whenever the best hypothesis so far scores below threshold ---
    profiles = PREPROCESSING_PROFILES[:max(1, config.re_estimate_max_attempts)] if config.re_estimate_enabled else PREPROCESSING_PROFILES[:1]

    best_pass = None
    attempts = []
    for i, profile in enumerate(profiles):
        if i > 0:
            report(Stage.RE_ESTIMATING, f"Attempt {i + 1}/{len(profiles)}: best score so far "
                   f"{best_pass['best_hypothesis'].score:.2f} < threshold {config.re_estimate_score_threshold} "
                   f"-> retrying with profile '{profile.name}'")
        result = _run_pass(raw_signal, config, profile, report)
        attempts.append({"profile": profile.name, "score": result["best_hypothesis"].score if result["best_hypothesis"] else None})

        if best_pass is None or (
            result["best_hypothesis"] is not None and
            (best_pass["best_hypothesis"] is None or result["best_hypothesis"].score > best_pass["best_hypothesis"].score)
        ):
            best_pass = result

        if best_pass["best_hypothesis"] is not None and best_pass["best_hypothesis"].score >= config.re_estimate_score_threshold:
            break

    samples = best_pass["samples"]
    features = best_pass["features"]
    estimate = best_pass["estimate"]
    hypotheses = best_pass["hypotheses"]
    best_hypothesis = best_pass["best_hypothesis"]
    features.extra["re_estimate_attempts"] = attempts
    features.extra["preprocessing_profile"] = best_pass["profile"]

    report(Stage.DEMODULATION, "Demodulation complete for all candidates")

    # --- deinterleaving + FEC recovery search ---
    recovered = None
    if best_hypothesis is not None and best_hypothesis.demodulation_result is not None and len(best_hypothesis.demodulation_result):
        recovered = _search_recovery(best_hypothesis.demodulation_result, config)
        recovered.modulation = best_hypothesis.modulation
    report(Stage.DEINTERLEAVING, recovered.deinterleave_method if recovered else "skipped")
    report(Stage.FEC_DECODING, recovered.fec_method if recovered else "skipped")

    # --- bitstream correlation ---
    bitstream = None
    if recovered is not None and len(recovered.bits):
        header = detect_header(recovered.bits)
        payload = None
        if header["header_offset"] is not None:
            pattern_len = len(header["header_pattern"]) if isinstance(header.get("header_pattern"), str) else 8
            payload = extract_payload(recovered.bits, header["header_offset"], pattern_len)
        bitstream = BitstreamResult(
            header_offset=header["header_offset"], header_pattern=header["header_pattern"],
            payload_bits=payload, correlation_peak=header["correlation_peak"],
        )
    report(Stage.BITSTREAM_CORRELATION, "Header search complete")

    # --- visualizations (downsampled for the browser) ---
    freqs, psd_db = power_spectrum(samples, raw_signal.sample_rate)
    wf_freqs, wf_times, wf_db = waterfall(samples, raw_signal.sample_rate)
    waveform_viz = decimate_for_visualization(samples)
    viz = {
        "waveform": [[float(s.real), float(s.imag)] for s in waveform_viz],
        "waveform_sample_rate": raw_signal.sample_rate,
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
        features=features,
        estimate=estimate,
        hypotheses=hypotheses,
        best_hypothesis=best_hypothesis,
        recovered=recovered,
        bitstream=bitstream,
        visualizations=viz,
    )
