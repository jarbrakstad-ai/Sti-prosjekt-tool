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


def test_waypoints_list_matches_input_points():
    dem = make_tilted_plane_dem()
    xy = [(500100, y) for y in range(6600080, 6600010, -20)]
    pts = points_from_xy(xy)
    result = analyze_trail(pts, dem, Thresholds())

    waypoints = result["waypoints"]
    assert len(waypoints) == len(pts)
    assert waypoints[0]["distance_from_start_m"] == 0.0
    assert waypoints[-1]["distance_from_start_m"] == pytest.approx(result["summary"]["total_length_m"], abs=0.1)
    for wp, p in zip(waypoints, pts):
        assert wp["lat"] == pytest.approx(p.lat, abs=1e-5)
        assert wp["lon"] == pytest.approx(p.lon, abs=1e-5)
        assert isinstance(wp["elevation_m"], float)


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


def test_no_corner_recommendation_on_straight_fall_line_trail():
    dem = make_tilted_plane_dem()
    pts = points_from_xy([(500100, y) for y in range(6600080, 6600010, -20)])
    result = analyze_trail(pts, dem, Thresholds())
    assert result["corner_recommendations"] == []


def test_corner_recommendation_for_right_angle_turn_on_flat_terrain():
    dem = make_tilted_plane_dem(grade=0.0)
    pts = points_from_xy([(500100, 6600080), (500100, 6600060), (500120, 6600060)])
    result = analyze_trail(pts, dem, Thresholds())

    recs = result["corner_recommendations"]
    assert len(recs) == 1
    rec = recs[0]
    assert rec["turn_angle_deg"] == pytest.approx(90.0, abs=0.5)
    assert rec["estimated_radius_m"] == pytest.approx(12.73, abs=0.2)
    assert rec["recommended_bank_deg"] == pytest.approx(13.9, abs=0.5)
    assert rec["flags"] == []


def test_corner_recommendation_higher_bank_on_descending_terrain():
    flat_dem = make_tilted_plane_dem(grade=0.0)
    descending_dem = make_tilted_plane_dem(grade=0.15)
    pts = points_from_xy([(500100, 6600080), (500100, 6600060), (500120, 6600060)])

    flat_rec = analyze_trail(pts, flat_dem, Thresholds())["corner_recommendations"][0]
    descending_rec = analyze_trail(pts, descending_dem, Thresholds())["corner_recommendations"][0]

    assert descending_rec["recommended_bank_deg"] > flat_rec["recommended_bank_deg"]
    assert descending_rec["recommended_bank_deg"] == pytest.approx(18.1, abs=0.5)


def test_jump_opportunity_found_on_consistent_moderate_descent():
    dem = make_tilted_plane_dem(grade=0.15)  # jevn 15% nedoverbakke, rett fallinje
    pts = points_from_xy([(500100, y) for y in range(6600080, 6600010, -20)])
    result = analyze_trail(pts, dem, Thresholds())

    opps = result["jump_opportunities"]
    assert len(opps) == 1
    opp = opps[0]
    assert opp["avg_grade_pct"] == pytest.approx(-15.0, abs=0.5)
    assert opp["grade_variation_pct"] < 1.0
    assert opp["length_m"] > 50.0


def test_no_jump_opportunity_on_flat_contouring_trail():
    dem = make_tilted_plane_dem()
    pts = points_from_xy([(x, 6600050) for x in range(500020, 500190, 20)])
    result = analyze_trail(pts, dem, Thresholds())
    assert result["jump_opportunities"] == []


def test_no_jump_opportunity_when_grade_too_steep():
    dem = make_tilted_plane_dem(grade=0.50)  # 50% - for bratt for et enkelt naturlig hopp
    pts = points_from_xy([(500100, y) for y in range(6600080, 6600010, -20)])
    result = analyze_trail(pts, dem, Thresholds())
    assert result["jump_opportunities"] == []


def test_no_jump_opportunity_when_grade_varies_too_much():
    # Vekselvis -10% og -25% helning - begge enkeltvis innenfor terskelen, men
    # for stor variasjon mellom naboseg­menter til å regnes som én jevn skråning.
    elevations = [1000.0]
    for i in range(6):
        elevations.append(elevations[-1] - (1.0 if i % 2 == 0 else 2.5))
    dem = _flat_crossslope_dem(elevations)
    pts = points_from_xy([(500005 + 10 * i, 6600050) for i in range(len(elevations))])

    result = analyze_trail(pts, dem, Thresholds())
    assert result["jump_opportunities"] == []


def test_realistic_dem_noise_does_not_fabricate_violations():
    """Regresjonstest: en 1 m-oppløst DEM har typisk noen cm målestøy pr.
    piksel. Rå punkt-til-punkt-gradient forsterker denne støyen kraftig (et par
    cm avvik over 1-2 m gir flere prosentpoeng falsk helning), noe som tidligere
    ga ustabile/varierende funn (half-rule-brudd, brå helningsendring, ustabil
    maks-helning) på en trasé som i virkeligheten bare er en jevn 6 %-skråning.
    DemSampler sin gradient-utjevning (grade_smoothing_radius_m) skal dempe
    dette betydelig."""
    size = 200
    rng = np.random.default_rng(42)
    rows = np.arange(size)[:, None]
    clean_array = np.tile(1000.0 + 0.06 * np.arange(size), (size, 1))
    noisy_array = clean_array + rng.normal(0, 0.08, (size, size))  # 8 cm std, realistisk DTM-støy
    transform = Affine(1, 0, 500000, 0, -1, 6600100)

    dem_clean = DemSampler(array=clean_array, transform=transform, crs=UTM)
    dem_noisy = DemSampler(array=noisy_array, transform=transform, crs=UTM)

    pts = points_from_xy([(500020 + 2.0 * i, 6600050) for i in range(100)])

    clean_result = analyze_trail(pts, dem_clean, Thresholds())
    noisy_result = analyze_trail(pts, dem_noisy, Thresholds())

    assert clean_result["summary"]["max_grade_pct"] == pytest.approx(6.0, abs=0.1)
    # Uten utjevning target dette til over 12 % og fabrikkerte half-rule-/
    # brå-helningsbrudd; med utjevning skal maks-helning holde seg nær sannheten.
    assert noisy_result["summary"]["max_grade_pct"] < 9.0
    assert "half_rule_violation" not in noisy_result["summary"]["flag_counts"]
    assert "abrupt_grade_transition" not in noisy_result["summary"]["flag_counts"]
