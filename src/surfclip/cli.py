"""Command-line interface (contracts/cli.md). Commands are added as tasks land.

Exit codes: 0 success, 1 processing error, 2 invalid input. ``--json`` prints machine-readable
output to stdout; human messages and logs go to stderr.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from surfclip import __version__
from surfclip.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from surfclip.edits.log import append_edit
from surfclip.media.probe import UnsupportedInputError, probe
from surfclip.stages import ZoneNotConfirmedError, default_pipeline
from surfclip.store.schemas import EditTarget, Rides, SourceInfo, StageName, Zone
from surfclip.store.session import SessionStore, SourceLocationError
from surfclip.zone.geometry import GeometryError, PoolMapping

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


@app.command()
def zone(
    video: Path,
    from_file: Annotated[Path, typer.Option("--from-file", help="Zone JSON to confirm.")],
    epoch: Annotated[int, typer.Option("--epoch", help="Camera epoch.")] = 0,
    artifacts: ArtifactsOpt = Path("artifacts"),
) -> None:
    """Confirm the wave zone for VIDEO from a file (until the zone editor exists)."""
    try:
        store = SessionStore.open(video, artifacts)
        z = Zone.model_validate_json(from_file.read_text(encoding="utf-8"))
        z = z.model_copy(update={"epoch_id": epoch, "origin": "user"})
        PoolMapping.from_corners(z.corners)
    except (SourceLocationError, FileNotFoundError, ValidationError, GeometryError) as exc:
        raise _fail(str(exc), 2) from exc
    edit = append_edit(
        store,
        "confirm_zone",
        EditTarget(epoch_id=epoch),
        {"zone": z.model_dump(mode="json"), "how": "file"},
    )
    typer.echo(f"zone confirmed for epoch {epoch} (edit {edit.edit_id})")


def _run(
    video: Path, until: StageName, artifacts: Path, config: Path, cpu: bool, timings: bool
) -> SessionStore:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        store = SessionStore.open(video, artifacts)
        cfg = load_config(config, store.session.config_overrides)
        report = default_pipeline(cpu=cpu).run(store, cfg, until=until)
    except (
        UnsupportedInputError,
        SourceLocationError,
        ConfigError,
        FileNotFoundError,
        ZoneNotConfirmedError,
    ) as exc:
        raise _fail(str(exc), 2) from exc
    except Exception as exc:
        raise _fail(f"{type(exc).__name__}: {exc}", 1) from exc
    if timings:
        for stage in report.cache_hits:
            typer.echo(f"  {stage:8s} cached", err=True)
        for stage, secs in report.seconds.items():
            typer.echo(f"  {stage:8s} {secs / 60:6.1f} min", err=True)
    return store


def _summarise(store: SessionStore, as_json: bool) -> None:
    rides = store.read_model("rides.json", Rides)
    if as_json:
        typer.echo(rides.model_dump_json(indent=2))
        return
    typer.echo(f"{len(rides.rides)} rides, {len(rides.short_attempts)} short attempts")
    for r in rides.rides:
        flags = [k for k, v in r.flags.model_dump().items() if v]
        typer.echo(
            f"  {r.ride_id}  {_clock(r.start_s)}-{_clock(r.end_s)}  {r.length_s:5.1f}s  "
            f"conf {r.confidence:.2f}  {r.start_kind:9s} {' '.join(flags)}"
        )


def _clock(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    return f"{int(m):02d}:{s:05.2f}"


CpuOpt = Annotated[bool, typer.Option("--cpu", help="Run detection on the CPU.")]
TimingsOpt = Annotated[bool, typer.Option("--timings", help="Print stage timings.")]


@app.command()
def analyse(
    video: Path,
    artifacts: ArtifactsOpt = Path("artifacts"),
    config: ConfigOpt = DEFAULT_CONFIG_PATH,
    cpu: CpuOpt = False,
    timings: TimingsOpt = False,
) -> None:
    """Detect and track people in VIDEO (the slow part; cached afterwards)."""
    _run(video, "track", artifacts, config, cpu, timings)
    typer.echo("analysis done")


@app.command()
def run(
    video: Path,
    artifacts: ArtifactsOpt = Path("artifacts"),
    config: ConfigOpt = DEFAULT_CONFIG_PATH,
    cpu: CpuOpt = False,
    timings: TimingsOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Run the whole pipeline for VIDEO and list the rides (needs a confirmed zone)."""
    store = _run(video, "rides", artifacts, config, cpu, timings)
    _summarise(store, as_json)


if __name__ == "__main__":
    app()
