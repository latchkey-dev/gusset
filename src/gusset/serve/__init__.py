"""gusset serve — the local canvas over Gusset's own state.

Reads what the tool already produces (graph.db, ladder.jsonl, run events,
harness workspace) and serves the six approved views. Local-only by
design: binds 127.0.0.1, holds no credentials beyond writing .env on the
user's machine, and adds no new persistent state except the run-event
log the workflows already emit through their turn-hook seam.
"""
