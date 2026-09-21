import numpy as np


def _prn_permutation(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.permutation(n)


def interleave_pseudo_random(bits: np.ndarray, seed: int = 42) -> np.ndarray:
    perm = _prn_permutation(len(bits), seed)
    out = np.zeros_like(bits)
    out[perm] = bits
    return out


def deinterleave_pseudo_random(bits: np.ndarray, seed: int = 42) -> np.ndarray:
    perm = _prn_permutation(len(bits), seed)
    return bits[perm]
