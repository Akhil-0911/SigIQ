import numpy as np


def extract_payload(bits: np.ndarray, header_offset: int, header_length: int,
                     payload_length: int = None) -> np.ndarray:
    """Everything after the detected header, optionally truncated to payload_length."""
    start = header_offset + header_length
    if start >= len(bits):
        return np.array([], dtype=np.uint8)
    end = start + payload_length if payload_length else len(bits)
    return bits[start:min(end, len(bits))]


def bits_to_bytes(bits: np.ndarray) -> bytes:
    """Pack bits MSB-first into bytes; a trailing partial byte is dropped."""
    bits = np.asarray(bits, dtype=np.uint8)
    n = len(bits) // 8 * 8
    return np.packbits(bits[:n]).tobytes() if n else b""


def bits_to_hex(bits: np.ndarray, group: int = 1) -> str:
    """Hex dump of the packed bytes, `group` bytes per space-separated group."""
    raw = bits_to_bytes(bits).hex()
    step = group * 2
    return " ".join(raw[i:i + step] for i in range(0, len(raw), step))
