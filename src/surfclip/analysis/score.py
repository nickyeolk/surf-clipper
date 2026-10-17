"""How good a ride was, learned from the rides the user stars (004 US3, research R8).

Features come from the ride's analysis and are standardised over all of the user's analysed
rides (every session). Without enough stars the default weights from ``[score]`` apply; with at
least ``min_stars`` starred and as many unstarred rides, weights are fitted by L2-regularised
logistic regression (starred = 1). The fit is cached in ``artifacts/score.json`` and redone when
any session's analysis or edits change. The score explains itself with its largest parts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from surfclip.config import ScoreConfig
from surfclip.store.schemas import AnalysisFile, RideAnalysis, RideScore, Session
from surfclip.store.session import SessionStore

FloatArray = np.ndarray[Any, np.dtype[np.float64]]
SCORE_FILE = "score.json"
FEATURES = (
    "length_s",
    "clean_end",
    "compressions_per_10s",
    "depth",
    "rhythm",
    "tricks",
    "unclear",
)
# (said when the part helps, said when it hurts)
WORDS = {
    "length_s": ("long ride", "short ride"),
    "clean_end": ("clean finish", "fell at the end"),
    "compressions_per_10s": ("lots of turns and pumps", "few turns"),
    "depth": ("deep compressions", "shallow turns"),
    "rhythm": ("steady rhythm", "uneven rhythm"),
    "tricks": ("tricks", "no tricks"),
    "unclear": ("easy to see", "partly hidden"),
}


class ScoreModel(BaseModel):
    features: list[str]
    mean: list[float]
    std: list[float]
    weights: list[float]
    bias: float = 0.0
    fitted: bool = False  # False: default weights
    stars: int = 0
    rides: int = 0
    fingerprint: str = ""
    made_at: datetime


def features(a: RideAnalysis) -> list[float]:
    s = a.summary
    events = s.turns + s.pumps
    return [
        s.length_s,
        {"exit": 1.0, "fall": 0.0}.get(a.ending, 0.5),
        10 * events / max(s.length_s, 1e-6),
        1.0 - (s.mean_depth if s.mean_depth is not None else 1.0),
        1.0 - min(1.0, s.rhythm_cv if s.rhythm_cv is not None else 1.0),
        float(len(a.tricks)),
        a.shares.unclear,
    ]


def fit_logistic(
    x: FloatArray, y: FloatArray, l2: float, iters: int = 50
) -> tuple[FloatArray, float]:
    """Newton's method for L2-regularised logistic regression (bias not regularised)."""
    n, d = x.shape
    xb = np.hstack([x, np.ones((n, 1))])
    w = np.zeros(d + 1)
    reg = np.full(d + 1, l2)
    reg[-1] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(xb @ w)))
        grad = xb.T @ (p - y) + reg * w
        hess = xb.T @ (xb * (p * (1 - p))[:, None]) + np.diag(reg + 1e-9)
        step = np.linalg.solve(hess, grad)
        w -= step
        if float(np.abs(step).max()) < 1e-8:
            break
    return w[:-1], float(w[-1])


def build_model(
    rows: list[tuple[list[float], bool]], cfg: ScoreConfig, fingerprint: str
) -> ScoreModel:
    x = np.array([r[0] for r in rows], dtype=float).reshape(-1, len(FEATURES))
    y = np.array([1.0 if r[1] else 0.0 for r in rows])
    mean = x.mean(axis=0) if len(x) else np.zeros(len(FEATURES))
    std = x.std(axis=0) if len(x) else np.ones(len(FEATURES))
    std = np.where(std > 1e-9, std, 1.0)
    stars = int(y.sum())
    defaults = np.array([cfg.weights[f] for f in FEATURES], dtype=float)
    weights, bias, fitted = defaults, 0.0, False
    if stars >= cfg.min_stars and len(y) - stars >= cfg.min_stars:
        weights, bias = fit_logistic((x - mean) / std, y, cfg.l2)
        fitted = True
    return ScoreModel(
        features=list(FEATURES), mean=mean.tolist(), std=std.tolist(), weights=weights.tolist(),
        bias=bias, fitted=fitted, stars=stars, rides=len(y), fingerprint=fingerprint,
        made_at=datetime.now(UTC),
    )  # fmt: skip


def explain(parts: dict[str, float], n: int = 3) -> str:
    good = [WORDS[f][0] for f, v in sorted(parts.items(), key=lambda kv: -kv[1]) if v > 0.15][:n]
    bad = [WORDS[f][1] for f, v in sorted(parts.items(), key=lambda kv: kv[1]) if v < -0.15][:2]
    text = ", ".join(good)
    if bad:
        text = f"{text}; {', '.join(bad)}" if text else ", ".join(bad)
    return text[:1].upper() + text[1:] if text else "An average ride"


def score_ride(a: RideAnalysis, model: ScoreModel) -> RideScore:
    z = (np.array(features(a)) - np.array(model.mean)) / np.array(model.std)
    contrib = z * np.array(model.weights)
    raw = float(contrib.sum() + model.bias)
    parts = {f: round(float(c), 3) for f, c in zip(model.features, contrib, strict=True)}
    return RideScore(
        value=round(100 / (1 + np.exp(-raw)), 1), parts=parts, explanation=explain(parts)
    )


def _fingerprint(artifacts: Path) -> str:
    parts: list[str] = []
    for f in sorted(artifacts.glob("*/analysis.json")):
        edits = f.with_name("edits.json")
        parts.append(
            f"{f}:{f.stat().st_mtime_ns}:{edits.stat().st_mtime_ns if edits.exists() else 0}"
        )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def all_rides(artifacts: Path) -> list[RideAnalysis]:
    """Every analysed ride of every session, with stars and tags applied."""
    from surfclip.analysis.service import read_analysis, with_user_edits

    out: list[RideAnalysis] = []
    for f in sorted(artifacts.glob("*/analysis.json")):
        session = Session.model_validate_json(
            f.with_name("session.json").read_text(encoding="utf-8")
        )
        if session.kind == "reference":
            continue
        store = SessionStore(f.parent, session)
        result = read_analysis(store)
        if result is not None:
            out += with_user_edits(store, result).rides
    return out


def score_model(artifacts: Path, cfg: ScoreConfig) -> ScoreModel:
    fingerprint = (
        _fingerprint(artifacts) + hashlib.sha256(cfg.model_dump_json().encode()).hexdigest()[:8]
    )
    path = artifacts / SCORE_FILE
    if path.exists():
        try:
            cached = ScoreModel.model_validate_json(path.read_text(encoding="utf-8"))
            if cached.fingerprint == fingerprint:
                return cached
        except ValueError:
            pass
    model = build_model([(features(a), a.starred) for a in all_rides(artifacts)], cfg, fingerprint)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(model.model_dump(mode="json"), indent=2), encoding="utf-8")
    tmp.replace(path)
    return model


def apply_scores(result: AnalysisFile, artifacts: Path, cfg: ScoreConfig) -> AnalysisFile:
    model = score_model(artifacts, cfg)
    return result.model_copy(
        update={
            "rides": [a.model_copy(update={"score": score_ride(a, model)}) for a in result.rides]
        }
    )
