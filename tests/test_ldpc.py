"""LDPC (IEEE 802.11n n=648, R=3/4): encode/decode round trip and negative control."""
import numpy as np

from core.fec.ldpc import ldpc_encode, ldpc_decode, parity_check_matrix, K, N


def test_ldpc():
    rng = np.random.default_rng(1)
    info = rng.integers(0, 2, K * 3).astype(np.uint8)
    cw = ldpc_encode(info)
    assert len(cw) == N * 3
    h = parity_check_matrix().astype(int)
    assert not np.any((h @ cw[:N].astype(int)) % 2), "encoder output must satisfy H"

    stream = np.concatenate([rng.integers(0, 2, 100).astype(np.uint8), cw])  # unknown start offset
    noisy = stream.copy()
    flips = rng.choice(len(noisy), size=int(0.01 * len(noisy)), replace=False)
    noisy[flips] ^= 1

    res = ldpc_decode(noisy)
    assert res["success"], res
    n_out = min(len(res["bits"]), len(info))
    assert np.array_equal(res["bits"][:n_out], info[:n_out]), "decoded info must equal transmitted info"
    assert res["offset"] == 100

    junk = rng.integers(0, 2, N * 4).astype(np.uint8)
    assert not ldpc_decode(junk)["success"], "random bits must not be reported as decoded"
    print(f"OK: LDPC round trip at 1% BER (offset {res['offset']}, {res['blocks']} blocks); random stream rejected.")


if __name__ == "__main__":
    test_ldpc()
