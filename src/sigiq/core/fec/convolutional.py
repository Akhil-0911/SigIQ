import numpy as np

# Standard rate-1/2, K=7 convolutional code (polynomials 171, 133 octal) --
# the same code used by many satellite/DVB/802.11 links, useful as a
# reference encoder for testing the Viterbi decoder.
CONSTRAINT_LENGTH = 7
POLY_G1 = 0b1111001  # 171 octal
POLY_G2 = 0b1011011  # 133 octal


def _parity(x: int) -> int:
    return bin(x).count("1") % 2


def convolutional_encode(bits: np.ndarray, poly1: int = POLY_G1, poly2: int = POLY_G2,
                          constraint_length: int = CONSTRAINT_LENGTH) -> np.ndarray:
    """Rate-1/2 convolutional encoder. Output is interleaved [g1_0, g2_0, g1_1, g2_1, ...]."""
    shift_reg = 0
    out = []
    for bit in bits:
        shift_reg = ((shift_reg << 1) | int(bit)) & ((1 << constraint_length) - 1)
        out.append(_parity(shift_reg & poly1))
        out.append(_parity(shift_reg & poly2))
    return np.array(out, dtype=np.uint8)
