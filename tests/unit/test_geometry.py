import numpy as np
import pytest

from surfclip.store.schemas import ZoneCorners
from surfclip.zone.geometry import (
    GeometryError,
    PoolMapping,
    distance_in_heights,
    point_in_polygon,
)

# Oblique view: far deck edge short and high in the image, near wave edge long and low.
OBLIQUE = ZoneCorners(
    deck_a=(400, 200), deck_b=(900, 220), wave_end_a=(100, 650), wave_end_b=(1200, 700)
)


def test_corners_map_to_unit_square_by_role() -> None:
    m = PoolMapping.from_corners(OBLIQUE)
    got = m.to_pool(
        np.array([OBLIQUE.deck_a, OBLIQUE.deck_b, OBLIQUE.wave_end_b, OBLIQUE.wave_end_a])
    )
    assert np.allclose(got, [(0, 0), (1, 0), (1, 1), (0, 1)], atol=1e-9)


def test_round_trip_image_pool_image() -> None:
    m = PoolMapping.from_corners(OBLIQUE)
    pts = np.array([(500.0, 400.0), (650.0, 300.0), (1000.0, 600.0)])
    assert np.allclose(m.to_image(m.to_pool(pts)), pts, atol=1e-6)


def test_perspective_far_side_pixels_cover_more_pool() -> None:
    """The same 50 px step is a bigger pool distance near the (far) deck than near the camera."""
    m = PoolMapping.from_corners(OBLIQUE)
    far = m.to_pool(np.array([(600, 230), (650, 230)]))
    near = m.to_pool(np.array([(600, 650), (650, 650)]))
    assert np.linalg.norm(far[1] - far[0]) > np.linalg.norm(near[1] - near[0])


def test_mirror_invariance() -> None:
    """Filming from the other side flips the image, but each physical point keeps its pool
    coordinates because corners are identified by role, not by image left/right."""
    width = 1280
    flip = lambda p: (width - p[0], p[1])  # noqa: E731
    mirrored = ZoneCorners(
        deck_a=flip(OBLIQUE.deck_a),
        deck_b=flip(OBLIQUE.deck_b),
        wave_end_a=flip(OBLIQUE.wave_end_a),
        wave_end_b=flip(OBLIQUE.wave_end_b),
    )
    pts = [(500.0, 400.0), (650.0, 300.0), (1000.0, 600.0)]
    a = PoolMapping.from_corners(OBLIQUE).to_pool(np.array(pts))
    b = PoolMapping.from_corners(mirrored).to_pool(np.array([flip(p) for p in pts]))
    assert np.allclose(a, b, atol=1e-9)


def test_degenerate_corners_are_rejected() -> None:
    collinear = ZoneCorners(
        deck_a=(0, 0), deck_b=(100, 0), wave_end_a=(200, 0), wave_end_b=(300, 0)
    )
    with pytest.raises(GeometryError):
        PoolMapping.from_corners(collinear)


def test_self_intersecting_corners_are_rejected() -> None:
    bowtie = ZoneCorners(deck_a=(0, 0), deck_b=(100, 0), wave_end_a=(100, 100), wave_end_b=(0, 100))
    with pytest.raises(GeometryError, match="cross"):
        PoolMapping.from_corners(bowtie)


def test_matrix_round_trips_through_schema_tuple() -> None:
    m = PoolMapping.from_corners(OBLIQUE)
    again = PoolMapping.from_matrix(m.as_tuple())
    pts = np.array([(500.0, 400.0)])
    assert np.allclose(m.to_pool(pts), again.to_pool(pts))


@pytest.mark.parametrize(
    ("pt", "inside"), [((0.5, 0.5), True), ((1.5, 0.5), False), ((0.0, 0.5), True)]
)
def test_point_in_polygon(pt: tuple[float, float], inside: bool) -> None:
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    assert point_in_polygon(pt, square) is inside


def test_distance_in_rider_heights() -> None:
    assert distance_in_heights((0, 0), (0, 300), box_height_px=100) == pytest.approx(3.0)
    with pytest.raises(GeometryError):
        distance_in_heights((0, 0), (1, 1), box_height_px=0)
