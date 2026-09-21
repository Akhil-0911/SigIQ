from core.hypotheses.modulation import build_candidates
from core.hypotheses.fec import build_fec_candidates
from core.hypotheses.interleaving import build_interleaving_candidates


def generate_hypothesis_space(sample_rate: float, symbol_rate: float, config: dict, snr_db: float = None) -> dict:
    modulations = config.get("modulations")
    return {
        "modulation_candidates": build_candidates(sample_rate, symbol_rate, modulations, snr_db),
        "fec_candidates": build_fec_candidates(config.get("fec", {}).get("types")),
        "interleaving_candidates": build_interleaving_candidates(config.get("deinterleaving", {}).get("types")),
    }
