import numpy as np


def interleave_block(bits: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Write row-wise into a rows x cols matrix, read out column-wise."""
    n = rows * cols
    padded = np.zeros(n, dtype=bits.dtype)
    padded[: min(len(bits), n)] = bits[:n]
    matrix = padded.reshape(rows, cols)
    return matrix.T.flatten()


def deinterleave_block(bits: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Inverse of interleave_block: written column-wise, read out row-wise."""
    n = rows * cols
    padded = np.zeros(n, dtype=bits.dtype)
    padded[: min(len(bits), n)] = bits[:n]
    matrix = padded.reshape(cols, rows).T
    return matrix.flatten()
