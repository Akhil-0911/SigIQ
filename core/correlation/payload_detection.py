import numpy as np


def extract_payload(bits: np.ndarray, header_offset: int, header_length: int,
                     payload_length: int = None) -> np.ndarray:
    """Everything after the detected header, optionally truncated to payload_length."""
    start = header_offset + header_length
    if start >= len(bits):
        return np.array([], dtype=np.uint8)
    end = start + payload_length if payload_length else len(bits)
    return bits[start:min(end, len(bits))]
