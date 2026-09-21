# Signal Analysis Workstation

Automated analysis of `.iq` / `.wav` signal recordings: parameter extraction
(sample rate, symbol rate, carrier, bandwidth, SNR), modulation identification,
demodulation (PSK/QAM/FSK), de-interleaving (block/convolutional/diagonal/
pseudo-random), FEC decoding (Viterbi, Reed-Solomon, concatenated, LDPC) and
bit-stream correlation for header/payload identification.

## Architecture

Three independent layers, per the design in `Idea.txt`:

```
frontend/   plain HTML + CSS + JS (no framework, no build step)
backend/    FastAPI — upload, job orchestration, WebSocket progress, results
core/       the actual DSP engine — numpy/scipy, zero HTTP/UI dependencies
```

`core/` is directly testable and runnable on its own — see
`tests/core/test_pipeline_smoke.py`, which builds a synthetic BPSK signal and
runs it through the full pipeline with no server involved:

```bash
python -m tests.core.test_pipeline_smoke
```

The backend is a thin orchestrator: `POST /api/upload` stores the file,
`POST /api/analysis/start` runs `core.pipeline.analyzer.run_pipeline()` in a
worker thread and streams progress over `/ws/analysis/{job_id}`, and
`GET /api/results/{job_id}` returns the full `AnalysisResult`. The frontend
never does DSP — it only uploads, configures, polls/watches progress, and
renders results on `<canvas>`.

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

## Running it

```bash
# 1. Install backend deps (uses the "iqfile" conda env in this workspace)
pip install -r backend/requirements.txt

# 2. Start the server (also serves the frontend as static files)
python -m uvicorn backend.app.main:app --port 8000

# 3. Open http://localhost:8000/ in a browser
```

## Accuracy (measured, not claimed)

`tests/core/test_accuracy_report.py` builds signals with known ground-truth
modulation/symbol-rate/bits, runs them through the real pipeline, and
compares the output numerically (not just "best hypothesis label matches").
Run it with `python -m tests.core.test_accuracy_report`.

As of the current build, across BPSK/QPSK/16-QAM/2-FSK at 5/15/25 dB SNR:
modulation classification 8/12 (67%), mean symbol-rate error ~6%, mean BER
(best-case alignment) ~0.25. Symbol-rate estimation is now essentially exact
(0% error) at 15/25 dB SNR for every modulation tested, including FSK. At
25/15 dB SNR, BPSK/QPSK/16-QAM/2-FSK all demodulate correctly, several with
0% or near-0% BER. Remaining failures concentrate specifically at 5 dB SNR
(low-SNR modulation confusion is expected even for mature classifiers) and,
less often, 16-QAM at 15 dB.

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
- Analysis runs synchronously in a worker thread per job (in-memory job
  store); this is fine for a single-instance prototype, not a multi-worker
  deployment.

## Project layout

```
core/            independent signal-processing engine (see above)
backend/app/     FastAPI orchestration layer
frontend/        plain HTML/CSS/JS UI (7-panel workflow: Input -> Configuration
                 -> Visualization -> Automated Analysis -> Hypotheses -> Recovery -> Results)
tests/core/      standalone core pipeline tests
data/            uploads / intermediate / results (gitignored contents)
```