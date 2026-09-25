import numpy as np


def interleave_diagonal(bits: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Write row-wise, read out along diagonals (wrapping) -- common in HF/satellite links."""
    n = rows * cols
    padded = np.zeros(n, dtype=bits.dtype)
    padded[: min(len(bits), n)] = bits[:n]
    matrix = padded.reshape(rows, cols)
    out = np.zeros(n, dtype=bits.dtype)
    idx = 0
    for d in range(cols):
        for r in range(rows):
            c = (d + r) % cols
            out[idx] = matrix[r, c]
            idx += 1
    return out


def deinterleave_diagonal(bits: np.ndarray, rows: int, cols: int) -> np.ndarray:
    n = rows * cols
    padded = np.zeros(n, dtype=bits.dtype)
    padded[: min(len(bits), n)] = bits[:n]
    matrix = np.zeros((rows, cols), dtype=bits.dtype)
    idx = 0
    for d in range(cols):
        for r in range(rows):
            c = (d + r) % cols
            matrix[r, c] = padded[idx]
            idx += 1
    return matrix.flatten()
