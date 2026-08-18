# Architecture

## System context

```mermaid
graph TD
    subgraph "Your repo"
        CODE[source code] --> IDX[indexer<br/>tree-sitter]
        TOML[gusset.toml<br/>invariants] --> SUP
        LEDGER[.gusset/ladder.jsonl<br/>autonomy ledger]
        HW[.gusset/harness/<br/>learned rules + journal]
    end

    IDX --> DB[(graph.db<br/>SQLite)]
    DB --> ORACLE[oracle<br/>deterministic verification]

    EV[events<br/>PR · push · cron] --> SUP[supervisor<br/>guards · budgets · routing]
    SUP -->|only if guards pass| WF[workflows<br/>LangGraph execution graphs]
    DB --> WF
    ORACLE --> WF
    WF --> ACT[actions<br/>artifact · PR comment · PR]
    SUP --> LEDGER
    ORACLE --> LEDGER

    WF -.traces.-> PP[(PandaProbe<br/>traces · scores · monitors)]
    ORACLE -.scores.-> PP
    HARNESS[self-healing harness] -.notices/repair.-> HW
    WF -.turn hooks.-> HARNESS
    ORACLE -.verifier.-> HARNESS
```

Solid arrows are the deterministic spine — they work with zero credentials.
Dotted arrows are the observability layer: PandaProbe tracing, oracle score
push, and the self-healing harness. All of it degrades to off.

## The impact workflow's execution graph

```mermaid
graph TD
    START([event / CLI]) --> RS[resolve_seeds]
    RS -->|no seeds| HALT([halt: honest no-op])
    RS --> ER[expand_ring<br/>graph computes ring<br/>LLM explains WHY]
    ER --> VG{verify_gate<br/>edge exists in graph?}
    VG -->|claim fails| DROP[dropped + logged]
    VG -->|more rings, depth < cap| ER
    VG -->|frontier empty| SYN[synthesize<br/>deterministic skeleton,<br/>model wording only]
    SYN --> HG{{human gate<br/>interrupt / PR review}}
    HG -->|approve| OUT([report + scores])
    HG -->|reject| REJ([nothing written])
```

The division of labor is strict: **the graph decides WHAT is affected, the
model only explains WHY.** Model output can degrade the wording of a
report, never its truth — that property is tested with a deliberately
lying fake model.

## The autonomy ladder

```mermaid
stateDiagram-v2
    [*] --> report
    report --> comment : 15 consecutive runs ≥ 0.9
    comment --> propose : 15 consecutive runs ≥ 0.9
    propose --> act : human config only —<br/>the ladder never grants act
    comment --> report : 3 of last 5 runs < 0.8
    propose --> comment : 3 of last 5 runs < 0.8
```

Promotion is slow, demotion is fast, the ceiling is human-granted per
invariant (`max_autonomy`), and every transition is a ledger entry with its
reason. The scores driving it come from the oracle — deterministic
verification against the code graph — so no human labels anything and no
LLM judges itself.

## The self-healing loop

```mermaid
sequenceDiagram
    participant W as workflow turn
    participant H as harness (PandaProbe)
    participant R as repair agent
    participant O as oracle

    W->>H: turn hook (session, turn_index, end_state)
    H->>H: score trajectory (tiered evals)
    H->>O: outcome verifier (synthesis turns only)
    O-->>H: ground truth score
    Note over H: trajectory stalls/regresses?
    H->>R: diagnostic notice (mailbox)
    R->>R: inspect traces, existing rules
    R->>H: candidate rule (rules/*.md)
    H->>W: next runs read rules via 4 read-only tools
    H->>H: replay original failure + trial window
    H->>H: promote to active / retire, journaled
```

The workflow never sees the mailbox and the repair agent never blocks a
run. Rules earn `active` status through replayed evidence — the same
philosophy as the ladder, one level down.
