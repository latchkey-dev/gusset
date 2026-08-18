"""End-to-end CLI tests: index a fixture repo, query it back."""

import json
from pathlib import Path

from typer.testing import CliRunner

from gusset.cli import app

FIXTURE = Path(__file__).parent / "fixtures" / "pyproj"
runner = CliRunner()


def test_index_stats_deadcode_roundtrip(tmp_path):
    db = tmp_path / "graph.db"

    result = runner.invoke(app, ["index", str(FIXTURE), "--db", str(db)])
    assert result.exit_code == 0, result.output
    counts = json.loads(result.output)
    # 4 python files + pyproject.toml (manifest files row).
    assert counts["files"] == 5 and counts["edges"] > 0

    result = runner.invoke(app, ["stats", "--db", str(db)])
    assert result.exit_code == 0
    stats = json.loads(result.output)
    assert stats["files"] == 5

    result = runner.invoke(app, ["deadcode", "--db", str(db)])
    assert result.exit_code == 0
    dead = json.loads(result.output)
    assert "pkg.lib.unused_fn" in {d["qualname"] for d in dead}


def test_missing_db_is_a_clear_error(tmp_path):
    result = runner.invoke(app, ["stats", "--db", str(tmp_path / "nope.db")])
    assert result.exit_code == 1
