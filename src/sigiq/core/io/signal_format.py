"""IQ raw-format detection helpers."""
import numpy as np

# byte-width -> numpy dtype for interleaved I,Q samples
DTYPE_MAP = {
    "int8": np.int8,
    "uint8": np.uint8,
    "int16": np.int16,
    "float32": np.float32,
    "float64": np.float64,
}


def dtype_for(fmt: str) -> np.dtype:
    if fmt not in DTYPE_MAP:
        raise ValueError(f"Unsupported IQ sample format '{fmt}'. Choose one of {list(DTYPE_MAP)}")
    return np.dtype(DTYPE_MAP[fmt])


def normalize_iq(raw: np.ndarray, dtype_name: str) -> np.ndarray:
    """Scale integer sample types to float32 in [-1, 1]; passthrough for float types."""
    if dtype_name in ("float32", "float64"):
        return raw.astype(np.complex128)
    info = np.iinfo(DTYPE_MAP[dtype_name])
    scale = max(abs(info.min), info.max)
    i = raw[0::2].astype(np.float64) / scale
    q = raw[1::2].astype(np.float64) / scale
    n = min(len(i), len(q))
    return (i[:n] + 1j * q[:n])
