from dataclasses import dataclass, field


@dataclass
class PipelineConfig:
    mode: str = "automatic"            # "automatic" | "manual"

    # re-estimation: if the best score is below re_estimate_score_threshold (or
    # the top two candidates are within ambiguity_margin), search
    # (symbol rate, carrier offset, low-pass cutoff) for a better score. The
    # search stops when an iteration improves the score by less than
    # re_estimate_tolerance or after re_estimate_max_iterations; if the
    # result is still weak the next preprocessing profile is tried, up to
    # re_estimate_max_attempts profiles in total.
    re_estimate_enabled: bool = True
    re_estimate_max_attempts: int = 3
    re_estimate_max_iterations: int = 3
    re_estimate_tolerance: float = 0.005
    re_estimate_score_threshold: float = 0.6
    re_estimate_timing_threshold: float = 0.3   # min timing_fit before the symbol rate is trusted

    # honest-outcome limits (see core/scoring/verdict.py)
    insufficient_evidence_score: float = 0.3
    min_timing_fit: float = 0.5   # below this no symbol clock is considered found (automatic rate only)
    min_symbols: int = 100        # a symbol rate giving fewer symbols than this is not evaluated
    ambiguity_margin: float = 0.05

    modulations: list = field(default_factory=lambda: ["BPSK", "QPSK", "16-QAM", "2-FSK", "4-FSK"])
    deinterleaving_enabled: bool = True
    deinterleaving_types: list = field(default_factory=lambda: ["block", "convolutional", "diagonal", "pseudo_random"])
    fec_enabled: bool = True
    fec_types: list = field(default_factory=lambda: ["convolutional_viterbi", "reed_solomon", "concatenated", "ldpc"])

    # manual overrides (used when mode == "manual"); None means "not specified"
    manual_modulation: str = None
    manual_symbol_rate: float = None
    manual_deinterleave: str = None
    manual_deinterleave_params: dict = field(default_factory=dict)
    manual_fec: str = None

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineConfig":
        analysis = d.get("analysis", {})
        deint = d.get("deinterleaving", {})
        fec = d.get("fec", {})
        manual = d.get("manual", {})
        defaults = cls()
        return cls(
            mode=analysis.get("mode", "automatic"),
            re_estimate_enabled=analysis.get("re_estimate_enabled", defaults.re_estimate_enabled),
            re_estimate_max_attempts=analysis.get("re_estimate_max_attempts", defaults.re_estimate_max_attempts),
            re_estimate_max_iterations=analysis.get("re_estimate_max_iterations", defaults.re_estimate_max_iterations),
            re_estimate_tolerance=analysis.get("re_estimate_tolerance", defaults.re_estimate_tolerance),
            re_estimate_score_threshold=analysis.get("re_estimate_score_threshold", defaults.re_estimate_score_threshold),
            re_estimate_timing_threshold=analysis.get("re_estimate_timing_threshold", defaults.re_estimate_timing_threshold),
            insufficient_evidence_score=analysis.get("insufficient_evidence_score", defaults.insufficient_evidence_score),
            ambiguity_margin=analysis.get("ambiguity_margin", defaults.ambiguity_margin),
            min_timing_fit=analysis.get("min_timing_fit", defaults.min_timing_fit),
            min_symbols=analysis.get("min_symbols", defaults.min_symbols),
            modulations=d.get("modulations", defaults.modulations),
            deinterleaving_enabled=deint.get("enabled", True),
            deinterleaving_types=deint.get("types", defaults.deinterleaving_types),
            fec_enabled=fec.get("enabled", True),
            fec_types=fec.get("types", defaults.fec_types),
            manual_modulation=manual.get("modulation"),
            manual_symbol_rate=manual.get("symbol_rate"),
            manual_deinterleave=manual.get("deinterleave"),
            manual_deinterleave_params=manual.get("deinterleave_params", {}),
            manual_fec=manual.get("fec"),
        )
