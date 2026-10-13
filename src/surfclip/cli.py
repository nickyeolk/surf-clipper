"""Command-line interface (contracts/cli.md). Commands are added as tasks land.

Exit codes: 0 success, 1 processing error, 2 invalid input. ``--json`` prints machine-readable
output to stdout; human messages and logs go to stderr.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from surfclip import __version__
from surfclip.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from surfclip.media.probe import UnsupportedInputError, probe
from surfclip.stages import default_pipeline
from surfclip.store.schemas import SourceInfo
from surfclip.store.session import SessionStore, SourceLocationError

app = typer.Typer(no_args_is_help=True, help="Surf Session Clipper", add_completion=False)

ArtifactsOpt = Annotated[Path, typer.Option("--artifacts", help="Folder for session outputs.")]
ConfigOpt = Annotated[Path, typer.Option("--config", help="Config file (TOML).")]
JsonOpt = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")]


def _fail(message: str, code: int) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(code)


def _describe(info: SourceInfo) -> str:
    mins = info.duration_s / 60
    vfr = ", variable frame rate" if info.is_vfr else ""
    hdr = "SDR" if info.hdr_format == "none" else info.hdr_format.upper()
    return (
        f"{Path(info.path).name}: {info.codec} {info.width}x{info.height} "
        f"{info.avg_fps:.2f} fps{vfr}, {info.bit_depth}-bit {hdr}, {mins:.1f} min"
    )


@app.command()
def version() -> None:
    """Print the surfclip version."""
    typer.echo(__version__)


@app.command("probe")
def probe_cmd(video: Path, as_json: JsonOpt = False) -> None:
    """Read a video's metadata and check it can be processed."""
    try:
        info = probe(video)
    except UnsupportedInputError as exc:
        raise _fail(str(exc), 2) from exc
    typer.echo(info.model_dump_json(indent=2) if as_json else _describe(info))


@app.command()
def ingest(
    video: Path,
    min_length: Annotated[
        float | None,
        typer.Option("--min-length", help="Minimum ride length in seconds (default 10)."),
    ] = None,
    artifacts: ArtifactsOpt = Path("artifacts"),
    config: ConfigOpt = DEFAULT_CONFIG_PATH,
    as_json: JsonOpt = False,
) -> None:
    """Create (or reopen) a session for VIDEO and run the ingest stages."""
    try:
        store = SessionStore.open(video, artifacts)
        if min_length is not None:
            store.session.config_overrides["rides.min_length_s"] = min_length
            store.save()
        cfg = load_config(config, store.session.config_overrides)
        report = default_pipeline().run(store, cfg, until="probe")
    except (UnsupportedInputError, SourceLocationError, ConfigError, FileNotFoundError) as exc:
        raise _fail(str(exc), 2) from exc
    except Exception as exc:
        raise _fail(f"{type(exc).__name__}: {exc}", 1) from exc
    info = store.read_model("probe.json", SourceInfo)
    if as_json:
        out = {
            "session_id": store.session.session_id,
            "folder": str(store.root),
            "ran": report.ran,
            "cache_hits": report.cache_hits,
        }
        typer.echo(json.dumps(out, indent=2))
    else:
        typer.echo(f"session {store.session.session_id} -> {store.root}", err=True)
        typer.echo(_describe(info))


if __name__ == "__main__":
    app()
