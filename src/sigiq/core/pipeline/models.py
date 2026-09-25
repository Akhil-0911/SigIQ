"""Shared data models passed between core stages.

Every stage consumes and returns one of these instead of a raw dict, so the
pipeline stays traceable end to end.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class RawSignal:
    """Complex baseband samples loaded from a .iq or .wav file."""
    samples: np.ndarray            # complex128 IQ samples (or real, upcast to complex)
    sample_rate: float             # Hz
    source_format: str             # "iq" | "wav"
    center_frequency: float = 0.0  # Hz, user supplied (IQ files carry no header)
    filename: str = ""


@dataclass
class IsolatedSignal:
    samples: np.ndarray
    sample_rate: float
    segment_start: int
    segment_end: int


@dataclass
class IsolationInfo:
    """Output of the Signal Isolation stage: which part of the recording
    and which channel the rest of the pipeline analyses."""
    segment_start: int = 0
    segment_end: int = 0
    total_samples: int = 0
    sample_rate: float = 0.0
    channel_offset_hz: float = 0.0
    channel_bandwidth_hz: float = 0.0
    preprocessing_profile: str = ""


@dataclass
class SignalFeatures:
    bandwidth: float = 0.0
    center_frequency: float = 0.0
    spectral_peaks: list = field(default_factory=list)
    estimated_symbol_rate: float = 0.0
    snr_db: float = 0.0
    papr_db: float = 0.0
    kurtosis: float = 0.0
    skewness: float = 0.0
    spectral_flatness: float = 0.0
    extra: dict = field(default_factory=dict)


@dataclass
class ParameterEstimate:
    sample_rate: float = 0.0
    symbol_rate: float = 0.0
    carrier_frequency: float = 0.0   # absolute = center_frequency + carrier_offset
    carrier_offset: float = 0.0      # estimated offset from the tuner center, Hz
    bandwidth: float = 0.0
    snr_db: float = 0.0
    timing_fit: float = 0.0          # 0..1, strength of the symbol-clock line above noise
    samples_per_symbol: int = 0      # round(sample_rate / symbol_rate); the timing-recovery decimation factor


@dataclass
class HypothesisResult:
    modulation: str
    parameters: dict
    evidence: dict
    score: float
    confidence: float
    metrics: dict = field(default_factory=dict)   # per-metric scores, each in [0, 1]
    demodulation_result: Optional[np.ndarray] = None
    demodulation_llr: Optional[np.ndarray] = None  # per-bit soft info, same order/length as demodulation_result
    diagnostics: dict = field(default_factory=dict)


@dataclass
class RecoveredSignal:
    bits: np.ndarray
    modulation: str
    deinterleave_method: Optional[str] = None
    fec_method: Optional[str] = None
    fec_success: Optional[bool] = None
    confirmed: bool = False   # True only if the chosen de-interleaver/FEC pair had supporting evidence
    llr_used: bool = False    # True if FEC decoding used real per-bit soft information, not hard 0/1 bits
    diagnostics: dict = field(default_factory=dict)


@dataclass
class BitstreamResult:
    header_offset: Optional[int]
    header_pattern: Optional[str]
    payload_bits: Optional[np.ndarray]
    correlation_peak: float            # normalized bipolar correlation, -1..1
    pattern_length: int = 0
    hamming_similarity: float = 0.0    # 1 - d_H / N at the match
    false_alarm_probability: float = 1.0  # chance a random stream matches this well (Bonferroni)
    polarity: str = "normal"          # "inverted" if the sync word matched the complemented stream
    payload_start: Optional[int] = None
    payload_end: Optional[int] = None
    diagnostics: dict = field(default_factory=dict)


@dataclass
class AnalysisResult:
    file_id: str
    isolation: IsolationInfo
    features: SignalFeatures
    estimate: ParameterEstimate
    hypotheses: list  # list[HypothesisResult], best-first
    best_hypothesis: Optional[HypothesisResult]
    recovered: Optional[RecoveredSignal]
    bitstream: Optional[BitstreamResult]
    visualizations: dict  # waveform/spectrum/waterfall/constellation arrays (downsampled)
    verdict: str = "determined"        # determined | ambiguous | insufficient_evidence | user_selected
    verdict_reason: str = ""
    provenance: dict = field(default_factory=dict)      # parameter -> where its value came from
    reestimation: list = field(default_factory=list)    # trace of the parameter search
