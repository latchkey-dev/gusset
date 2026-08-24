"""The trace-upload retry digest.

On a free PandaProbe tier every run printed four to eight
`429, retrying` warnings from the SDK. Tracing is optional and scores are
local, so those lines were noise that read as failure to a first-time
user — but silently dropping them would be dishonest, so they are counted
and reported once.
"""

import logging

from gusset.probe import tracing


def _fresh_digest(monkeypatch):
    digest = tracing._RetryDigest()
    monkeypatch.setattr(tracing, "_digest", digest)
    return digest


def _record(level: int, msg: str) -> logging.LogRecord:
    return logging.LogRecord("pandaprobe", level, __file__, 1, msg, None, None)


def test_retry_warnings_are_suppressed_and_counted(monkeypatch):
    digest = _fresh_digest(monkeypatch)
    for _ in range(4):
        assert digest.filter(_record(
            logging.WARNING,
            "PandaProbe POST https://api.pandaprobe.com/traces → 429, "
            "retrying in 0.5s (attempt 1/3)",
        )) is False
    assert digest.suppressed == 4
    note = tracing.retry_digest_note()
    assert note is not None and "4 trace-upload retries" in note
    assert "scores are computed locally" in note
    # The count resets, so a later run does not inherit this one's noise.
    assert tracing.retry_digest_note() is None


def test_exhausted_upload_error_still_prints(monkeypatch):
    """The failure that means the trace link won't work must survive.

    Suppressing retries is a courtesy; suppressing the outcome would be a
    lie about whether the trace exists.
    """
    digest = _fresh_digest(monkeypatch)
    record = _record(
        logging.ERROR,
        "PandaProbe POST https://api.pandaprobe.com/traces → 429: rate limited",
    )
    assert digest.filter(record) is True
    assert digest.suppressed == 0


def test_unrelated_warnings_pass_through(monkeypatch):
    digest = _fresh_digest(monkeypatch)
    assert digest.filter(_record(logging.WARNING, "PandaProbe: project not found")) is True


def test_singular_wording(monkeypatch):
    digest = _fresh_digest(monkeypatch)
    digest.filter(_record(logging.WARNING, "x, retrying in 1.0s (attempt 1/3)"))
    assert "1 trace-upload retry" in tracing.retry_digest_note()


def test_no_note_when_nothing_suppressed(monkeypatch):
    _fresh_digest(monkeypatch)
    assert tracing.retry_digest_note() is None
