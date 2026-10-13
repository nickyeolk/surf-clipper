"""Command-line interface. Commands are added per contracts/cli.md as tasks land."""

import typer

from surfclip import __version__

app = typer.Typer(no_args_is_help=True, help="Surf Session Clipper")


@app.command()
def version() -> None:
    """Print the surfclip version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
