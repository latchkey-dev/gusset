from typer.testing import CliRunner

from gusset import __version__
from gusset.cli import app

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    assert "self-healing repo upkeep" in result.output
