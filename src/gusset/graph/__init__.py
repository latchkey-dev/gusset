"""The knowledge-graph substrate: tree-sitter -> SQLite.

This is the supporting organ of Gusset, not the product. It exists so that
workflows have something verifiable to operate on: every claim a workflow
makes is checked against this graph (the "oracle"). Deliberately minimal —
symbol/call/import/inheritance edges, no type inference, no LSP.
"""

from gusset.graph.store import GraphStore

__all__ = ["GraphStore"]
