# Security Policy

## Supported Versions

SigIQ is a desktop application distributed as source and as a standalone Windows build
(see [Releases](https://github.com/Akhil-0911/SigIQ/releases)). Only the latest release is
supported with security fixes.

## Reporting a Vulnerability

If you find a security issue (for example, a way a malformed `.iq`/`.wav` file could crash the
app or execute unexpected code, or an issue in how the standalone `.exe` is built or signed),
please report it privately rather than opening a public issue:

- Email: rajanbabu.akhil@gmail.com
- Include: a description of the issue, steps to reproduce, and the affected version/commit.

You should expect an initial response within a few days. Once a fix is available, it will be
released and the reporter credited (unless anonymity is requested).

## Scope

This project processes untrusted binary input (`.iq`/`.wav` recordings). Parsing/decoding bugs
in `src/sigiq/core/io/`, `src/sigiq/core/demodulation/`, or `src/sigiq/core/fec/` that could be
triggered by a crafted file are in scope. General signal-processing accuracy issues (e.g. a
modulation being misclassified) are functional bugs, not security issues -- please file those as
a normal GitHub issue instead.
