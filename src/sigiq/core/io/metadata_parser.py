"""Extracts cheap, non-DSP metadata from uploaded files for the file API."""
import os
import wave


def parse_wav_metadata(path: str) -> dict:
    with wave.open(path, "rb") as w:
        return {
            "format": "wav",
            "sample_rate": w.getframerate(),
            "channels": w.getnchannels(),
            "sample_width_bytes": w.getsampwidth(),
            "num_frames": w.getnframes(),
            "duration_sec": w.getnframes() / float(w.getframerate()),
            "size_bytes": os.path.getsize(path),
        }


def parse_iq_metadata(path: str, sample_rate: float = None, dtype_name: str = "float32") -> dict:
    from sigiq.core.io.signal_format import dtype_for
    size_bytes = os.path.getsize(path)
    itemsize = dtype_for(dtype_name).itemsize
    num_samples = size_bytes // (itemsize * 2)
    meta = {
        "format": "iq",
        "dtype": dtype_name,
        "size_bytes": size_bytes,
        "num_samples": num_samples,
    }
    if sample_rate:
        meta["sample_rate"] = sample_rate
        meta["duration_sec"] = num_samples / float(sample_rate)
    return meta


def parse_metadata(path: str, sample_rate: float = None, dtype_name: str = "float32") -> dict:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wav":
        return parse_wav_metadata(path)
    return parse_iq_metadata(path, sample_rate, dtype_name)
