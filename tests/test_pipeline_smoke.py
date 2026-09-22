"""Runs the core signal-processing engine standalone (no FastAPI, no React) on
a synthetic BPSK signal, proving the pipeline is independently executable and
testable as required by the architecture."""
import numpy as np

from core.pipeline.models import RawSignal
from core.pipeline.pipeline_config import PipelineConfig
from core.pipeline.analyzer import run_pipeline


def make_synthetic_bpsk(n_symbols=800, sps=8, sample_rate=48000.0, snr_db=25.0, seed=1):
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, n_symbols)
    symbols = 2 * bits - 1  # BPSK: 0->-1, 1->+1
    upsampled = np.repeat(symbols, sps).astype(np.complex128)

    noise_power = 10 ** (-snr_db / 10)
    noise = np.sqrt(noise_power / 2) * (rng.standard_normal(len(upsampled)) + 1j * rng.standard_normal(len(upsampled)))
    return upsampled + noise, sample_rate


def print_progress(stage, percent, message):
    print(f"[{percent:3d}%] {stage}: {message}")


def main():
    samples, sample_rate = make_synthetic_bpsk()
    raw = RawSignal(samples=samples, sample_rate=sample_rate, source_format="iq",
                     center_frequency=0.0, filename="synthetic_bpsk.iq")

    config = PipelineConfig.from_dict({
        "analysis": {"mode": "automatic"},
        "modulations": ["BPSK", "QPSK", "16-QAM", "2-FSK", "4-FSK"],
        "deinterleaving": {"enabled": True, "types": ["block", "pseudo_random"]},
        "fec": {"enabled": True, "types": ["convolutional_viterbi"]},
    })

    result = run_pipeline(raw, config, progress_cb=print_progress)

    print("\n--- Result ---")
    print("Estimated symbol rate:", result.estimate.symbol_rate)
    print("Estimated SNR (dB):", result.estimate.snr_db)
    print("Top hypotheses:")
    for h in result.hypotheses:
        print(f"  {h.modulation:8s} score={h.score:.3f} confidence={h.confidence}%")
    assert result.best_hypothesis is not None
    assert result.best_hypothesis.modulation == "BPSK", f"expected BPSK, got {result.best_hypothesis.modulation}"
    print("\nOK: BPSK correctly identified as best hypothesis.")


if __name__ == "__main__":
    main()
