# Contributing to Gusset

Thanks for looking under the hood. The short version:

- **The dev loop is documented in [CLAUDE.md](CLAUDE.md)** — it applies to
  humans and coding agents alike (Gusset develops Gusset; use the tool on
  your own change before pushing it).
- **New workflows** follow [docs/howto/write-a-workflow.md](docs/howto/write-a-workflow.md)
  and the eight-point discipline checklist. The non-negotiable: the model
  writes wording, the graph owns truth — if you can't write the
  lying-model test, the design is wrong.
- **New languages** are the friendliest first contribution: an extractor
  (~150 lines, manual tree-sitter walk), a fixture repo with a *known*
  call graph, and exact-edge tests. Recipe at the bottom of the workflow
  how-to; `src/gusset/graph/extract.py` has three worked examples.
- **Tests are the contract:** `uv run pytest -q` green before any PR, and
  every bug fix lands with the regression test that would have caught it.
- Friction you hit while using Gusset is itself a contribution — a
  [DOGFOOD.md](DOGFOOD.md)-style issue ("what I did, what surprised me")
  is as valuable as a patch.

By contributing you agree your work is licensed under the repo's MIT
license.
