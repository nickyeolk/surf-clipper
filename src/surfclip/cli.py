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
from surfclip.detect.errors import ModelMissingError
from surfclip.edits.log import append_edit
from surfclip.eval.labels import (
    LabelError,
    LabelWork,
    SessionLabels,
    contained_ids,
    finalize,
    import_csv,
    propose,
)
from surfclip.eval.metrics import Span, evaluate
from surfclip.media.export import export_rides
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
        ModelMissingError,
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


@app.command()
def export(
    video: Path,
    rides: Annotated[str, typer.Option("--rides", help="Comma-separated ride ids.")] = "",
    artifacts: ArtifactsOpt = Path("artifacts"),
    config: ConfigOpt = DEFAULT_CONFIG_PATH,
    cpu: CpuOpt = False,
) -> None:
    """Export final-quality clips for new or changed rides (HDR kept)."""
    store = SessionStore.open(video, artifacts)
    if not store.path("rides.json").exists():
        raise _fail("no rides yet: run `surfclip run` first", 2)
    cfg = load_config(config, store.session.config_overrides)
    ids = [r.strip() for r in rides.split(",") if r.strip()] or None

    def progress(i: int, n: int, rid: str) -> None:
        typer.echo(f"  [{i}/{n}] {rid}", err=True)

    try:
        done, skipped = export_rides(store, cfg.export, ride_ids=ids, cpu=cpu, progress=progress)
    except RuntimeError as exc:
        raise _fail(str(exc), 1) from exc
    typer.echo(
        f"exported {len(done)} clips, {len(skipped)} already up to date -> {store.path('clips')}"
    )


@app.command()
def serve(
    artifacts: ArtifactsOpt = Path("artifacts"),
    config: ConfigOpt = DEFAULT_CONFIG_PATH,
    labels_dir: Annotated[Path, typer.Option("--labels-dir")] = Path("labels/rides"),
) -> None:
    """Start the local backend and browser UI (loopback only)."""
    import uvicorn

    from surfclip.api.app import create_app

    cfg = load_config(config)
    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if not (web_dist / "index.html").exists():
        typer.echo("note: web UI not built yet (cd web && npm run build); API only", err=True)
    url = f"http://localhost:{cfg.server.port}"
    typer.echo(f"Surf Session Clipper at {url}  (Ctrl+C to stop)", err=True)
    uvicorn.run(
        create_app(artifacts.resolve(), labels_dir.resolve(), web_dist, config.resolve()),
        host=cfg.server.host,
        port=cfg.server.port,
        log_level="warning",
    )


models_app = typer.Typer(no_args_is_help=True, help="Manage pretrained model weights.")
app.add_typer(models_app, name="models")


@models_app.command("download")
def models_download(config: ConfigOpt = DEFAULT_CONFIG_PATH) -> None:
    """Download the detector weights once (the tool's only network access)."""
    from surfclip.detect.detector import download_model

    path = download_model(load_config(config).detect)
    typer.echo(f"detector weights at {path}")


labels_app = typer.Typer(no_args_is_help=True, help="Propose and import hand labels.")
app.add_typer(labels_app, name="labels")
LabelsDirOpt = Annotated[Path, typer.Option("--labels-dir", help="Where label files live.")]


@labels_app.command("propose")
def labels_propose(
    video: Path,
    artifacts: ArtifactsOpt = Path("artifacts"),
    labels_dir: LabelsDirOpt = Path("labels/rides"),
) -> None:
    """Write labels/rides/<video>.csv from the detected rides, for the user to validate."""
    store = SessionStore.open(video, artifacts)
    if not store.path("rides.json").exists():
        raise _fail("no rides yet: run `surfclip run` first", 2)
    out = labels_dir / f"{video.stem}.csv"
    if out.exists():
        raise _fail(f"{out} exists; not overwriting validated labels", 2)
    n = propose(store.read_model("rides.json", Rides), out)
    typer.echo(f"{n} proposed rides -> {out}")


@labels_app.command("import")
def labels_import(csv_file: Path, video_name: Annotated[str, typer.Option("--video")] = "") -> None:
    """Convert a validated CSV into labels/rides/<name>.json."""
    try:
        labels = import_csv(csv_file, video_name or csv_file.stem)
    except LabelError as exc:
        raise _fail(str(exc), 2) from exc
    out = csv_file.with_suffix(".json")
    out.write_text(labels.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"{len(labels.rides)} labelled rides -> {out}")


@labels_app.command("finalize")
def labels_finalize(work_file: Path) -> None:
    """Re-write labels/rides/<name>.json from its .work.json (e.g. after a rule change)."""
    work = LabelWork.model_validate_json(work_file.read_text(encoding="utf-8"))
    try:
        labels = finalize(work)
    except LabelError as exc:
        raise _fail(str(exc), 2) from exc
    out = work_file.with_name(work_file.name.replace(".work.json", ".json"))
    out.write_text(labels.model_dump_json(indent=2), encoding="utf-8")
    inside = len(contained_ids(work.items))
    typer.echo(f"{len(labels.rides)} labelled rides -> {out} ({inside} merged into longer rides)")


@app.command("eval")
def eval_cmd(
    video: Path,
    artifacts: ArtifactsOpt = Path("artifacts"),
    labels_dir: LabelsDirOpt = Path("labels/rides"),
    as_json: JsonOpt = False,
) -> None:
    """Score a session's rides against its validated labels (SC-001..SC-003)."""
    store = SessionStore.open(video, artifacts)
    label_file = labels_dir / f"{video.stem}.json"
    if not label_file.exists():
        raise _fail(f"no validated labels at {label_file}", 2)
    labels = SessionLabels.model_validate_json(label_file.read_text(encoding="utf-8"))
    # Score the tool's own detections: rides.json also contains the user's review edits.
    rides = store.read_model("rides.detected.json", Rides)
    m = evaluate(
        [Span(r.start_s, r.end_s) for r in rides.rides],
        labels.rides,
        min_length_s=rides.settings.min_length_s,
        pad_before_s=rides.settings.pad_before_s,
        pad_after_s=rides.settings.pad_after_s,
    )
    if as_json:
        typer.echo(json.dumps(m.__dict__, indent=2))
        return
    added = sum(1 for r in labels.rides if r.origin == "added")
    acid = sorted(m.acid_start_errs)
    typer.echo(
        f"recall      {m.recall:6.1%}  ({m.n_labels - len(m.missed)}/{m.n_labels})  "
        f"target >= 95%\n"
        f"precision   {m.precision:6.1%}  ({m.n_detected - len(m.false_rides)}/{m.n_detected})  "
        f"target >= 90%\n"
        f"complete    {m.completeness:6.1%}  ({m.n_labels - len(m.incomplete)}/{m.n_labels} rides "
        f"fully inside their clip)  target >= 95%\n"
        f"tightness   {m.overhang_p95:5.2f} s  (clip beyond the ride, p95)  target <= 3 s\n"
        f"diagnostics: start error p95 {m.start_err_p95:.2f}s, end error p95 "
        f"{m.end_err_p95:.2f}s; acid-drop start error p95 "
        f"{(acid[int(0.95 * (len(acid) - 1))] if acid else 0):.2f}s; "
        f"rides the user added (tool misses): {added}"
    )


if __name__ == "__main__":
    app()
