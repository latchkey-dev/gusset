# Why Gusset is built the way it is

Gusset is a working answer to a design question: **what does it take to let
an agent act on a repository without a human watching every run?**

Our answer is *graph engineering* — the discipline of designing the
structures an agent works through, rather than the prompts it is fed.
Prompt engineering shapes one model call. Context engineering shapes what a
model sees. Graph engineering shapes how models, deterministic functions,
validators, and humans work *together*: as an explicit, executable graph
with typed state, guarded routes, verification gates, checkpoints, and
human decision points.

## The three graphs

Gusset uses all three graph types the discipline names:

| Graph | In Gusset | Why it exists |
|---|---|---|
| **Execution graphs** | Every workflow is a LangGraph `StateGraph`; the supervisor that routes events is one more level of the same idea | So control flow is code you can read, not emergent model behavior |
| **Knowledge graph** | Your repo, indexed: symbols and call/import/inheritance edges in SQLite | So workflows have something *verifiable* to stand on |
| **Provenance** | PandaProbe traces/sessions/scores keyed to commit + inputs; the ladder ledger; the harness journal | So every output can answer "which run of which code on which repo state produced you?" |

## The oracle: why the code graph is special

Most agent output can only be judged by another model. A claim about code
structure is different: *"changing `auth.validate_token` affects `login`"*
names an edge that either exists in the parsed graph or does not. The
knowledge graph is therefore not context — it is an **oracle**, a source of
free, deterministic ground truth on every single run.

That one property powers the whole system:

- The **verification gate** in each workflow checks every claim against the
  graph. Unverifiable claims are dropped and logged — never silently kept.
- The **oracle scores** (`closure_recall`, `summary_grounding`,
  `gate_drop_rate`) measure each run with no human labeling and no LLM
  judge in the loop.
- The **autonomy ladder** promotes and demotes an invariant's permissions
  from that score history — evals with teeth, not dashboards.
- The **self-healing harness** gets an outcome verifier that cannot be
  sweet-talked, and a replay function that is honest because the substrate
  is deterministic: same commit + same seeds = same ground truth.

The indexer is built never to guess: references it cannot resolve are
counted (`unresolved_refs`) but never written as edges. A fabricated edge
would poison everything downstream, so the graph prefers ignorance to
invention.

## The discipline checklist

Every Gusset workflow satisfies eight properties. They read as sensible
hygiene for a CLI tool; for an unattended agent they are the difference
between a custodian and a liability.

1. **Typed state** — every node reads and writes a declared schema.
2. **Real-dependency edges only** — graph edges exist because the target
   needs the source's output.
3. **Deterministic guards** — routing is code: fan-out caps, depth caps,
   "zero seeds → halt". A doc-only diff never wakes the LLM.
4. **Diamond verification** — model work and oracle work run on separate
   tracks and merge only through the gate.
5. **Validation gates** — no claim survives unverified; failures are
   dropped *and logged*.
6. **Checkpoints** — state snapshots at every turn boundary buy resumability
   and honest replay for free.
7. **Human gates at the highest-cost points** — interactively an interrupt,
   autonomously a PR review. The gate moves; it never disappears.
8. **Provenance on every claim** — edge evidence in every report line,
   commit + inputs on every run.

## Autonomy is the argument

A one-shot CLI barely needs any of this — a human reads the output and
catches nonsense. Remove the human and the checklist becomes load-bearing:
guards bound spend, gates bound falsehood, checkpoints bound failure,
ledgers bound trust. That is the project's thesis: **graph engineering is
what makes it safe to take the human out of the loop** — and measured
evals (PandaProbe) are what make the remaining trust *earned* rather than
assumed.
