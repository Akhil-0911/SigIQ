import numpy as np


def interleave_convolutional(bits: np.ndarray, num_branches: int = 4, delay_step: int = 4) -> np.ndarray:
    """Ramsey/Forney-style convolutional interleaver: branch b delays by b*delay_step bits.
    Bits are distributed round-robin across branches, each branch is a FIFO shift register."""
    branches = [[] for _ in range(num_branches)]
    fifos = [[0] * (b * delay_step) for b in range(num_branches)]
    out = []
    for i, bit in enumerate(bits):
        b = i % num_branches
        fifos[b].append(bit)
        out.append(fifos[b].pop(0))
    return np.array(out, dtype=bits.dtype)


def deinterleave_convolutional(bits: np.ndarray, num_branches: int = 4, delay_step: int = 4) -> np.ndarray:
    """Inverse: branch b delays by (num_branches-1-b)*delay_step bits."""
    fifos = [[0] * ((num_branches - 1 - b) * delay_step) for b in range(num_branches)]
    out = []
    for i, bit in enumerate(bits):
        b = i % num_branches
        fifos[b].append(bit)
        out.append(fifos[b].pop(0))
    return np.array(out, dtype=bits.dtype)
