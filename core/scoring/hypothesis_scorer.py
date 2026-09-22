from core.pipeline.models import HypothesisResult
from core.scoring.evidence import metrics_from_evidence, score_from_metrics
from core.scoring.confidence import confidence_from_scores


def score_candidates(candidates: list, samples, timing_fit: float = 0.0, spectrum_samples=None) -> list:
    """Demodulate every ModulationCandidate, extract its evidence, score it,
    and return HypothesisResult objects sorted best-first. `timing_fit` is the
    pass-level symbol-clock strength shared by all candidates."""
    results = []
    for candidate in candidates:
        candidate.spectrum_samples = spectrum_samples
        demod = candidate.demodulate(samples)
        evidence = candidate.extract_evidence(samples, demod)
        evidence["timing_fit"] = timing_fit
        metrics = metrics_from_evidence(evidence)
        results.append((candidate, demod, evidence, metrics, score_from_metrics(metrics)))

    confidences = confidence_from_scores([r[4] for r in results])

    hypotheses = []
    for (candidate, demod, evidence, metrics, score), confidence in zip(results, confidences):
        hypotheses.append(HypothesisResult(
            modulation=candidate.name,
            parameters={"symbol_rate": candidate.symbol_rate, "sample_rate": candidate.sample_rate,
                        "envelope_kurtosis": candidate.envelope_kurtosis},
            evidence=evidence,
            score=score,
            confidence=confidence,
            metrics=metrics,
            demodulation_result=demod.get("bits"),
            demodulation_llr=demod.get("llr"),
            diagnostics={
                "evm": demod.get("evm"),
                "symbols": [[float(s.real), float(s.imag)] for s in demod.get("symbols", [])][:2000],
            },
        ))

    hypotheses.sort(key=lambda h: h.score, reverse=True)
    return hypotheses
