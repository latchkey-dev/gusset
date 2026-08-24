"""LangGraph → PandaProbe tracing.

The LangGraph integration has no instrument() pattern: the callback handler
must be passed per invocation (config={"callbacks": [...]}) — centralized
here so workflows never touch pandaprobe imports themselves.
"""

from __future__ import annotations

import logging
import os


def probe_enabled() -> bool:
    return bool(os.environ.get("PANDAPROBE_API_KEY"))


class _RetryDigest(logging.Filter):
    """Collapse the SDK's per-attempt retry warnings into a single line.

    The free tier rate-limits trace uploads, so an ordinary run printed
    four to eight `429, retrying` warnings. Tracing is optional and scores
    are computed locally regardless, but to anyone running Gusset for the
    first time those lines read as the tool failing. Counting them and
    saying so once keeps the information and drops the alarm.

    Only the retry chatter is filtered. The SDK's ERROR when retries are
    exhausted still prints — that one means the trace link will not work,
    which the user genuinely needs.
    """

    def __init__(self) -> None:
        super().__init__()
        self.suppressed = 0

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno <= logging.WARNING and "retrying in" in record.getMessage():
            self.suppressed += 1
            return False
        return True


_digest = _RetryDigest()
_installed = False


def install_retry_digest() -> None:
    """Attach the digest to the pandaprobe logger. Idempotent."""
    global _installed
    if _installed:
        return
    logging.getLogger("pandaprobe").addFilter(_digest)
    _installed = True


def retry_digest_note() -> str | None:
    """One honest line about suppressed retries, or None. Resets the count."""
    count = _digest.suppressed
    _digest.suppressed = 0
    if not count:
        return None
    return (
        f"pandaprobe: {count} trace-upload retr{'y' if count == 1 else 'ies'} "
        f"(rate limit); scores are computed locally and are unaffected"
    )


def make_callbacks(session_id: str, tags: list[str] | None = None) -> list:
    """Callbacks for graph.invoke(config={"callbacks": ...}).

    One workflow run = one PandaProbe session; LangChain propagates the
    handler to every nested chain/LLM call, so nodes, model calls, and
    the whole execution graph arrive as one trace tree.
    """
    if not probe_enabled():
        return []
    install_retry_digest()
    from pandaprobe.integrations.langgraph import LangGraphCallbackHandler

    return [LangGraphCallbackHandler(session_id=session_id, tags=tags or [])]


def trace_url_hint(session_id: str) -> str | None:
    if not probe_enabled():
        return None
    return f"https://app.pandaprobe.com/sessions?search={session_id}"
