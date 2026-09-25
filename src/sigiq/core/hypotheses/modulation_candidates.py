"""Modulation candidates as objects rather than hardcoded
if/else branches. Each candidate knows how to demodulate itself and extract
real evidence; the scorer (core/scoring) turns evidence into a score."""
import numpy as np

from sigiq.core.demodulation.psk import demodulate_psk, psk_constellation
from sigiq.core.demodulation.qam import demodulate_qam, qam_constellation
from sigiq.core.estimation.snr import envelope_kurtosis as _kurtosis_of
from sigiq.core.demodulation.fsk import demodulate_fsk
from sigiq.core.feature_extraction.constellation_features import constellation_features


class ModulationCandidate:
    name = "base"
    # envelope kurtosis of the noise-free signal, used by the M2M4 SNR estimator
    envelope_kurtosis = 1.0

    def __init__(self, sample_rate: float, symbol_rate: float):
        self.sample_rate = sample_rate
        self.symbol_rate = symbol_rate
        self.spectrum_samples = None   # unfiltered signal, set by the scorer

    def demodulate(self, samples: np.ndarray) -> dict:
        raise NotImplementedError

    def extract_evidence(self, samples: np.ndarray, demod_result: dict) -> dict:
        symbols = demod_result.get("symbols", np.array([]))
        cf = constellation_features(symbols) if len(symbols) else {"compactness": 1.0, "best_order": 0}
        return {
            "evm": demod_result.get("evm", 1.0),
            "expected_order": demod_result.get("order", 0),
            "matched_cluster_order": cf["best_order"],
        }


class BPSKCandidate(ModulationCandidate):
    name = "BPSK"
    envelope_kurtosis = _kurtosis_of(psk_constellation(2))

    def demodulate(self, samples):
        return demodulate_psk(samples, self.sample_rate, self.symbol_rate, order=2)


class QPSKCandidate(ModulationCandidate):
    name = "QPSK"
    envelope_kurtosis = _kurtosis_of(psk_constellation(4))

    def demodulate(self, samples):
        return demodulate_psk(samples, self.sample_rate, self.symbol_rate, order=4)


class QAM16Candidate(ModulationCandidate):
    name = "16-QAM"
    envelope_kurtosis = _kurtosis_of(qam_constellation(16))

    def demodulate(self, samples):
        return demodulate_qam(samples, self.sample_rate, self.symbol_rate, order=16)


class FSK2Candidate(ModulationCandidate):
    name = "2-FSK"

    def demodulate(self, samples):
        return demodulate_fsk(samples, self.sample_rate, self.symbol_rate, order=2,
                               spectrum_samples=self.spectrum_samples)


class FSK4Candidate(ModulationCandidate):
    name = "4-FSK"

    def demodulate(self, samples):
        return demodulate_fsk(samples, self.sample_rate, self.symbol_rate, order=4,
                               spectrum_samples=self.spectrum_samples)


CANDIDATE_REGISTRY = [BPSKCandidate, QPSKCandidate, QAM16Candidate, FSK2Candidate, FSK4Candidate]


def build_candidates(sample_rate: float, symbol_rate: float, names: list = None) -> list:
    registry = CANDIDATE_REGISTRY
    if names:
        registry = [c for c in CANDIDATE_REGISTRY if c.name in names]
    return [c(sample_rate, symbol_rate) for c in registry]
