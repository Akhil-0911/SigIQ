def estimate_sample_rate(raw_sample_rate: float, source_format: str) -> dict:
    """WAV files carry a real sample-rate header (authoritative). IQ files
    don't, so the value the user supplied at upload time is the estimate,
    flagged as user-supplied rather than measured."""
    if source_format == "wav":
        return {"sample_rate": raw_sample_rate, "source": "file_header", "confidence": 1.0}
    return {"sample_rate": raw_sample_rate, "source": "user_supplied", "confidence": 0.5}
