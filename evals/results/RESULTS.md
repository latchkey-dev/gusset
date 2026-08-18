# Impact analysis: graph-engineered workflow vs. freeform agent

Model: `claude-sonnet-5` for every condition. 16 questions (8 seeds x 2 corpora: this repo itself + a generated 30-file layered repo), ground truth = the code graph's reverse closure (depth <= 4, modules and the seed excluded).

Fairness notes: the baseline prompt included a static listing of the repo's source files (orientation only — its two tools remain read_file and grep); claims that resolve to the seed symbol itself are excluded from every metric denominator. The ground truth is the same graph condition B traverses, so B's scores measure the workflow's fidelity to its substrate while A's measure what a freeform agent recovers without it.

| Condition | n | Precision (mean/med) | Recall (mean/med) | Hallucinated rate (mean/med) | Mean tokens | Mean wall s |
|---|---|---|---|---|---|---|
| A — freeform agent (no graph) | 16 | 44.7% / 41.0% | 68.6% / 83.3% | 11.4% / 1.6% | 90,982.4 | 37.0 |
| B — gusset impact workflow | 16 | 100.0% / 100.0% | 100.0% / 100.0% | 0.0% / 0.0% | 4,086.6 | 17.2 |
| C — gusset, verify gate neutered (derived) | 16 | 100.0% / 100.0% | 100.0% / 100.0% | 0.0% / 0.0% | 0 | 0.0 |

Condition C is derived from condition B's recorded pre-gate candidates (verified + dropped) rather than separate monkeypatched runs — the gate is the only difference, so this is exact for ring 1 and exact overall whenever the gate drops nothing; it re-uses B's LLM calls, so its tokens/wall are reported as 0.

## Per-corpus breakdown

| Corpus | Condition | Precision | Recall | Hallucinated |
|---|---|---|---|---|
| real | A | 33.2% | 37.2% | 20.4% |
| real | B | 100.0% | 100.0% | 0.0% |
| real | C | 100.0% | 100.0% | 0.0% |
| synth | A | 56.1% | 100.0% | 2.4% |
| synth | B | 100.0% | 100.0% | 0.0% |
| synth | C | 100.0% | 100.0% | 0.0% |

## Spend

Total recorded usage: 1,452,682 input (of which 1,213,562 cache reads, 0 cache writes), 68,421 output tokens over 229 LLM calls.

- standard: **$2.11**
- intro_thru_2026-08-31: **$1.41**

## Observations

- **The verify gate dropped 0 of 276 claims (C is identical to B).** The ablation's finding is that the gate contributes nothing *when candidates are graph-derived*: `expand_ring` only proposes symbols the graph already returned as dependents, so `edge_exists` always passes. The gate is insurance against model-authored claims (the LLM only writes the "why" strings here), not a measured source of lift — and B's 16/16 perfect precision/recall is fidelity to its own substrate, since the ground truth is the same graph the workflow traverses. The informative comparison is what A loses without that substrate.

- **The freeform agent's recall is bimodal, and its effort did not scale with blast radius.** On the synthetic layered repo (globally unique names, grep-friendly) A hit 100% recall on all 8 questions, at 0.30-0.75 precision. On the real repo recall fell as closures grew: 67% at closure 3, 20-31% mid-range, and 3% on the 104-symbol closure (`GussetConfig.get`) — where A used only 8 of its 25 tool calls, claimed 5 things at 0.60 precision, and confidently stopped. B returned all 104 at 20.5k tokens. Baseline wins one axis honestly: on that hardest question its 42k tokens beat several of its own easier runs, because giving up early is cheap.

- **Where A goes wrong, it's mostly real-but-outside-the-closure, not invention — but 10% of claims were pure fabrications.** Of 310 claims: 122 correct, 157 (51%) resolved to real symbols outside the depth-4 reverse closure (tests, CLI commands, conceptually-affected neighbors the graph does not connect), and 31 (10%) resolved to nothing — invented node names (`atlas.partition`, `atlas.summarize_module`), enum members, wrong intermediate paths (`atlas.synthesize` for `atlas.build_atlas_graph.synthesize`), and filenames formatted as dotted paths (`core2.py`). Caveat cutting A's way: the indexer's resolution is deliberately conservative (1,134 unresolved refs in the real repo), so some "wrong-but-real" claims may be genuinely affected symbols the graph cannot see. Token cost: A averaged 22x B's tokens (91.0k vs 4.1k) and 2.1x its wall time; prompt caching (84% of A's input tokens were cache reads) kept the billed gap smaller than the raw one.
