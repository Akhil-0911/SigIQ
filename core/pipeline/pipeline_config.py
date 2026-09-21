from dataclasses import dataclass, field


@dataclass
class PipelineConfig:
    format: str = "iq"                 # "iq" | "wav"
    sample_rate: float = 0.0           # required for iq, overrides header for wav if set
    center_frequency: float = 0.0
    iq_dtype: str = "float32"

    mode: str = "automatic"            # "automatic" | "manual"
    estimate_sample_rate: bool = True
    detect_modulation: bool = True
    detect_fec: bool = True
    detect_interleaving: bool = True

    # re-estimation feedback loop: if the best hypothesis scores below
    # re_estimate_score_threshold, redo preprocessing/isolation with a
    # different profile and re-score, up to re_estimate_max_attempts times.
    re_estimate_enabled: bool = True
    re_estimate_max_attempts: int = 3
    re_estimate_score_threshold: float = 0.6

    modulations: list = field(default_factory=lambda: ["BPSK", "QPSK", "16-QAM", "2-FSK", "4-FSK"])
    deinterleaving_enabled: bool = True
    deinterleaving_types: list = field(default_factory=lambda: ["block", "convolutional", "diagonal", "pseudo_random"])
    fec_enabled: bool = True
    fec_types: list = field(default_factory=lambda: ["convolutional_viterbi", "reed_solomon", "concatenated", "ldpc"])

    # manual overrides (used when mode == "manual")
    manual_modulation: str = None
    manual_symbol_rate: float = None
    manual_deinterleave: str = None
    manual_deinterleave_params: dict = field(default_factory=dict)
    manual_fec: str = None

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineConfig":
        inp = d.get("input", {})
        analysis = d.get("analysis", {})
        deint = d.get("deinterleaving", {})
        fec = d.get("fec", {})
        manual = d.get("manual", {})
        return cls(
            format=inp.get("format", "iq"),
            sample_rate=inp.get("sample_rate", 0.0),
            center_frequency=inp.get("center_frequency", 0.0),
            iq_dtype=inp.get("iq_dtype", "float32"),
            mode=analysis.get("mode", "automatic"),
            estimate_sample_rate=analysis.get("estimate_sample_rate", True),
            detect_modulation=analysis.get("detect_modulation", True),
            detect_fec=analysis.get("detect_fec", True),
            detect_interleaving=analysis.get("detect_interleaving", True),
            re_estimate_enabled=analysis.get("re_estimate_enabled", True),
            re_estimate_max_attempts=analysis.get("re_estimate_max_attempts", 3),
            re_estimate_score_threshold=analysis.get("re_estimate_score_threshold", 0.6),
            modulations=d.get("modulations", ["BPSK", "QPSK", "16-QAM", "2-FSK", "4-FSK"]),
            deinterleaving_enabled=deint.get("enabled", True),
            deinterleaving_types=deint.get("types", ["block", "convolutional", "diagonal", "pseudo_random"]),
            fec_enabled=fec.get("enabled", True),
            fec_types=fec.get("types", ["convolutional_viterbi", "reed_solomon", "concatenated", "ldpc"]),
            manual_modulation=manual.get("modulation"),
            manual_symbol_rate=manual.get("symbol_rate"),
            manual_deinterleave=manual.get("deinterleave"),
            manual_deinterleave_params=manual.get("deinterleave_params", {}),
            manual_fec=manual.get("fec"),
        )
