"""Modulation candidates as objects (per Idea.txt §8) rather than hardcoded
if/else branches. Each candidate knows how to demodulate itself and extract
real evidence; the scorer (core/scoring) turns evidence into a score."""
import numpy as np

from core.demodulation.psk import demodulate_psk
from core.demodulation.qam import demodulate_qam
from core.demodulation.fsk import demodulate_fsk
from core.feature_extraction.constellation_features import constellation_features
from core.demodulation.synchronization import symbol_decimate


class ModulationCandidate:
    name = "base"

    def __init__(self, sample_rate: float, symbol_rate: float, snr_db: float = None):
        self.sample_rate = sample_rate
        self.symbol_rate = symbol_rate
        self.snr_db = snr_db

    def demodulate(self, samples: np.ndarray) -> dict:
        raise NotImplementedError

    def extract_evidence(self, samples: np.ndarray, demod_result: dict) -> dict:
        symbols = demod_result.get("symbols", np.array([]))
        cf = constellation_features(symbols) if len(symbols) else {"compactness": 1.0, "best_order": 0}
        return {
            "evm": demod_result.get("evm", 1.0),
            "constellation_compactness": cf["compactness"],
            "expected_order": demod_result.get("order", 0),
            "matched_cluster_order": cf["best_order"],
        }


class BPSKCandidate(ModulationCandidate):
    name = "BPSK"

    def demodulate(self, samples):
        return demodulate_psk(samples, self.sample_rate, self.symbol_rate, order=2)


class QPSKCandidate(ModulationCandidate):
    name = "QPSK"

    def demodulate(self, samples):
        return demodulate_psk(samples, self.sample_rate, self.symbol_rate, order=4)


class QAM16Candidate(ModulationCandidate):
    name = "16-QAM"

    def demodulate(self, samples):
        return demodulate_qam(samples, self.sample_rate, self.symbol_rate, order=16)


class FSK2Candidate(ModulationCandidate):
    name = "2-FSK"

    def demodulate(self, samples):
        return demodulate_fsk(samples, self.sample_rate, self.symbol_rate, order=2, snr_db=self.snr_db)


class FSK4Candidate(ModulationCandidate):
    name = "4-FSK"

    def demodulate(self, samples):
        return demodulate_fsk(samples, self.sample_rate, self.symbol_rate, order=4, snr_db=self.snr_db)


CANDIDATE_REGISTRY = [BPSKCandidate, QPSKCandidate, QAM16Candidate, FSK2Candidate, FSK4Candidate]


def build_candidates(sample_rate: float, symbol_rate: float, names: list = None, snr_db: float = None) -> list:
    registry = CANDIDATE_REGISTRY
    if names:
        registry = [c for c in CANDIDATE_REGISTRY if c.name in names]
    return [c(sample_rate, symbol_rate, snr_db) for c in registry]
