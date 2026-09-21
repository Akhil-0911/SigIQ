"""Shared data models passed between core stages.

Every stage consumes and returns one of these instead of a raw dict, so the
pipeline stays traceable end to end (see architecture notes in docs/design_notes.txt, §10).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import numpy as np


@dataclass
class RawSignal:
    """Complex baseband samples loaded from a .iq or .wav file."""
    samples: np.ndarray            # complex128 IQ samples (or real, upcast to complex)
    sample_rate: float             # Hz
    source_format: str             # "iq" | "wav"
    center_frequency: float = 0.0  # Hz, user supplied (IQ files carry no header)
    bit_depth: Optional[int] = None
    channels: int = 1
    filename: str = ""


@dataclass
class PreprocessedSignal:
    samples: np.ndarray
    sample_rate: float
    applied_steps: list = field(default_factory=list)


@dataclass
class IsolatedSignal:
    samples: np.ndarray
    sample_rate: float
    segment_start: int
    segment_end: int
    occupied_bandwidth: float = 0.0
    center_offset_hz: float = 0.0


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
    constellation_cluster_count: int = 0
    constellation_compactness: float = 0.0
    cyclic_peak_freq: float = 0.0
    extra: dict = field(default_factory=dict)


@dataclass
class ParameterEstimate:
    sample_rate: float = 0.0
    symbol_rate: float = 0.0
    carrier_frequency: float = 0.0
    bandwidth: float = 0.0
    snr_db: float = 0.0


@dataclass
class CandidateResult:
    name: str
    evidence: dict = field(default_factory=dict)
    score: float = 0.0
    demod_bits: Optional[np.ndarray] = None
    diagnostics: dict = field(default_factory=dict)


@dataclass
class HypothesisResult:
    modulation: str
    parameters: dict
    evidence: dict
    score: float
    confidence: float
    demodulation_result: Optional[np.ndarray] = None
    diagnostics: dict = field(default_factory=dict)


@dataclass
class RecoveredSignal:
    bits: np.ndarray
    modulation: str
    deinterleave_method: Optional[str] = None
    fec_method: Optional[str] = None
    fec_success: Optional[bool] = None
    diagnostics: dict = field(default_factory=dict)


@dataclass
class BitstreamResult:
    header_offset: Optional[int]
    header_pattern: Optional[str]
    payload_bits: Optional[np.ndarray]
    correlation_peak: float
    diagnostics: dict = field(default_factory=dict)


@dataclass
class AnalysisResult:
    file_id: str
    features: SignalFeatures
    estimate: ParameterEstimate
    hypotheses: list  # list[HypothesisResult], best-first
    best_hypothesis: Optional[HypothesisResult]
    recovered: Optional[RecoveredSignal]
    bitstream: Optional[BitstreamResult]
    visualizations: dict  # waveform/spectrum/waterfall/constellation arrays (downsampled)
