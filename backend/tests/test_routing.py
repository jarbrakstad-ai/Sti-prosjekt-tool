"""Tester for trasé-forslag (A*-søk over DEM etter beste praksis)."""
from __future__ import annotations

import numpy as np
import pytest
from affine import Affine
from pyproj import Transformer

from app.dem import DemSampler
from app.routing import RouteOptions, RoutingError, suggest_route

UTM = "EPSG:32633"
to_wgs84 = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True)


def latlon_for_rowcol(dem: DemSampler, row: int, col: int) -> tuple[float, float]:
    x, y = dem.rowcol_to_xy(row, col)
    lon, lat = to_wgs84.transform(x, y)
    return float(lat), float(lon)


def make_flat_dem(size: int = 40, cell: float = 5.0) -> DemSampler:
    array = np.full((size, size), 1000.0)
    transform = Affine(cell, 0, 500000, 0, -cell, 6600000)
    return DemSampler(array=array, transform=transform, crs=UTM)


def make_walled_dem(size: int = 40, cell: float = 5.0) -> DemSampler:
    array = np.full((size, size), 1000.0)
    wall_cols = range(18, 22)
    gap_rows = range(27, 33)
    for c in wall_cols:
        array[:, c] = 1040.0
        for r in gap_rows:
            array[r, c] = 1000.0
    transform = Affine(cell, 0, 500000, 0, -cell, 6600000)
    return DemSampler(array=array, transform=transform, crs=UTM)


def test_flat_dem_route_is_direct_and_clean():
    dem = make_flat_dem()
    start = latlon_for_rowcol(dem, 5, 5)
    end = latlon_for_rowcol(dem, 5, 30)

    result = suggest_route(dem, start, end, RouteOptions())

    assert result["analysis"]["summary"]["max_grade_pct"] < 1.0
    assert len(result["points"]) >= 2


def test_route_detours_around_steep_wall_instead_of_crossing_it():
    dem = make_walled_dem()
    start = latlon_for_rowcol(dem, 2, 2)
    end = latlon_for_rowcol(dem, 2, 37)

    result = suggest_route(dem, start, end, RouteOptions())

    to_dem = Transformer.from_crs("EPSG:4326", UTM, always_xy=True)
    wall_crossings = []
    for lat, lon in result["points"]:
        x, y = to_dem.transform(lon, lat)
        row, col = dem.xy_to_nearest_rowcol(x, y)
        if 18 <= col <= 21:
            wall_crossings.append(row)

    assert wall_crossings, "forventet at ruten faktisk krysser vegg-kolonnene"
    assert all(26 <= r <= 34 for r in wall_crossings), (
        f"ruten burde krysse gjennom åpningen (rad ~27-32), fant {wall_crossings}"
    )
    assert result["analysis"]["summary"]["max_grade_pct"] < 20.0


def test_raises_when_grid_too_large():
    dem = make_flat_dem(size=50)
    start = latlon_for_rowcol(dem, 5, 5)
    end = latlon_for_rowcol(dem, 5, 30)
    with pytest.raises(RoutingError):
        suggest_route(dem, start, end, RouteOptions(max_grid_nodes=100))


def test_raises_when_start_and_end_same_cell():
    dem = make_flat_dem()
    start = latlon_for_rowcol(dem, 5, 5)
    with pytest.raises(RoutingError):
        suggest_route(dem, start, start, RouteOptions())
