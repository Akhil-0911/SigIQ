"""Ground-truth accuracy check: build signals with known modulation, symbol
rate and bits, run them through the real pipeline, and measure how close the
output is to the known truth (not just 'best hypothesis label matches')."""
import numpy as np

from sigiq.core.pipeline.models import RawSignal
from sigiq.core.pipeline.pipeline_config import PipelineConfig
from sigiq.core.pipeline.analyzer import run_pipeline


def make_signal(modulation, n_symbols=1000, sps=8, sample_rate=48000.0, snr_db=20.0, seed=0):
    rng = np.random.default_rng(seed)
    true_symbol_rate = sample_rate / sps

    if modulation == "BPSK":
        bits = rng.integers(0, 2, n_symbols)
        symbols = 2 * bits - 1
    elif modulation == "QPSK":
        # Gray-coded like the PSK demodulator: bits (g1, g0) sit at angle index i
        # where g = i ^ (i >> 1), i.e. index order 00, 01, 11, 10
        gray_to_index = {0: 0, 1: 1, 3: 2, 2: 3}
        pairs = rng.integers(0, 4, n_symbols)
        bits = np.array([[(p >> 1) & 1, p & 1] for p in pairs]).flatten()
        symbols = np.exp(1j * (2 * np.pi * np.array([gray_to_index[p] for p in pairs]) / 4 + np.pi / 4))
    elif modulation == "16-QAM":
        levels = rng.integers(0, 16, n_symbols)
        bits = np.array([[(l >> i) & 1 for i in range(3, -1, -1)] for l in levels]).flatten()
        side = 4
        i_val = (levels % side) * 2 - (side - 1)
        q_val = (levels // side) * 2 - (side - 1)
        symbols = (i_val + 1j * q_val)
        symbols = symbols / np.sqrt(np.mean(np.abs(symbols) ** 2))
    elif modulation == "2-FSK":
        bits = rng.integers(0, 2, n_symbols)
        dev = 3000.0
        phase = np.cumsum(2 * np.pi * np.where(np.repeat(bits, sps) == 1, dev, -dev) / sample_rate)
        symbols = None
    else:
        raise ValueError(modulation)

    if modulation == "2-FSK":
        baseband = np.exp(1j * phase)
    else:
        baseband = np.repeat(symbols, sps).astype(np.complex128)

    signal_power = np.mean(np.abs(baseband) ** 2)
    noise_power = signal_power / (10 ** (snr_db / 10))
    noise = np.sqrt(noise_power / 2) * (rng.standard_normal(len(baseband)) + 1j * rng.standard_normal(len(baseband)))
    samples = baseband + noise

    return samples, bits, true_symbol_rate


def bit_error_rate(true_bits, recovered_bits):
    """Best-case BER: recovered demod bits can be phase/offset ambiguous
    (e.g. BPSK 180 deg flip, symbol timing off-by-one), so compare both the
    bitstream and its logical inverse, at the best of a small set of offsets,
    and report the minimum BER found -- this reports the demodulator's raw
    symbol-decision accuracy, not phase/frame synchronization."""
    n = min(len(true_bits), len(recovered_bits))
    if n == 0:
        return 1.0, 0
    best_ber = 1.0
    for offset in range(0, min(4, len(recovered_bits) - n + 1)):
        window = recovered_bits[offset:offset + n]
        for candidate in (window, 1 - window):
            errors = np.sum(true_bits[:n] != candidate)
            ber = errors / n
            best_ber = min(best_ber, ber)
    return best_ber, n


def run_case(modulation, snr_db, seed=0):
    samples, true_bits, true_symbol_rate = make_signal(modulation, snr_db=snr_db, seed=seed)
    sample_rate = 48000.0

    raw = RawSignal(samples=samples, sample_rate=sample_rate, source_format="iq",
                     center_frequency=0.0, filename=f"{modulation}_{snr_db}dB.iq")
    config = PipelineConfig.from_dict({
        "analysis": {"mode": "automatic", "re_estimate_enabled": True},
        "modulations": ["BPSK", "QPSK", "16-QAM", "2-FSK", "4-FSK"],
        "deinterleaving": {"enabled": False},
        "fec": {"enabled": False},
    })

    result = run_pipeline(raw, config)

    true_sr_pct_err = abs(result.estimate.symbol_rate - true_symbol_rate) / true_symbol_rate * 100
    modulation_correct = result.best_hypothesis is not None and result.best_hypothesis.modulation == modulation

    ber, n_compared = (1.0, 0)
    if result.best_hypothesis is not None and result.best_hypothesis.demodulation_result is not None:
        ber, n_compared = bit_error_rate(true_bits, result.best_hypothesis.demodulation_result)

    return {
        "modulation": modulation,
        "snr_db": snr_db,
        "predicted_modulation": result.best_hypothesis.modulation if result.best_hypothesis else None,
        "modulation_correct": modulation_correct,
        "true_symbol_rate": true_symbol_rate,
        "estimated_symbol_rate": result.estimate.symbol_rate,
        "symbol_rate_pct_error": true_sr_pct_err,
        "estimated_snr_db": result.estimate.snr_db,
        "score": result.best_hypothesis.score if result.best_hypothesis else None,
        "ber": ber,
        "n_bits_compared": n_compared,
    }


def _deterministic_seed(modulation: str, snr_db: float) -> int:
    """Python's built-in hash() is randomized per-process (PYTHONHASHSEED),
    so hash((modulation, snr_db)) gives a DIFFERENT seed on every run --
    silently making this whole report non-reproducible. Use a fixed,
    deterministic seed instead so results are comparable run to run."""
    import zlib
    return zlib.crc32(f"{modulation}:{snr_db}".encode()) % 1000


def main():
    cases = []
    for modulation in ["BPSK", "QPSK", "16-QAM", "2-FSK"]:
        for snr_db in [25.0, 15.0, 5.0]:
            cases.append(run_case(modulation, snr_db, seed=_deterministic_seed(modulation, snr_db)))

    header = f"{'Modulation':10} {'SNR(dB)':8} {'Predicted':10} {'Correct':8} {'True SymRate':13} {'Est SymRate':13} {'SR err%':8} {'Est SNR':8} {'Score':6} {'BER':8}"
    print(header)
    print("-" * len(header))
    n_correct = 0
    for c in cases:
        print(f"{c['modulation']:10} {c['snr_db']:8.1f} {str(c['predicted_modulation']):10} "
              f"{str(c['modulation_correct']):8} {c['true_symbol_rate']:13.1f} {c['estimated_symbol_rate']:13.1f} "
              f"{c['symbol_rate_pct_error']:8.1f} {c['estimated_snr_db']:8.2f} "
              f"{(c['score'] or 0):6.2f} {c['ber']:8.4f}")
        n_correct += int(c["modulation_correct"])

    print()
    print(f"Modulation classification accuracy: {n_correct}/{len(cases)} ({100 * n_correct / len(cases):.0f}%)")
    mean_sr_err = np.mean([c["symbol_rate_pct_error"] for c in cases])
    print(f"Mean symbol-rate estimation error: {mean_sr_err:.1f}%")
    mean_ber = np.mean([c["ber"] for c in cases])
    print(f"Mean BER (best-case alignment) across all cases: {mean_ber:.4f}")


if __name__ == "__main__":
    main()
