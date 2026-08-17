# Gusset

**An autonomous repo custodian, engineered as graphs.**

Gusset installs on a repository and keeps its engineering truths true:

- Every pull request gets a **verified blast-radius comment** — what your change affects, proven against the code graph, not guessed.
- Architecture docs **never go stale** — refreshed by PR when the module structure actually shifts.
- Dead code **gets deleted** — with per-symbol proof.

It acts through PRs you approve, and it earns more autonomy as its evaluation scores prove out — permissions are climbed (`report → comment → propose → act`), never assumed, and lost automatically when quality slips.

Under the hood, Gusset is a working example of **graph engineering**: explicit execution graphs with typed state, deterministic guards, validation gates, checkpoints, and human gates — supervised, measured, and self-healing via [PandaProbe](https://docs.pandaprobe.com) (optional, free tier available; Gusset runs without it).

## Status

🚧 Under active construction. Install guide, docs, and v0.1 land soon.

## License

MIT
