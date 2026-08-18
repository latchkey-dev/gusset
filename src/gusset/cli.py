"""Gusset command-line interface.

Commands land phase by phase:
  index / stats / deadcode  — phase 1 (graph substrate, no LLM)
  impact                    — phase 2
  atlas / docs-drift        — phase 5
  watch / init              — phase 6 (autonomous mode)
"""

import typer

from gusset import __version__

app = typer.Typer(
    name="gusset",
    help="An autonomous repo custodian, engineered as graphs.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """An autonomous repo custodian, engineered as graphs."""


@app.command()
def version() -> None:
    """Print the Gusset version."""
    typer.echo(f"gusset {__version__}")
