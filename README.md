# Signal Analysis Workstation

Automated analysis of `.iq` / `.wav` signal recordings: parameter extraction
(sample rate, symbol rate, carrier, bandwidth, SNR), modulation identification,
demodulation (PSK/QAM/FSK), de-interleaving (block/convolutional/diagonal/
pseudo-random), FEC decoding (Viterbi, Reed-Solomon, concatenated, LDPC) and
bit-stream correlation for header/payload identification.

## Architecture

```
gui/          Tkinter desktop app: file input, configuration, plots, results
core/         the DSP engine: numpy/scipy only, no UI dependencies
```

`core/` is directly testable and runnable on its own -- see
`tests/test_pipeline_smoke.py`, which builds a synthetic BPSK signal and
runs it through the full pipeline:

```bash
python -m tests.test_pipeline_smoke
```

The desktop app runs `core.pipeline.analyzer.run_pipeline()` in a background
thread and renders the result; it does no DSP itself.

### Pipeline stages (`core/pipeline/analyzer.py`)

```
Input Loader (iq_reader/wav_reader)
  -> Preprocessing (DC removal, power normalization)
  -> Isolation (energy-based segmentation, strongest-channel detection)
  -> Feature Extraction (spectral, temporal, statistical)
  -> Parameter Estimation (sample rate, symbol rate, carrier, bandwidth, SNR)
  -> Candidate Generation (ModulationCandidate registry: BPSK/QPSK/16-QAM/2-FSK/4-FSK)
  -> Evidence Scoring (EVM + constellation clustering -> score, no hardcoded branches)
  -> Demodulation (best-scoring candidate's bits)
  -> De-interleaving x FEC combination search (scored by header correlation + FEC success)
  -> Bit-stream Correlation (cross-correlation against known sync words)
  -> Header / Payload identification
```

## Running the app

```bash
pip install -r requirements.txt
python main.py
```

Single window: left panel for file input and configuration, right panel with
two tabs (Visualization; Analysis, which shows parameters, hypotheses, recovery and results together). Hypotheses
and the full report can be exported as CSV / JSON. Try it with the files in
`samples/`.

## Accuracy (measured, not claimed)

`tests/test_accuracy_report.py` builds signals with known ground-truth
modulation/symbol-rate/bits, runs them through the real pipeline, and
compares the output numerically (not just "best hypothesis label matches").
Run it with `python -m tests.test_accuracy_report`.

Measured with fixed, deterministic seeds (reproducible run to run), across
BPSK/QPSK/16-QAM/2-FSK at 5/15/25 dB SNR: modulation classification 6/12
(50%), mean symbol-rate error ~4.2%, mean BER (best-case alignment) ~0.33.
Symbol-rate estimation is essentially exact (0% error) at 15/25 dB SNR for
every modulation tested, including FSK. Most classification errors are at
5 dB SNR (low-SNR modulation confusion) and, less often, 16-QAM at 15 dB.
Earlier figures of 67% / 0.25 came from a non-deterministic test seed and
should not be relied on.

Four real correctness bugs were found and fixed via this test during
development, in case similar patterns turn up elsewhere:
1. The symbol-rate estimator originally used only `|signal|^2` cyclic
   spectrum, which is flat (carries no symbol-rate signal at all) for
   constant-envelope modulations like unshaped BPSK/QPSK. Fixed by adding a
   transition-energy (`|diff(signal)|^2`) estimator and picking whichever
   shows the more confident spectral line.
2. That transition-energy estimator was itself blind to symmetric-deviation
   FSK (e.g. +dev/-dev tones): `|diff(signal)|` tracks `|instantaneous
   frequency|`, and both tones have the same magnitude, so it saw no
   symbol-rate structure at all. Fixed by adding a third, FSK-specific
   feature -- transitions of the *signed* instantaneous frequency, which
   genuinely jumps at every tone change regardless of deviation symmetry
   (`core/feature_extraction/cyclostationary.py`).
3. PSK/QAM residual-phase correction used the classic M-th-power ("Costas")
   method, which only works for constant-modulus (PSK) signals — applied to
   QAM (amplitude varies), it introduced a large *spurious* rotation even on
   signals with zero actual carrier offset, wrecking EVM. Fixed with a
   decision-directed phase search compared against the real constellation
   instead (`core/demodulation/synchronization.py`). EVM for all modulations
   is also now normalized by each constellation's own point spacing, so
   higher-order constellations (denser point grids) don't get an unfair
   apparent-accuracy edge just from having closer-together points.
4. FSK's evidence (evm) was ultimately derived from the same noisy data it
   was judging (percentile range of the observed tones), so it could look
   "reasonable" even on a non-FSK signal purely from noise scatter. Fixed by
   rejecting the fit outright when the observed tone spread is no larger
   than pure AWGN phase noise would produce at the measured SNR (a
   Cramer-Rao-style theoretical expectation, not another self-referential
   statistic) — see `core/demodulation/fsk.py`.

## Known limitations (documented, not hidden)

- **Low-SNR (~5 dB) modulation confusion.** FSK is still occasionally
  over-selected over the true modulation at 5 dB SNR specifically. The
  SNR-aware noise-rejection check in `core/demodulation/fsk.py` relies on
  `core/estimation/snr.py`'s own SNR estimate, which is itself a crude
  spectral estimate that tends to overestimate the true SNR at low SNR —
  when it does, the noise-rejection threshold is set too permissively.
  Tightening the SNR estimator itself would likely fix most of this.
- **LDPC** (`core/fec/ldpc.py`) is a small regular-code bit-flipping decoder
  built for this project, not a standards-compliant 5G/DVB-S2 LDPC stack.
- **De-interleaving parameter search** in automatic mode tries default
  row/column and branch/delay parameters per method; it does not brute-force
  every possible interleaver depth. Use Manual mode with known parameters
  for a specific known link.
- Timing recovery decimates at an integer samples-per-symbol phase (best
  average-energy phase); it does not interpolate for non-integer
  samples-per-symbol ratios, which costs some accuracy when sample_rate /
  symbol_rate isn't close to a whole number.

## Project layout

```
core/            signal-processing engine
  io/              read .iq / .wav, parse metadata
  preprocessing/   normalization, denoising, resampling, retry profiles
  isolation/       spectrum, band/channel detection, segmentation
  feature_extraction/  spectral, temporal, statistical, cyclostationary
  estimation/      sample rate, symbol rate, carrier, SNR
  hypotheses/      candidate generation (modulation, FEC, interleaving)
  scoring/         evidence scoring and confidence
  demodulation/    PSK, QAM, FSK, synchronization
  deinterleaving/  block, convolutional, diagonal, pseudo-random
  fec/             Viterbi, Reed-Solomon, concatenated, LDPC
  correlation/     bit-stream correlation, header/payload detection
  pipeline/        orchestrator (analyzer), config, stages, result models
gui/             Tkinter desktop UI (app.py, plots.py, style.py); launched by main.py
tests/           pipeline smoke test and accuracy report
samples/         small synthetic .iq / .wav files for trying the app
docs/            design notes
main.py           entry point (launches the GUI)
requirements.txt
```
