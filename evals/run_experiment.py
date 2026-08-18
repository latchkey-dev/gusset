"""Orchestrator: corpus x seed x condition -> raw.jsonl -> summary + RESULTS.md.

Conditions:
  A — freeform ReAct agent, read_file + grep, no graph (evals/baseline.py)
  B — gusset's build_impact_graph workflow (evals/gusset_runner.py)
  C — ablation: verify gate neutered. Derived from B's recorded pre-gate
      candidates (verified + dropped) at zero extra LLM cost: the gate is the
      only difference between B's claims and its pre-gate candidates, so
      passing everything through == claiming verified+dropped. (A separate
      monkeypatched run would re-spend B's tokens to produce the same set,
      because candidates are graph-derived; decision noted in RESULTS.md.)

Resumable: rows already in evals/results/raw.jsonl are skipped. Individual
run failures are recorded as errored rows and the experiment continues.

Usage:
  .venv/bin/python -m evals.run_experiment                # run + aggregate
  .venv/bin/python -m evals.run_experiment --aggregate    # aggregate only
  .venv/bin/python -m evals.run_experiment --limit N      # first N questions
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv

from evals.corpus import EVALS_DIR, REPO_ROOT, load_questions
from evals.measure import measure_claims

RESULTS_DIR = EVALS_DIR / "results"
RAW = RESULTS_DIR / "raw.jsonl"
SUMMARY = RESULTS_DIR / "summary.json"
RESULTS_MD = RESULTS_DIR / "RESULTS.md"
OBSERVATIONS = RESULTS_DIR / "observations.md"

DEFAULT_MODEL = "claude-sonnet-5"

# claude-sonnet-5 pricing per 1M tokens (cache read 0.1x base in, write 1.25x)
PRICING = {
    "standard": {"in": 3.00, "out": 15.00},
    "intro_thru_2026-08-31": {"in": 2.00, "out": 10.00},
}

CONDITION_NAMES = {
    "A": "A — freeform agent (no graph)",
    "B": "B — gusset impact workflow",
    "C": "C — gusset, verify gate neutered (derived)",
}


def _model_name() -> str:
    return os.environ.get("GUSSET_MODEL", DEFAULT_MODEL)


def _load_rows() -> list[dict]:
    if not RAW.exists():
        return []
    return [json.loads(line) for line in RAW.read_text().splitlines() if line.strip()]


def _append_row(row: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with RAW.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _make_models():
    from langchain_anthropic import ChatAnthropic

    name = _model_name()
    # Baseline resends a growing transcript every turn; top-level
    # cache_control auto-caches the prefix so the loop stays affordable.
    # 8192: sonnet-5's adaptive thinking counts against max_tokens, and the
    # final answer on large-closure questions must list ~100 symbols.
    baseline_model = ChatAnthropic(
        model=name, max_tokens=8192,
        model_kwargs={"cache_control": {"type": "ephemeral"}},
    )
    gusset_model = ChatAnthropic(model=name, max_tokens=4096)
    return baseline_model, gusset_model


def run_all(limit: int | None = None) -> None:
    load_dotenv(REPO_ROOT / ".env")
    questions = load_questions()
    if limit is not None:
        questions = questions[:limit]
    done = {(r["corpus"], r["seed"], r["condition"]) for r in _load_rows()}
    baseline_model, gusset_model = _make_models()

    from evals.baseline import run_baseline
    from evals.gusset_runner import run_gusset

    for q in questions:
        for condition in ("B", "A"):  # B is cheap; run it first
            key = (q["corpus"], q["seed"], condition)
            if key in done:
                continue
            row = {"corpus": q["corpus"], "seed": q["seed"],
                   "condition": condition, "model": _model_name()}
            print(f"[run] {q['corpus']} {condition} {q['seed']}", flush=True)
            try:
                if condition == "A":
                    result = run_baseline(q, baseline_model)
                    row["tool_calls"] = result["tool_calls"]
                    row["answer"] = result["answer"]
                else:
                    result = run_gusset(q, gusset_model)
                    state = result["state"]
                    row["n_verified"] = len(state["verified"])
                    row["n_dropped"] = len(state["dropped"])
                    row["draft"] = state["draft"]
                    row["halt_reason"] = state["halt_reason"]
                    row["claimed_pre_gate"] = (
                        [c["qualname"] for c in state["verified"]]
                        + [d["qualname"] for d in state["dropped"]]
                    )
                row["claimed"] = result["claimed"]
                row["usage"] = result["usage"]
                row["wall_seconds"] = result["wall_seconds"]
                row["metrics"] = measure_claims(q["db_path"], q["seed"],
                                                result["claimed"])
                row["status"] = "ok"
            except Exception:
                row["status"] = "error"
                row["error"] = traceback.format_exc()[-2000:]
                print(f"[error] {key}: {row['error'].splitlines()[-1]}", flush=True)
            _append_row(row)
            done.add(key)
        # C is derived from B — no LLM spend
        key_c = (q["corpus"], q["seed"], "C")
        if key_c not in done:
            b_row = next(
                (r for r in _load_rows()
                 if (r["corpus"], r["seed"], r["condition"]) == (q["corpus"], q["seed"], "B")),
                None,
            )
            if b_row is not None and b_row.get("status") == "ok":
                claimed = b_row.get("claimed_pre_gate", b_row["claimed"])
                row = {
                    "corpus": q["corpus"], "seed": q["seed"], "condition": "C",
                    "model": _model_name(), "derived_from": "B",
                    "claimed": claimed,
                    "usage": {"input_tokens": 0, "output_tokens": 0,
                              "cache_read": 0, "cache_creation": 0,
                              "llm_calls": 0},
                    "wall_seconds": 0.0,
                    "metrics": measure_claims(q["db_path"], q["seed"], claimed),
                    "status": "ok",
                }
                _append_row(row)
                done.add(key_c)


# -- aggregation -------------------------------------------------------------

def _mean(vals: list[float]) -> float | None:
    return round(statistics.mean(vals), 4) if vals else None

def _median(vals: list[float]) -> float | None:
    return round(statistics.median(vals), 4) if vals else None


def _cost(rows: list[dict], prices: dict) -> float:
    """Dollar cost of the recorded usage under a price schedule."""
    total = 0.0
    for r in rows:
        u = r.get("usage") or {}
        cache_read = u.get("cache_read", 0)
        cache_creation = u.get("cache_creation", 0)
        uncached_in = max(u.get("input_tokens", 0) - cache_read - cache_creation, 0)
        total += (
            uncached_in * prices["in"]
            + cache_creation * prices["in"] * 1.25
            + cache_read * prices["in"] * 0.10
            + u.get("output_tokens", 0) * prices["out"]
        ) / 1_000_000
    return round(total, 4)


def aggregate() -> dict:
    rows = _load_rows()
    summary: dict = {"model": _model_name(), "n_rows": len(rows), "conditions": {}}
    for cond in ("A", "B", "C"):
        crows = [r for r in rows if r["condition"] == cond]
        ok = [r for r in crows if r.get("status") == "ok"]
        metrics = [r["metrics"] for r in ok]
        tokens = [r["usage"]["input_tokens"] + r["usage"]["output_tokens"] for r in ok]
        entry = {
            "name": CONDITION_NAMES[cond],
            "n_ok": len(ok),
            "n_error": len(crows) - len(ok),
        }
        for m in ("precision", "recall", "hallucinated_rate"):
            vals = [x[m] for x in metrics if x.get(m) is not None]
            entry[f"mean_{m}"] = _mean(vals)
            entry[f"median_{m}"] = _median(vals)
        entry["mean_tokens"] = _mean(tokens)
        entry["median_tokens"] = _median(tokens)
        entry["mean_wall_seconds"] = _mean([r["wall_seconds"] for r in ok])
        entry["median_wall_seconds"] = _median([r["wall_seconds"] for r in ok])
        entry["total_claims"] = sum(x["n_claims"] for x in metrics)
        entry["total_hallucinated"] = sum(x["n_hallucinated"] for x in metrics)
        summary["conditions"][cond] = entry
    summary["spend_usd"] = {
        sched: _cost(rows, prices) for sched, prices in PRICING.items()
    }
    usage_totals = {"input_tokens": 0, "output_tokens": 0, "cache_read": 0,
                    "cache_creation": 0, "llm_calls": 0}
    for r in rows:
        for k in usage_totals:
            usage_totals[k] += (r.get("usage") or {}).get(k, 0)
    summary["usage_totals"] = usage_totals
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=2))
    RESULTS_MD.write_text(_render_md(summary, rows))
    return summary


def _fmt(v, pct=False) -> str:
    if v is None:
        return "—"
    if pct:
        return f"{v * 100:.1f}%"
    return f"{v:,.1f}" if isinstance(v, float) else f"{v:,}"


def _render_md(summary: dict, rows: list[dict]) -> str:
    lines = [
        "# Impact analysis: graph-engineered workflow vs. freeform agent",
        "",
        f"Model: `{summary['model']}` for every condition. "
        "16 questions (8 seeds x 2 corpora: this repo itself + a generated "
        "30-file layered repo), ground truth = the code graph's reverse "
        "closure (depth <= 4, modules and the seed excluded).",
        "",
        "Fairness notes: the baseline prompt included a static listing of the "
        "repo's source files (orientation only — its two tools remain "
        "read_file and grep); claims that resolve to the seed symbol itself "
        "are excluded from every metric denominator. The ground truth is the "
        "same graph condition B traverses, so B's scores measure the "
        "workflow's fidelity to its substrate while A's measure what a "
        "freeform agent recovers without it.",
        "",
        "| Condition | n | Precision (mean/med) | Recall (mean/med) | "
        "Hallucinated rate (mean/med) | Mean tokens | Mean wall s |",
        "|---|---|---|---|---|---|---|",
    ]
    for cond in ("A", "B", "C"):
        e = summary["conditions"][cond]
        lines.append(
            f"| {CONDITION_NAMES[cond]} | {e['n_ok']}"
            + (f" ({e['n_error']} err)" if e["n_error"] else "")
            + f" | {_fmt(e['mean_precision'], pct=True)} / {_fmt(e['median_precision'], pct=True)}"
            f" | {_fmt(e['mean_recall'], pct=True)} / {_fmt(e['median_recall'], pct=True)}"
            f" | {_fmt(e['mean_hallucinated_rate'], pct=True)} / {_fmt(e['median_hallucinated_rate'], pct=True)}"
            f" | {_fmt(e['mean_tokens'])} | {_fmt(e['mean_wall_seconds'])} |"
        )
    lines += [
        "",
        "Condition C is derived from condition B's recorded pre-gate "
        "candidates (verified + dropped) rather than separate monkeypatched "
        "runs — the gate is the only difference, so this is exact for ring 1 "
        "and exact overall whenever the gate drops nothing; it re-uses B's "
        "LLM calls, so its tokens/wall are reported as 0.",
        "",
        "## Per-corpus breakdown",
        "",
        "| Corpus | Condition | Precision | Recall | Hallucinated |",
        "|---|---|---|---|---|",
    ]
    for corpus in ("real", "synth"):
        for cond in ("A", "B", "C"):
            ok = [r for r in rows
                  if r["condition"] == cond and r["corpus"] == corpus
                  and r.get("status") == "ok"]
            if not ok:
                continue
            p = _mean([r["metrics"]["precision"] for r in ok
                       if r["metrics"]["precision"] is not None])
            rc = _mean([r["metrics"]["recall"] for r in ok
                        if r["metrics"]["recall"] is not None])
            h = _mean([r["metrics"]["hallucinated_rate"] for r in ok
                       if r["metrics"]["hallucinated_rate"] is not None])
            lines.append(f"| {corpus} | {cond} | {_fmt(p, pct=True)} | "
                         f"{_fmt(rc, pct=True)} | {_fmt(h, pct=True)} |")
    lines += [
        "",
        "## Spend",
        "",
        f"Total recorded usage: {summary['usage_totals']['input_tokens']:,} input "
        f"(of which {summary['usage_totals']['cache_read']:,} cache reads, "
        f"{summary['usage_totals']['cache_creation']:,} cache writes), "
        f"{summary['usage_totals']['output_tokens']:,} output tokens over "
        f"{summary['usage_totals']['llm_calls']} LLM calls.",
        "",
    ]
    for sched, cost in summary["spend_usd"].items():
        lines.append(f"- {sched}: **${cost:.2f}**")
    lines += ["", "## Observations", ""]
    if OBSERVATIONS.exists():
        lines.append(OBSERVATIONS.read_text().strip())
    else:
        lines.append("_(pending: written after inspecting the data)_")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--aggregate" not in args:
        limit = None
        if "--limit" in args:
            limit = int(args[args.index("--limit") + 1])
        run_all(limit=limit)
    s = aggregate()
    print(json.dumps(s, indent=2))
