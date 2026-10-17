"""004 T022: best-rides score (defaults, fit to stars, explanation)."""

import numpy as np

from surfclip.analysis.score import FEATURES, build_model, explain, features, score_ride
from surfclip.config import load_config
from surfclip.store.schemas import RideAnalysis, RideShares, RideSummary

CFG = load_config().score


def _ride(
    rid: str, length: float, ending: str = "exit", depth: float = 0.7, starred: bool = False
) -> RideAnalysis:
    return RideAnalysis(
        ride_id=rid, span=(0.0, length), rider="me", cache_key="k", keypoints_key="k", fps=15,
        t0=0.0, ending=ending, ending_auto=ending,  # type: ignore[arg-type]
        summary=RideSummary(length_s=length, turns=4, pumps=2, rhythm_cv=0.3, mean_depth=depth),
        shares=RideShares(unclear=0.05), starred=starred,
    )  # fmt: skip


def test_features_follow_the_analysis() -> None:
    f = dict(zip(FEATURES, features(_ride("a", 30.0, "fall", 0.6)), strict=True))
    assert f["length_s"] == 30.0 and f["clean_end"] == 0.0
    assert f["compressions_per_10s"] == 2.0 and abs(f["depth"] - 0.4) < 1e-9


def test_defaults_with_few_stars() -> None:
    rides = [_ride(f"r{i}", 20.0 + i) for i in range(10)]
    model = build_model([(features(r), i < 2) for i, r in enumerate(rides)], CFG, "fp")
    assert not model.fitted and model.weights[0] == CFG.weights["length_s"]
    scores = [score_ride(r, model).value for r in rides]
    assert scores == sorted(scores)  # longer = better by default


def test_fit_learns_what_the_user_stars() -> None:
    rng = np.random.default_rng(0)
    rides = []
    for i in range(40):
        deep = rng.uniform(0.5, 0.95)
        # the user stars deep rides regardless of length
        rides.append(_ride(f"r{i}", float(rng.uniform(15, 60)), depth=deep, starred=deep < 0.65))
    model = build_model([(features(r), r.starred) for r in rides], CFG, "fp")
    assert model.fitted
    w = dict(zip(FEATURES, model.weights, strict=True))
    assert w["depth"] > abs(w["length_s"])
    ranked = sorted(rides, key=lambda r: -score_ride(r, model).value)
    top = ranked[: sum(r.starred for r in rides)]
    assert sum(r.starred for r in top) / len(top) > 0.8


def test_explanation_in_words() -> None:
    assert (
        explain({"length_s": 1.2, "depth": 0.6, "clean_end": -0.9})
        == "Long ride, deep compressions; fell at the end"
    )
    assert explain({"length_s": 0.01}) == "An average ride"
