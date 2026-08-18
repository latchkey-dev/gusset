"""LangGraph → PandaProbe tracing.

The LangGraph integration has no instrument() pattern: the callback handler
must be passed per invocation (config={"callbacks": [...]}) — centralized
here so workflows never touch pandaprobe imports themselves.
"""

from __future__ import annotations

import os


def probe_enabled() -> bool:
    return bool(os.environ.get("PANDAPROBE_API_KEY"))


def make_callbacks(session_id: str, tags: list[str] | None = None) -> list:
    """Callbacks for graph.invoke(config={"callbacks": ...}).

    One workflow run = one PandaProbe session; LangChain propagates the
    handler to every nested chain/LLM call, so nodes, model calls, and
    the whole execution graph arrive as one trace tree.
    """
    if not probe_enabled():
        return []
    from pandaprobe.integrations.langgraph import LangGraphCallbackHandler

    return [LangGraphCallbackHandler(session_id=session_id, tags=tags or [])]


def trace_url_hint(session_id: str) -> str | None:
    if not probe_enabled():
        return None
    return f"https://app.pandaprobe.com/sessions?search={session_id}"
