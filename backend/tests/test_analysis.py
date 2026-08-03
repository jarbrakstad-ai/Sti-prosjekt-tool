"""Enhetstester for kjerneanalysen med syntetiske DEM-er (ingen filer nødvendig)."""
from __future__ import annotations

import numpy as np
import pytest
from affine import Affine
from pyproj import Transformer

from app.analysis import Thresholds, analyze_trail
from app.dem import DemSampler
from app.gpx_io import TrailPoint

UTM = "EPSG:32633"
to_wgs84 = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True)


def latlon(x: float, y: float) -> tuple[float, float]:
    lon, lat = to_wgs84.transform(x, y)
    return lat, lon


def make_tilted_plane_dem(size: int = 200, grade: float = 0.10) -> DemSampler:
    """DEM som er en jevn skråning: heller `grade` (f.eks 0.10 = 10%) nedover sørover."""
    rows = np.arange(size)[:, None]
    array = np.tile(1000.0 - grade * rows, (1, size))
    transform = Affine(1, 0, 500000, 0, -1, 6600100)
    return DemSampler(array=array, transform=transform, crs=UTM)


def points_from_xy(xy: list[tuple[float, float]], ele: float | None = None) -> list[TrailPoint]:
    return [TrailPoint(*latlon(x, y), ele=ele) for x, y in xy]


def test_fall_line_trail_is_flagged_high_risk():
    dem = make_tilted_plane_dem()
    pts = points_from_xy([(500100, y) for y in range(6600080, 6600010, -20)])
    result = analyze_trail(pts, dem, Thresholds())
    flags = {f for seg in result["segments"] for f in seg["flags"]}
    assert "fall_line_high_risk" in flags
    assert "half_rule_violation" not in flags


def test_contouring_trail_is_clean():
    dem = make_tilted_plane_dem()
    pts = points_from_xy([(x, 6600050) for x in range(500020, 500190, 20)])
    result = analyze_trail(pts, dem, Thresholds())
    for seg in result["segments"]:
        assert seg["flags"] == []
    assert abs(result["summary"]["avg_grade_pct"]) < 0.5


def test_diagonal_trail_half_rule_and_moderate_fall_line():
    dem = make_tilted_plane_dem()
    import math

    theta = math.radians(20)
    start = (500050.0, 6600090.0)
    dx, dy = math.sin(theta), -math.cos(theta)
    end = (start[0] + 100 * dx, start[1] + 100 * dy)
    pts = points_from_xy([start, end])

    result = analyze_trail(pts, dem, Thresholds())
    seg = result["segments"][0]

    assert seg["half_rule_ratio"] == pytest.approx(2.75, abs=0.1)
    assert seg["fall_line_angle_deg"] == pytest.approx(20.0, abs=1.0)
    assert "half_rule_violation" in seg["flags"]
    assert "fall_line_moderate_risk" in seg["flags"]
    assert "steep_grade" not in seg["flags"]


def _flat_crossslope_dem(elevations: list[float], dx: float = 10.0) -> DemSampler:
    n = len(elevations)
    array = np.tile(np.array(elevations, dtype=float), (5, 1))
    transform = Affine(dx, 0, 500000, 0, -1, 6600100)
    return DemSampler(array=array, transform=transform, crs=UTM)


def test_sustained_descent_without_reversal_is_flagged():
    elevations = [1000.0 - 0.5 * i for i in range(25)]
    dem = _flat_crossslope_dem(elevations)
    pts = points_from_xy([(500005 + 10 * i, 6600050) for i in range(25)])

    result = analyze_trail(pts, dem, Thresholds())
    flags = {f for seg in result["segments"] for f in seg["flags"]}
    assert "missing_grade_reversal" in flags


def test_descent_with_frequent_reversals_is_not_flagged():
    z = 1000.0
    elevations = []
    for i in range(25):
        elevations.append(z)
        z += 0.3 if i % 3 == 2 else -0.6
    dem = _flat_crossslope_dem(elevations)
    pts = points_from_xy([(500005 + 10 * i, 6600050) for i in range(25)])

    result = analyze_trail(pts, dem, Thresholds())
    flags = {f for seg in result["segments"] for f in seg["flags"]}
    assert "missing_grade_reversal" not in flags


def test_requires_at_least_two_points():
    dem = make_tilted_plane_dem()
    with pytest.raises(ValueError):
        analyze_trail(points_from_xy([(500100, 6600050)]), dem, Thresholds())
