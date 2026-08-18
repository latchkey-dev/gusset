# How to write a new workflow

Gusset workflows are LangGraph execution graphs that satisfy the
eight-point discipline checklist
([explanation/graph-engineering.md](../explanation/graph-engineering.md)).
Use `src/gusset/workflows/impact.py` as the canonical example and keep
these invariants:

## The contract

```python
def build_myworkflow_graph(
    model,                    # BaseChatModel; None if your workflow can run LLM-free
    checkpointer=None,        # SqliteSaver; pass one in production
    system_preamble="",       # prepended to EVERY system message (harness rules)
    turn_hook=None,           # callable(node_name, state_view) — the healing seam
):
    ...
    return graph.compile(checkpointer=checkpointer)
```

1. **Typed state.** A `TypedDict` with `Annotated[list, append]` reducers
   for accumulated fields (`verified`, `dropped`).
2. **The model never decides truth.** Compute candidate facts from
   `GraphStore` queries; let the model author *wording only*. If your
   workflow needs a graph query that doesn't exist, add deterministic SQL
   to `GraphStore` with a docstring and tests — never work around it with
   model judgment.
3. **A verification gate.** Every model-touched claim re-verifies against
   the graph before it may enter `verified`. Failures append to `dropped`
   with a reason; they are logged, never silently discarded.
4. **Deterministic guards.** Empty input → `halt_reason`, never invented
   work. Fan-out caps aggregate rather than truncate silently.
5. **Human gate last.** `interrupt({"draft": ...})` before anything leaves
   the workflow; resume with `Command(resume=True/False)` or
   `{"draft": edited, "approved": bool}`. The workflow never writes files —
   the caller does, after approval.
6. **Fire the turn hook** at each gate and at synthesis with accumulated
   state: `turn_hook(node, {**state, **update})`. Never import `probe/`
   from a workflow — the hook is a plain callable seam.
7. **Tolerate block-list content.** Use the `_content_text` helper pattern
   for Claude adaptive-thinking responses.
8. **Test with a lying model.** A `FakeMessagesListChatModel` that invents
   symbols must not be able to corrupt your output — if that test can't be
   written, the design is wrong.

## Wiring it up

- **CLI**: add a command in `cli.py` following `atlas`'s shape — one
  `asyncio.run()` for the whole run, workflow in `asyncio.to_thread`,
  `SelfHealing.create/bind_loop/turn_hook/settle` around it, oracle scores
  printed and pushed after approval.
- **Supervisor**: add a branch in `runner.py:_execute_workflow` returning
  `(report_body, scores, commit_paths)`, and add the workflow name to
  `config.py:VALID_WORKFLOWS`. Give it an oracle scorer in
  `gusset/oracle/` — without scores the ladder cannot govern it, and an
  ungoverned invariant stays at `report` forever.
- **Docs**: a row in `docs/reference/cli.md` and, if it introduces new
  scores, the scores table.

## How to add a language

Extractors live in `src/gusset/graph/extract.py` as manual tree-sitter AST
walks (no query DSL — node-type names are stable, query APIs are not).
Add the suffix to `LANGUAGE_BY_SUFFIX`, write `_walk_<lang>` following
`_walk_go`, and — non-negotiable — a fixture repo under `tests/fixtures/`
with a *known* call graph and tests asserting exact edges, a negative
case, and the dead-symbol. The parser comes from
`tree_sitter_language_pack.get_parser`; add no new dependencies.
