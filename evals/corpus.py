"""Fixture corpora for the impact experiment.

Two corpora, both indexed with gusset's own indexer into scratch DBs under
evals/.work/:

  real   — this repository itself (evals/, .gusset/ excluded from the index
           so the experiment cannot contaminate its own ground truth).
  synth  — a generated ~30-file layered repo (core -> domain -> services ->
           api -> app) with known deep call chains. Deterministic seed.

Seed symbols are selected by querying the graph: non-module symbols whose
reverse closure (depth <= 4, modules and the seed itself excluded) has >= 3
members at >= 2 distinct depths. Eight per corpus, spread across closure
sizes, persisted to evals/.work/seeds.json so reruns stay stable.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from gusset.graph import indexer
from gusset.graph.indexer import index_repo
from gusset.graph.store import GraphStore

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
WORK_DIR = EVALS_DIR / ".work"
SEEDS_FILE = WORK_DIR / "seeds.json"

# Never index the experiment itself (or gusset's own scratch state) into the
# ground-truth graph of the "real" corpus.
EXTRA_SKIP = {"evals", ".gusset"}

MAX_DEPTH = 4          # closure depth cap, matches workflows.impact.MAX_DEPTH
N_SEEDS = 8
MIN_CLOSURE = 3
SYNTH_SEED = 20260817  # deterministic generator seed


@dataclass(frozen=True)
class Corpus:
    name: str
    repo_root: Path
    db_path: Path


def _index(repo: Path, db: Path) -> dict:
    """index_repo with the experiment dirs excluded (runtime-only tweak)."""
    original = indexer.SKIP_DIRS
    indexer.SKIP_DIRS = original | EXTRA_SKIP
    try:
        return index_repo(repo, db)
    finally:
        indexer.SKIP_DIRS = original


def build_real_corpus() -> Corpus:
    db = WORK_DIR / "real.db"
    if not db.exists():
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        _index(REPO_ROOT, db)
    return Corpus("real", REPO_ROOT, db)


def build_synth_corpus() -> Corpus:
    repo = WORK_DIR / "synth_repo"
    db = WORK_DIR / "synth.db"
    if not repo.exists():
        generate_synthetic_repo(repo, seed=SYNTH_SEED)
    if not db.exists():
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        _index(repo, db)
    return Corpus("synth", repo, db)


# -- synthetic repo generator ------------------------------------------------

LAYERS = [("core", 6), ("domain", 6), ("services", 7), ("api", 6), ("app", 5)]


def generate_synthetic_repo(dest: Path, seed: int = SYNTH_SEED) -> None:
    """~30 files / ~150 non-module symbols in a strict layered architecture.

    Every function name is globally unique (``<layer><i>_alpha`` etc.) so the
    indexer's unique-global-name resolution produces exact cross-file call
    edges. Within a file: beta -> alpha, gamma -> beta, Widget.run -> gamma,
    launch -> Widget — so a change to ``<layer><i>_alpha`` has a known chain
    of dependents in-file, and upper layers call lower layers' gamma/beta,
    which makes reverse closures 4+ levels deep.
    """
    rnd = random.Random(seed)
    dest.mkdir(parents=True, exist_ok=True)
    for li, (lname, count) in enumerate(LAYERS):
        layer_dir = dest / lname
        layer_dir.mkdir(exist_ok=True)
        for i in range(count):
            p = f"{lname}{i}"
            cls = f"{lname.capitalize()}{i}Widget"
            lines = [f'"""{lname} layer, module {i} (generated, deterministic)."""', ""]
            if li == 0:
                alpha_body = f"    return value + {i}"
                gamma_extra = ""
            else:
                lower_name, lower_count = LAYERS[li - 1]
                t1 = rnd.randrange(lower_count)
                t2 = rnd.randrange(lower_count)
                fn1 = f"{lower_name}{t1}_gamma"
                fn2 = f"{lower_name}{t2}_beta"
                lines += [
                    f"from {lower_name}.{lower_name}{t1} import {fn1}",
                    f"from {lower_name}.{lower_name}{t2} import {fn2}",
                    "",
                ]
                alpha_body = f"    return {fn1}(value) + 1"
                gamma_extra = f" + {fn2}(value)"
            lines += [
                "",
                f"def {p}_alpha(value):",
                f'    """Leaf computation for {p}."""',
                alpha_body,
                "",
                "",
                f"def {p}_beta(value):",
                f'    """Doubles the {p} alpha result."""',
                f"    return {p}_alpha(value) * 2",
                "",
                "",
                f"def {p}_gamma(value):",
                f'    """Aggregates {p} results."""',
                f"    return {p}_beta(value){gamma_extra}",
                "",
                "",
                f"class {cls}:",
                f'    """Widget facade over the {p} pipeline."""',
                "",
                "    def run(self, value):",
                f"        return {p}_gamma(value)",
                "",
                "",
                f"def {p}_launch(value):",
                f'    """Entry point: builds and runs the {p} widget."""',
                f"    widget = {cls}()",
                "    return widget.run(value)",
                "",
            ]
            (layer_dir / f"{lname}{i}.py").write_text("\n".join(lines))


# -- seed selection ----------------------------------------------------------

def closure_truth(store: GraphStore, seed_qualname: str,
                  max_depth: int = MAX_DEPTH) -> dict[str, int]:
    """Ground truth: {qualname: min_depth} of the reverse closure of the seed,
    depth capped, modules excluded, the seed itself excluded."""
    sym = store.symbol_by_qualname(seed_qualname)
    if sym is None:
        return {}
    closure = store.reverse_closure([sym.id], max_depth=max_depth)
    truth: dict[str, int] = {}
    for sid, depth in closure.items():
        if depth == 0:
            continue
        s = store.symbol_by_id(sid)
        if s is None or s.kind == "module" or s.qualname == seed_qualname:
            continue
        truth[s.qualname] = depth
    return truth


def select_seeds(db_path: Path, n: int = N_SEEDS) -> list[dict]:
    """Deterministically pick n seeds with non-trivial, mixed-depth closures,
    spread across closure sizes."""
    store = GraphStore(db_path)
    try:
        symbols = [
            s
            for syms in store.module_clusters().values()  # sorted, deterministic
            for s in syms
            if s.kind != "module"
        ]
        candidates = []
        for sym in symbols:
            truth = closure_truth(store, sym.qualname)
            if len(truth) >= MIN_CLOSURE and len(set(truth.values())) >= 2:
                candidates.append({
                    "seed": sym.qualname,
                    "closure_size": len(truth),
                    "depths": sorted(set(truth.values())),
                })
        candidates.sort(key=lambda c: (c["closure_size"], c["seed"]))
        if len(candidates) <= n:
            return candidates
        idxs = list(dict.fromkeys(
            round(i * (len(candidates) - 1) / (n - 1)) for i in range(n)
        ))
        chosen = [candidates[i] for i in idxs]
        # top up (deduped evenly-spaced indices can fall short of n)
        for c in candidates:
            if len(chosen) >= n:
                break
            if c not in chosen:
                chosen.append(c)
        return chosen[:n]
    finally:
        store.close()


def load_questions() -> list[dict]:
    """All 16 questions: {corpus, repo_root, db_path, seed, closure_size}.

    Seed choices are persisted so a resumed run measures the same questions.
    """
    if SEEDS_FILE.exists():
        return json.loads(SEEDS_FILE.read_text())
    corpora = [build_real_corpus(), build_synth_corpus()]
    questions = []
    for corpus in corpora:
        for entry in select_seeds(corpus.db_path):
            questions.append({
                "corpus": corpus.name,
                "repo_root": str(corpus.repo_root),
                "db_path": str(corpus.db_path),
                "seed": entry["seed"],
                "closure_size": entry["closure_size"],
                "depths": entry["depths"],
            })
    SEEDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEDS_FILE.write_text(json.dumps(questions, indent=2))
    return questions


if __name__ == "__main__":
    for q in load_questions():
        print(f"{q['corpus']:5}  closure={q['closure_size']:3}  depths={q['depths']}  {q['seed']}")
