"""Reed-Solomon encode/decode over GF(256) via the `reedsolo` library."""
import numpy as np
import reedsolo


def _bits_to_bytes(bits: np.ndarray) -> bytes:
    n = (len(bits) // 8) * 8
    bits = bits[:n]
    return bytes(np.packbits(bits))


def _bytes_to_bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))


def rs_encode(bits: np.ndarray, nsym: int = 10) -> np.ndarray:
    rsc = reedsolo.RSCodec(nsym)
    encoded = rsc.encode(_bits_to_bytes(bits))
    return _bytes_to_bits(bytes(encoded))


def rs_decode(bits: np.ndarray, nsym: int = 10) -> dict:
    rsc = reedsolo.RSCodec(nsym)
    data = _bits_to_bytes(bits)
    try:
        decoded, decoded_full, errata_pos = rsc.decode(data)
        return {
            "bits": _bytes_to_bits(bytes(decoded)),
            "success": True,
            "errors_corrected": len(errata_pos),
        }
    except reedsolo.ReedSolomonError as e:
        return {"bits": np.array([], dtype=np.uint8), "success": False, "error": str(e)}
