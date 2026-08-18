"""Push oracle scores onto the PandaProbe trace for a workflow session.

Trace IDs are generated inside the SDK's callback handler and not exposed,
so we flush, look the trace up by session_id via the documented REST
endpoint, and score the run's root trace (the one with the most spans).
No-ops without credentials, like everything in probe/.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from gusset.probe.tracing import probe_enabled

API_BASE = os.environ.get("PANDAPROBE_ENDPOINT", "https://api.pandaprobe.com")


def _find_trace_id(session_id: str) -> str | None:
    query = urllib.parse.urlencode({"session_id": session_id, "limit": 50})
    req = urllib.request.Request(
        f"{API_BASE}/traces?{query}",
        headers={
            "X-API-Key": os.environ["PANDAPROBE_API_KEY"],
            "X-Project-Name": os.environ.get("PANDAPROBE_PROJECT_NAME", "gusset"),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        items = json.load(resp).get("items", [])
    if not items:
        return None
    root = max(items, key=lambda t: t.get("span_count") or 0)
    return root.get("trace_id")


def push_scores(session_id: str, scores: list) -> bool:
    """Attach oracle scores to the session's root trace. True if pushed."""
    if not probe_enabled():
        return False
    import pandaprobe

    pandaprobe.flush()  # the trace must be ingested before we can score it
    trace_id = _find_trace_id(session_id)
    if trace_id is None:
        return False
    for s in scores:
        pandaprobe.score(
            trace_id=trace_id,
            name=s.name,
            value=str(s.value),
            data_type="NUMERIC",
            reason=s.reason,
        )
    pandaprobe.flush()
    return True
