<div align="center">

# 📡 Signal Analysis Workstation

**A Tkinter desktop application and numpy/scipy DSP engine for automated `.iq` / `.wav` signal analysis.**

Parameter estimation, modulation identification, demodulation, de-interleaving, FEC decoding, and
bit-stream correlation, with every result labelled by where it actually came from.

![Python](https://img.shields.io/badge/python-3.10-blue?logo=python&logoColor=white)
![GUI](https://img.shields.io/badge/GUI-Tkinter-orange)
![DSP](https://img.shields.io/badge/DSP-numpy%20%2F%20scipy-013243?logo=numpy&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![Tests](https://img.shields.io/badge/tests-15%2F15%20passing-brightgreen)
![No hardcoding](https://img.shields.io/badge/results-never%20hardcoded-critical)

</div>

---

## Contents

1. [Overview](#1-overview)
2. [Design principles](#2-design-principles)
3. [Architecture](#3-architecture)
4. [Pipeline stages](#4-pipeline-stages)
5. [Installation](#5-installation)
6. [Usage](#6-usage)
7. [Interface walkthrough](#7-interface-walkthrough)
8. [Accuracy](#8-accuracy)
9. [Known limitations](#9-known-limitations)
10. [Project layout](#10-project-layout)
11. [Testing](#11-testing)

---

## 1. Overview

Given a raw `.iq` (headerless interleaved I/Q binary) or `.wav` recording, this tool determines,
end to end and with no manual DSP work:

| Question | How it is answered |
|---|---|
| What modulation is being used? | Demodulates against every candidate (BPSK, QPSK, 16-QAM, 2-FSK, 4-FSK) and scores which one the data actually supports best. |
| What are the real transmission parameters? | Sample rate, symbol rate, carrier offset, bandwidth, and SNR, each labelled as user-provided, read from a file header, estimated, or inferred from the winning candidate. |
| Are the bits interleaved and/or FEC-coded? | A joint search over de-interleaving (block, convolutional, diagonal, pseudo-random) and FEC (Viterbi, Reed-Solomon, concatenated, LDPC), kept only if a header match or a verifying decoder supports it. |
| Is there a recognizable header/payload? | Correlation against known sync words (CCSDS ASM, HDLC flag, Barker-11), backed by a statistical false-alarm test, not a similarity guess. |

If the evidence is weak, or the signal is ambiguous between two hypotheses, the tool says so
(`ambiguous` or `insufficient_evidence`) instead of forcing a confident-looking wrong answer.

## 2. Design principles

This project was built against one rule: **never hardcode a detected result, confidence value, sample
rate, FEC outcome, or plot value.** Every number shown in the UI is computed from the loaded signal, on
that run, by the code in `core/`. Some concrete guarantees that follow from that rule:

- A "decoded" result only appears if a decoder's parity/syndrome check genuinely passes, or a Viterbi
  decode's bit-mismatch rate is statistically far enough below what a random stream produces (a z-test
  against a random-stream baseline, not a fixed threshold).
- A "header found" result only appears if the correlation peak clears a binomial false-alarm test at
  p < 0.01, Bonferroni-corrected across the sync words tried. An 8-bit pattern matching by chance in a
  few thousand random bits is expected, and is not reported as a find.
- Pure noise input is reported as `insufficient_evidence` with nothing recovered, verified by a test
  that feeds the pipeline seeded random noise and asserts nothing downstream fires.
- Soft-decision (LLR) information from demodulation is threaded through de-interleaving into Viterbi/LDPC
  decoding when available, instead of being discarded in favor of hard 0/1 bits. Measured to cut output
  BER from 14.6% to 0.4% at the same SNR in one Viterbi test case.

## 3. Architecture

```
gui/          Tkinter desktop app: file input, configuration, plots, results
core/         the DSP engine: numpy/scipy only, no UI dependencies
```

```mermaid
flowchart LR
    A[".iq / .wav file"] --> B["gui/app.py<br/>file input + configuration"]
    B --> C["core.pipeline.analyzer.run_pipeline()<br/>background thread"]
    C --> D["AnalysisResult<br/>parameters, hypotheses, recovery, provenance"]
    D --> E["gui/plots.py + result tabs<br/>render only, no DSP"]
```

`core/` has no import of `gui/`, and is directly testable and runnable on its own. See
`tests/test_pipeline_smoke.py`, which builds a synthetic BPSK signal and runs it through the full
pipeline:

```bash
python -m tests.test_pipeline_smoke
python -m tests.test_behaviour
python -m tests.test_ldpc
```

The desktop app runs `core.pipeline.analyzer.run_pipeline()` in a background thread and renders the
result. It performs no DSP itself.

## 4. Pipeline stages

Implemented in `core/pipeline/analyzer.py`.

```mermaid
flowchart TD
    L["Input Loader<br/>iq_reader / wav_reader / metadata_parser"] --> P["Preprocessing profile<br/>DC removal, power normalization, optional denoising"]
    P --> I["Isolation<br/>energy segmentation, strongest-channel detection"]
    I --> F["Feature Extraction<br/>spectral, temporal, statistical"]
    F --> E["Parameter Estimation<br/>symbol rate, carrier offset, bandwidth"]
    E --> G["Candidate Generation<br/>BPSK / QPSK / 16-QAM / 2-FSK / 4-FSK"]
    G --> S["Candidate processing + Evidence Scoring<br/>constellation_fit, order_consistency, timing_fit"]
    S --> W{"Weak or ambiguous,<br/>and attempts remain?"}
    W -- yes --> R["Re-estimation search<br/>bounded search over symbol rate,<br/>carrier offset, low-pass cutoff"]
    R --> S
    W -- no --> V["Best-supported hypothesis + verdict"]
    V --> D["De-interleaving x FEC decoding<br/>joint search, ranked by header correlation + FEC success"]
    D --> H["Known sync-word matching<br/>CCSDS ASM, HDLC flag, Barker-11"]
    H --> PL["Header / payload extraction"]
    PL --> RI["Recovered information"]
```

Reference form of the same flow, with the detail each arrow's box above summarizes:

```
Input Loader (iq_reader / wav_reader, metadata_parser)
  -> Preprocessing profile (DC removal, power normalization, optional denoising)
  -> Isolation (energy-based segmentation, strongest-channel detection)
  -> Feature Extraction (spectral, temporal, statistical)
  -> Parameter Estimation (symbol rate, carrier offset, bandwidth)
  -> Candidate Generation (BPSK / QPSK / 16-QAM / 2-FSK / 4-FSK candidate objects)
  -> Candidate-specific processing + Evidence Scoring
       each candidate is demodulated; per-metric scores are kept:
       constellation_fit, order_consistency, timing_fit
  -> Re-estimation search (only if weak or ambiguous)
       bounded search over symbol rate, carrier offset and low-pass cutoff,
       objective = best score, stops when an iteration gains < 0.005 or after
       3 iterations; if still weak, the next preprocessing profile is tried
  -> Best-supported hypothesis + verdict
       determined / ambiguous / insufficient_evidence / user_selected
  -> De-interleaving x FEC decoding, searched jointly
       ranked by header correlation + FEC success; reported "undetermined"
       if nothing shows real evidence
  -> Known sync-word matching (CCSDS ASM, HDLC flag, Barker-11)
       a match counts only if its false-alarm probability is < 0.01; both
       bit polarities are tried and an inverted stream is corrected
  -> Header / payload extraction (hex, bytes and bits)
  -> Recovered information
```

Notes on what this does and does not do:

- Demodulation happens per candidate during scoring, not once after the winner is chosen. Only the
  winner's bits (and soft LLRs, when available) are recovered further.
- De-interleaving and FEC are a joint search, not a fixed chain. Header correlation is used inside that
  search as well as afterwards.
- Every reported parameter has a source: user-provided, metadata-derived, estimated, candidate-inferred
  or tested, or decoded. A manual choice is never presented as detected.
- With no symbol clock, or too little evidence, the result says so (`insufficient_evidence`) and nothing
  is recovered. Pure noise is handled this way.
- Header detection recognises three fixed sync words. It does not discover an unknown frame structure.
- Visualization data (waveform, PSD, waterfall, constellation) is produced by the pipeline. `gui/plots.py`
  only renders it and is not part of recovery.

### 4.1 Verdict decision logic

Implemented in `core/scoring/verdict.py`, checked in this exact order:

```mermaid
flowchart TD
    Start(["Scored candidate hypotheses"]) --> Chk0{"Any hypotheses<br/>could be evaluated?"}
    Chk0 -- no --> Ins["insufficient_evidence"]
    Chk0 -- yes --> Chk1{"Modulation was<br/>manually selected?"}
    Chk1 -- yes --> Us["user_selected"]
    Chk1 -- no --> Chk2{"Timing fit >=<br/>minimum threshold?"}
    Chk2 -- no --> Ins
    Chk2 -- yes --> Chk3{"Best score >=<br/>minimum score?"}
    Chk3 -- no --> Ins
    Chk3 -- yes --> Chk4{"Best score - runner-up score<br/>>= ambiguity margin?"}
    Chk4 -- no --> Amb["ambiguous"]
    Chk4 -- yes --> Det["determined"]
```

## 5. Installation

```bash
# conda (recommended): creates the "iqfile" environment
conda env create -f environment.yml
conda activate iqfile

# or plain pip on Python 3.10+ (Tkinter must be available)
pip install -r requirements.txt
```

| Package | Version |
|---|---|
| Python | 3.10 |
| numpy | 2.2.6 |
| scipy | 1.15.3 |
| matplotlib | 3.10.9 |
| reedsolo | 1.7.0 |
| tk | 8.6 |

## 6. Usage

```bash
python main.py
```

The window opens maximized. The left panel handles file input and configuration. The right panel has
four tabs, one per pipeline stage, each carrying its own plots alongside its data. There is no separate
"visualization" tab; every plot lives next to the stage that produced it.

| Tab | Contents |
|---|---|
| **Signal Isolation** | Active segment, isolated channel, preprocessing profile, plus the waveform and waterfall of what was isolated. |
| **Evidence Extraction** | Estimated parameters, spectral peaks, the re-estimation search trace, plus the spectrum (PSD) they were measured from. |
| **Hypothesis & Demodulation** | The best-supported hypothesis, every scored candidate, plus the constellation of the winning hypothesis's own demodulated symbols. |
| **Recovery Information** | De-interleaving/FEC choices, the recovered bitstream, header, and payload. |

Hypotheses and the full report can be exported as CSV / JSON. Try it with the files in `samples/`.

## 7. Interface walkthrough

The screenshots below are the actual, live application (captured via `PrintWindow` on its own window,
not mocked up), analyzing `samples/bpsk_carrier_8k.wav`.

### 7.1 Idle state

Nothing loaded yet. The left panel is where every run starts: pick a file, confirm its format details,
choose which modulations, de-interleavers, and FEC types to try (or switch to Manual mode to fix a
specific parameter and only search the rest), then click **Run Analysis**.

![Idle state](docs/screenshots/01_idle.png)

### 7.2 File loaded, ready to run

Selecting a file reads whatever metadata is available: sample rate and channel count from a `.wav`
header. A `.iq` file carries none, so sample rate and data type must be entered manually. This is a
real limitation of headerless IQ, not something the tool can guess around. The **Run Analysis** button
enables once there is enough information to start.

![File loaded](docs/screenshots/02_loaded.png)

### 7.3 Tab: Signal Isolation

Shows exactly which part of the recording and which frequency channel the rest of the pipeline is
analyzing: the active sample range, isolated fraction, the detected channel's center offset and
bandwidth, and which preprocessing profile was used (the plain "default" profile, or a denoised/
re-filtered one if the first pass was too weak to score confidently). Below that, the waveform envelope
and a waterfall (time versus frequency) of that isolated segment. This is the signal before any
down-conversion, so it shows where the signal actually sits in frequency.

![Signal Isolation tab](docs/screenshots/03_signal_isolation.png)

### 7.4 Tab: Evidence Extraction

The estimated parameters (sample rate, carrier offset, symbol rate, bandwidth, SNR, samples per symbol,
PAPR, spectral flatness, kurtosis, skewness), each tagged with its source in the third column. The
spectral peaks used as an FSK tone-grid reference sit alongside the re-estimation search trace: every
iteration the bounded coordinate search took over symbol rate, carrier offset, and low-pass cutoff, and
whether each step was kept. The spectrum (PSD) plot below is exactly what these parameters were measured
from.

![Evidence Extraction tab](docs/screenshots/04_evidence_extraction.png)

### 7.5 Tab: Hypothesis & Demodulation

The verdict, front and center: which modulation won, its score, confidence relative to the runner-up,
and the pipeline's verdict rule (`determined`, `ambiguous`, `insufficient_evidence`, or
`user_selected`). Below it, every candidate that was actually demodulated and scored, not just the
winner, with its own per-metric breakdown (constellation fit, order consistency, timing fit, EVM), so
you can see why one modulation beat the others rather than taking it on faith. The constellation plot on
the right is the winning hypothesis's own demodulated symbols: cluster count and shape is direct visual
evidence for the modulation call, and cluster tightness is a direct visual read of signal quality (EVM).

![Hypothesis & Demodulation tab](docs/screenshots/05_hypothesis_demodulation.png)

### 7.6 Tab: Recovery Information

What happened after demodulation: which de-interleaver and FEC method (if any) were selected by the
joint search, the parameters actually used, decode quality/success, and whether soft per-bit LLR
information was available to the decoder or it fell back to hard bits. On the right, header/payload
detection: pattern, offset, bit polarity, similarity, and the false-alarm probability that makes a
"header found" claim a statistical statement rather than a guess. This particular file carries no
framing, so both sides honestly report "not determined" / "not found" rather than inventing a decode.

![Recovery Information tab](docs/screenshots/06_recovery_information.png)

## 8. Accuracy

Measured, not claimed. `tests/test_accuracy_report.py` builds signals with known ground-truth
modulation, symbol rate, and bits, runs them through the real pipeline, and compares the output
numerically, not just whether the best-hypothesis label matches. Run it with:

```bash
python -m tests.test_accuracy_report
```

Measured with fixed, deterministic seeds (reproducible run to run), across BPSK/QPSK/16-QAM/2-FSK at
5/15/25 dB SNR:

| Metric | Result | Starting point |
|---|---|---|
| Modulation classification | 11/12 (92%) | 50% |
| Mean symbol-rate error | 0.0% | 4.2% |
| Mean BER (best-case alignment) | 0.046 | 0.329 |

The one miss is 16-QAM at 5 dB SNR (measured SNR about 2 dB), which is at the physical limit for this
constellation.

`tests/test_behaviour.py` covers the honesty rules and one end-to-end recovery (raw IQ of coded, framed
BPSK, with the interleaver and FEC inferred, recovered exactly): pure noise is not classified, coded
streams are verified and random bits are not, headers need statistical significance, manual choices are
labelled user-provided, and the re-estimation search stops on tolerance and iteration limit.

### 8.1 Correctness bugs found and fixed

Recorded here in case similar patterns turn up elsewhere.

1. The symbol-rate estimator used only `|signal|^2`, which is flat for constant-envelope modulations. A
   transition-energy feature and a signed instantaneous-frequency feature were added
   (`core/feature_extraction/cyclostationary.py`).
2. M-th-power (Costas) phase correction is invalid for QAM. It was replaced with a decision-directed
   phase search (`core/demodulation/synchronization.py`), and EVM is normalised by each constellation's
   minimum point spacing.
3. FSK evidence was derived from the same noisy samples it judged. The tone grid now comes from the PSD,
   with a chi-square noise-significance test, and from the unfiltered signal (`core/demodulation/fsk.py`).
4. The old SNR estimator assumed the signal sat in the centre of the band and read 13 dB at a true
   25 dB. It is now the M2M4 moment estimator using each hypothesis's own envelope kurtosis
   (`core/estimation/snr.py`).
5. A symbol rate found at a sub-harmonic of the true clock demodulates to equally clean symbols, so EVM
   cannot reveal it. The timing metric now measures the clock line at the tested rate, and the search
   prefers the higher rate on a tie only if its line is meaningfully stronger
   (`core/pipeline/reestimation.py`, `HARMONIC_TIE_MARGIN`).
6. Cyclic-line prominence against the global median was fooled by filtered noise. It now uses a local
   noise floor.
7. Header matches, Viterbi "success," and FEC decodes on random data were false positives. Each now has
   a statistical test against chance.
8. The manual symbol rate was collected by the GUI but never used.
9. FEC decoding used only hard 0/1 bits, discarding the demodulator's own confidence per bit. A
   soft-decision (LLR) path now runs end to end from demodulation, through de-interleaving, into
   Viterbi/LDPC decoding (`core/demodulation/soft_bits.py`), verified to cut Viterbi output BER from
   14.6% to 0.4% and to let LDPC converge at an SNR where the hard-decision decoder failed outright.

## 9. Known limitations

Documented, not hidden.

| Area | Limitation |
|---|---|
| Classification | 16-QAM at very low SNR is misclassified as QPSK. 2-FSK whose tone spacing equals the symbol rate is spectrally hard to separate from BPSK. |
| FSK detection | Low modulation-index FSK (tone spacing a small fraction of the symbol rate) is not detected at all, confirmed against real captures. The PSD is a single unimodal lobe with no resolvable per-tone humps, and the instantaneous-frequency samples show only shallow, noise-comparable bimodality. No threshold-based fix was found that did not also false-positive on PSK/QAM (see `CLAUDE.md` for the two approaches tried and rejected). |
| SNR estimation | The M2M4 estimator saturates near the +40 dB clamp for true SNR above roughly 20 to 25 dB, a finite-sample instability in the 4th-moment estimate at high SNR. The qualitative read ("very clean") stays right; the exact dB figure above ~20 dB should not be trusted. |
| Symbol-rate estimation | Can still lock onto an exact 2x harmonic for unshaped (rectangular-pulse) PSK/QAM during a second preprocessing-profile retry, even with the tie-break margin in place, because sampling at an exact multiple of an unshaped signal's true rate just repeats each real symbol. EVM cannot tell that apart from the true rate. |
| LDPC | Supports exactly one code, the IEEE 802.11n n=648 rate-3/4 code, with min-sum decoding (soft LLR when available, hard-bit fallback otherwise). Other LDPC codes are reported as not decodable. |
| Reed-Solomon | Hard-decision only. Classical Berlekamp-Massey decoding has no soft form. |
| Header detection | Knows three sync words (CCSDS ASM, HDLC flag, Barker-11). Short patterns in long streams cannot pass the false-alarm test, so an 8-bit HDLC flag is not reported in a stream of thousands of bits. |
| De-interleaving parameters | Automatic mode uses defaults per method. Manual mode takes explicit parameters for a specific known link. |
| Verdict logic | Does not yet distinguish "wrong because the constellation is not supported" from "wrong with real ambiguity." An unsupported order like 64-QAM can come back `determined` with an incorrect modulation instead of being flagged ambiguous/insufficient. |
| Timing recovery | Decimates at an integer samples-per-symbol phase. It does not interpolate non-integer ratios. |
| Spectral-fit metric | Not scored: for unshaped pulses, PSD peaks cannot discriminate hypotheses reliably. |
| Runtime | Worst case is noise-like input (every profile and search step is tried), a few seconds for 8k samples. Real signals usually finish in 1 to 2 seconds. |

## 10. Project layout

```
core/            signal-processing engine
  io/              read .iq / .wav, parse metadata
  preprocessing/   normalization, denoising, resampling, retry profiles
  isolation/       spectrum, band/channel detection, segmentation
  feature_extraction/  spectral, temporal, statistical, cyclostationary
  estimation/      sample rate, symbol rate, carrier, SNR
  hypotheses/      candidate generation (modulation, FEC, interleaving)
  scoring/         evidence scoring and confidence
  demodulation/    PSK, QAM, FSK, synchronization, soft-bit (LLR) computation
  deinterleaving/  block, convolutional, diagonal, pseudo-random
  fec/             Viterbi, Reed-Solomon, concatenated, LDPC
  correlation/     bit-stream correlation, header/payload detection
  pipeline/        orchestrator (analyzer), config, stages, result models
gui/             Tkinter desktop UI (app.py, plots.py, style.py); launched by main.py
tests/           smoke, behaviour, LDPC and accuracy tests
samples/         small synthetic .iq / .wav files for trying the app
docs/            implementation specification (the design contract) + screenshots
main.py          entry point (launches the GUI)
CLAUDE.md        working notes: rules, status, known dead ends
environment.yml  conda environment (Python 3.10, Tk 8.6, pinned packages)
requirements.txt the same pinned packages for pip
```

## 11. Testing

```bash
python -m tests.test_pipeline_smoke    # synthetic BPSK end to end
python -m tests.test_behaviour         # honesty/behaviour checks (15 tests, ~40 s)
python -m tests.test_ldpc              # LDPC round trip + negative control
python -m tests.test_accuracy_report   # ground-truth accuracy table (~25 s)
```
