# Contributing to SigIQ

Thanks for your interest in SigIQ. This project doesn't have a formal contribution process
set up yet, but issues and pull requests are welcome.

## Getting set up

```bash
conda env create -f environment.yml
conda activate iqfile
```

or, with plain pip on Python 3.10+:

```bash
pip install -e ".[dev]"
```

## Before opening a pull request

- Run the test suite and make sure it passes:
  ```bash
  pytest
  python -m tests.test_pipeline_smoke
  python -m tests.test_accuracy_report
  ```
- Keep the core engine (`src/sigiq/core/`) free of any GUI imports -- it must stay runnable
  and testable on its own.
- Follow the honesty rules the project is built around: never hardcode a detected result,
  confidence value, sample rate, or FEC outcome; every reported parameter should carry a
  provenance label; report `insufficient_evidence` rather than guessing when the signal
  doesn't support a conclusion.

## Reporting issues

Open a GitHub issue with what you ran, what you expected, and what happened instead. For
signal-processing bugs, attaching a small `.iq`/`.wav` sample that reproduces the issue
(or the exact synthetic-signal parameters used) makes it much easier to track down.

## Security issues

Please don't open a public issue for a security concern -- see [SECURITY.md](SECURITY.md).
