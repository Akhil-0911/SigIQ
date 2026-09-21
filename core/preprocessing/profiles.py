"""Alternative preprocessing/isolation parameter sets for the pipeline's
re-estimation loop: when the best-scoring hypothesis is weak, the analyzer
retries with the next profile instead of giving up on the first pass."""
from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.preprocessing.normalization import remove_dc, normalize_power
from core.preprocessing.noise_reduction import spectral_gate, moving_average_denoise


@dataclass
class PreprocessingProfile:
    name: str
    denoise: Optional[str]           # None | "spectral_gate" | "moving_average"
    segment_threshold_db: float      # passed to segment_by_energy


PREPROCESSING_PROFILES = [
    PreprocessingProfile(name="default", denoise=None, segment_threshold_db=6.0),
    PreprocessingProfile(name="denoised_lenient_segmentation", denoise="spectral_gate", segment_threshold_db=3.0),
    PreprocessingProfile(name="denoised_strict_segmentation", denoise="moving_average", segment_threshold_db=10.0),
]


def apply_profile(samples: np.ndarray, sample_rate: float, profile: PreprocessingProfile) -> np.ndarray:
    samples = remove_dc(samples)
    samples = normalize_power(samples)
    if profile.denoise == "spectral_gate":
        samples = spectral_gate(samples, sample_rate)
    elif profile.denoise == "moving_average":
        samples = moving_average_denoise(samples)
    return samples
