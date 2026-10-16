"""Whole-session processing for the browser UI: add a video, analyse it, re-run with settings.

Wraps the cached pipeline with one overall progress figure. Stage weights reflect typical run
times on the RTX 2060 (review copy and detection dominate; tracking and rides take seconds).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from surfclip.config import load_config
from surfclip.edits.log import append_edit, confirmed_zone, read_edits
from surfclip.store.schemas import EditTarget, Rides, StageName
from surfclip.store.session import SessionStore

Report = Callable[[float, str], None]

# Share of total time per stage (the rest are instant).
WEIGHTS: dict[StageName, float] = {
    "probe": 0.01,
    "review_copy": 0.41,
    "detect": 0.52,
    "track": 0.02,
    "rides": 0.01,
    "riders": 0.03,
}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv"}
LABELS: dict[StageName, str] = {
    "probe": "reading the video",
    "review_copy": "making the preview copy",
    "detect": "finding people",
    "track": "following people between frames",
    "rides": "finding rides",
    "riders": "telling riders apart",
}


class SourceNotAllowedError(ValueError):
    pass


def allowed_source(path: Path, source_dirs: list[str]) -> Path:
    """The video at ``path`` if it lies in one of the configured source folders."""
    resolved = path.resolve()
    if not any(resolved.is_relative_to(Path(d).resolve()) for d in source_dirs):
        raise SourceNotAllowedError(f"{path} is not in a configured source folder")
    if resolved.suffix.lower() not in VIDEO_SUFFIXES or not resolved.is_file():
        raise SourceNotAllowedError(f"{path} is not a video file")
    return resolved


def list_sources(source_dirs: list[str]) -> list[Path]:
    out: list[Path] = []
    for d in source_dirs:
        folder = Path(d)
        if folder.is_dir():
            out += [
                p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES
            ]
    return sorted(out, key=lambda p: p.name.lower())


def _overall(report: Report) -> Callable[[StageName, float, str], None]:
    order = list(WEIGHTS)

    def stage_progress(stage: StageName, fraction: float, message: str) -> None:
        if stage not in WEIGHTS:
            return
        before = sum(WEIGHTS[s] for s in order[: order.index(stage)])
        label = message if message not in ("running", "done") else LABELS[stage]
        report(before + WEIGHTS[stage] * fraction, label)

    return stage_progress


def process_session(store: SessionStore, config_path: Path, report: Report) -> dict[str, object]:
    """Analyse a session and find its rides, using the zone proposal when no zone has been
    confirmed and the proposal is reliable; otherwise stop before rides for the zone editor."""
    import torch

    from surfclip.stages import default_pipeline  # heavy imports (torch) only when processing
    from surfclip.zone.editing import zone_proposal

    cfg = load_config(config_path, store.session.config_overrides)
    has_zone = confirmed_zone(read_edits(store)) is not None
    gpu = torch.cuda.is_available()  # without one the detector falls back to the CPU itself

    def tell(fraction: float, message: str) -> None:
        report(fraction, message if gpu else f"{message} (no GPU found: on the CPU, much slower)")

    progress = _overall(tell)
    default_pipeline().run(store, cfg, until="track", progress=progress)
    proposal = None
    if not has_zone:
        # A reliable proposal is used straight away (recorded as an automatic confirmation, zone
        # origin "proposed") so rides are ready to review; the user can check it in the editor.
        tell(0.965, "proposing the wave zone")
        proposal = zone_proposal(store)
        if proposal is None or proposal.unreliable:
            return {
                "next": "zone",
                "proposal_confidence": proposal.confidence if proposal else None,
            }
        zone = proposal.zone.model_copy(update={"origin": "proposed"})
        append_edit(
            store,
            "confirm_zone",
            EditTarget(epoch_id=zone.epoch_id),
            {"zone": zone.model_dump(mode="json"), "how": "auto"},
        )
    default_pipeline().run(store, cfg, until="riders", progress=progress)
    rides = store.read_model("rides.json", Rides)
    return {
        "next": "review",
        "rides": len(rides.rides),
        "zone": "proposed" if proposal else "confirmed",
    }


def rerun_rides(
    store: SessionStore, config_path: Path, overrides: dict[str, object], report: Report
) -> dict[str, object]:
    """Re-run ride finding with changed settings (cached detection; edits are kept)."""
    from surfclip.stages import default_pipeline

    if confirmed_zone(read_edits(store)) is None:
        raise RuntimeError("set the wave zone first")
    store.session.config_overrides.update(overrides)
    store.save()
    cfg = load_config(config_path, store.session.config_overrides)  # raises on bad values
    report(0.1, "finding rides")
    default_pipeline().run(store, cfg, until="riders")
    rides = store.read_model("rides.json", Rides)
    return {"rides": len(rides.rides), "short_attempts": len(rides.short_attempts)}
