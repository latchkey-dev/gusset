"""All PandaProbe wiring lives here — and ONLY here.

Gusset must degrade gracefully to fully-off: without credentials every
function in this package becomes a cheap no-op, so no other module may
import pandaprobe directly or assume tracing exists.
"""

from gusset.probe.tracing import make_callbacks, probe_enabled, trace_url_hint

__all__ = ["make_callbacks", "probe_enabled", "trace_url_hint"]
