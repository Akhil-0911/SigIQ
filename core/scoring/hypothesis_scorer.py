from core.pipeline.models import HypothesisResult
from core.scoring.evidence import score_from_evidence
from core.scoring.confidence import confidence_from_scores


def score_candidates(candidates: list, samples) -> list:
    """Run demodulate() + extract_evidence() for every ModulationCandidate,
    score them, and return HypothesisResult objects sorted best-first."""
    results = []
    for candidate in candidates:
        demod = candidate.demodulate(samples)
        evidence = candidate.extract_evidence(samples, demod)
        score = score_from_evidence(evidence)
        results.append((candidate, demod, evidence, score))

    confidences = confidence_from_scores([r[3] for r in results])

    hypotheses = []
    for (candidate, demod, evidence, score), confidence in zip(results, confidences):
        hypotheses.append(HypothesisResult(
            modulation=candidate.name,
            parameters={"symbol_rate": candidate.symbol_rate, "sample_rate": candidate.sample_rate},
            evidence=evidence,
            score=score,
            confidence=confidence,
            demodulation_result=demod.get("bits"),
            diagnostics={
                "evm": demod.get("evm"),
                "symbols": [[float(s.real), float(s.imag)] for s in demod.get("symbols", [])][:2000],
            },
        ))

    hypotheses.sort(key=lambda h: h.score, reverse=True)
    return hypotheses
