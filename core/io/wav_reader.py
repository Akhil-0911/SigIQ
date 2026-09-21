"""Reader for .wav files. Mono -> treated as a real-valued IF/audio signal
(Hilbert-transformed to complex baseband). Stereo -> channel 0/1 treated as I/Q
(a common convention for SDR recordings saved as stereo WAV)."""
import numpy as np
from scipy.io import wavfile
from scipy.signal import hilbert

from core.pipeline.models import RawSignal


def read_wav(path: str, center_frequency: float = 0.0, iq_stereo: bool = True) -> RawSignal:
    sample_rate, data = wavfile.read(path)

    if data.dtype.kind in ("i", "u"):
        info = np.iinfo(data.dtype)
        scale = max(abs(info.min), info.max)
        data = data.astype(np.float64) / scale
    else:
        data = data.astype(np.float64)

    if data.ndim == 1:
        channels = 1
        samples = hilbert(data)  # analytic signal -> complex baseband approximation
    else:
        channels = data.shape[1]
        if iq_stereo and channels == 2:
            samples = data[:, 0] + 1j * data[:, 1]
        else:
            samples = hilbert(data[:, 0])

    return RawSignal(
        samples=samples.astype(np.complex128),
        sample_rate=float(sample_rate),
        source_format="wav",
        center_frequency=float(center_frequency),
        bit_depth=None,
        channels=channels,
        filename=path,
    )
