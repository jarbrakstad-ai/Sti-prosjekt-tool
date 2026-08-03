"""Tester for terreng-gitteret brukt til 3D-visning, inkl. at det stemmer
geometrisk overens med trasépunktenes x_m/y_m fra analyze_trail."""
from __future__ import annotations

import numpy as np
import pytest
from affine import Affine
from pyproj import Transformer

from app.analysis import Thresholds, analyze_trail
from app.dem import DemSampler
from app.gpx_io import TrailPoint
from app.terrain_grid import build_terrain_grid

UTM = "EPSG:32633"
to_wgs84 = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True)


def latlon(x: float, y: float) -> tuple[float, float]:
    lon, lat = to_wgs84.transform(x, y)
    return lat, lon


def make_tilted_plane_dem(size: int = 50, grade: float = 0.10) -> DemSampler:
    rows = np.arange(size)[:, None]
    array = np.tile(1000.0 - grade * rows, (1, size))
    transform = Affine(1, 0, 500000, 0, -1, 6600100)
    return DemSampler(array=array, transform=transform, crs=UTM)


def test_grid_downsampling_dimensions_and_cell_size():
    dem = make_tilted_plane_dem(size=200, grade=0.0)
    grid = build_terrain_grid(dem, max_dim=50)

    assert grid["rows"] == 50
    assert grid["cols"] == 50
    assert grid["cell_size_x_m"] == pytest.approx(4.0)
    assert grid["cell_size_y_m"] == pytest.approx(4.0)
    assert len(grid["elevations"]) == 50
    assert len(grid["elevations"][0]) == 50


def test_grid_no_downsampling_when_within_max_dim():
    dem = make_tilted_plane_dem(size=50, grade=0.10)
    grid = build_terrain_grid(dem, max_dim=150)

    assert grid["rows"] == 50
    assert grid["cols"] == 50
    assert grid["cell_size_x_m"] == pytest.approx(1.0)
    assert grid["elevations"][0][0] == pytest.approx(1000.0, abs=0.05)
    # rad 49 (siste) skal være 4.9 m lavere enn rad 0 ved 10 % helning over 49 m
    assert grid["elevations"][49][0] == pytest.approx(1000.0 - 4.9, abs=0.05)


def test_grid_fills_nan_instead_of_producing_holes():
    dem = make_tilted_plane_dem(size=50, grade=0.0)
    dem.array[0, 0] = np.nan
    grid = build_terrain_grid(dem, max_dim=150)
    assert not any(np.isnan(v) for row in grid["elevations"] for v in row)


def test_terrain_grid_aligns_with_waypoint_local_coordinates():
    """Kritisk konsistens-test: en trasé sitt waypoint på DEM-ens (0,0)-pikselsenter
    skal ha x_m/y_m som stemmer med terreng-gitterets origin (samme koordinatsystem),
    selv om de beregnes av to forskjellige funksjoner i to separate kall."""
    dem = make_tilted_plane_dem(size=50, grade=0.10)

    x0, y0 = dem.rowcol_to_xy(np.array([0]), np.array([0]))
    x1, y1 = dem.rowcol_to_xy(np.array([20]), np.array([20]))
    pts = [
        TrailPoint(*latlon(float(x0[0]), float(y0[0]))),
        TrailPoint(*latlon(float(x1[0]), float(y1[0]))),
    ]

    result = analyze_trail(pts, dem, Thresholds())
    wp0 = result["waypoints"][0]

    grid = build_terrain_grid(dem, max_dim=150)

    assert wp0["x_m"] == pytest.approx(grid["origin_x_m"], abs=1e-2)
    assert wp0["y_m"] == pytest.approx(grid["origin_y_m"], abs=1e-2)

    # Grid-vertex (rad 20, kolonne 20) sin lokale posisjon, rekonstruert fra
    # origin + indeks * cellestørrelse, skal stemme med waypoint 1 sin x_m/y_m.
    reconstructed_x = grid["origin_x_m"] + 20 * grid["cell_size_x_m"]
    reconstructed_y = grid["origin_y_m"] + 20 * grid["cell_size_y_m"]
    wp1 = result["waypoints"][1]
    assert wp1["x_m"] == pytest.approx(reconstructed_x, abs=1e-2)
    assert wp1["y_m"] == pytest.approx(reconstructed_y, abs=1e-2)
