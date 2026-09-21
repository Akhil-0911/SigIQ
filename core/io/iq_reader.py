"""Reader for raw .iq files (interleaved I,Q binary, no header)."""
import numpy as np

from core.io.signal_format import dtype_for, normalize_iq
from core.pipeline.models import RawSignal


def read_iq(path: str, sample_rate: float, center_frequency: float = 0.0,
            dtype_name: str = "float32") -> RawSignal:
    """Load a headerless .iq file of interleaved I/Q samples.

    sample_rate and dtype must be supplied by the caller/UI since raw .iq
    files carry no metadata (this is exactly the limitation the PS calls out).
    """
    dt = dtype_for(dtype_name)
    raw = np.fromfile(path, dtype=dt)
    if len(raw) % 2 != 0:
        raw = raw[:-1]
    samples = normalize_iq(raw, dtype_name)
    return RawSignal(
        samples=samples,
        sample_rate=float(sample_rate),
        source_format="iq",
        center_frequency=float(center_frequency),
        bit_depth=dt.itemsize * 8,
        channels=1,
        filename=path,
    )
