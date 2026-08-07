"""Tester for trasé-forslag (A*-søk over DEM etter beste praksis)."""
from __future__ import annotations

import numpy as np
import pytest
from affine import Affine
from pyproj import Transformer
from shapely.geometry import LineString

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

    result = suggest_route(dem, [start, end], RouteOptions())

    assert result["analysis"]["summary"]["max_grade_pct"] < 1.0
    assert len(result["points"]) >= 2
    assert result["search_stats"]["smoothed"] is True
    assert result["search_stats"]["final_points"] > result["search_stats"]["raw_path_nodes"]


def test_route_detours_around_steep_wall_instead_of_crossing_it():
    dem = make_walled_dem()
    start = latlon_for_rowcol(dem, 2, 2)
    end = latlon_for_rowcol(dem, 2, 37)

    result = suggest_route(dem, [start, end], RouteOptions())

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
    # Glatting her ville kuttet hjørner inn i veggen (ren geometri, kjenner
    # ikke til terrenget) -- forvent at sikkerhetsfallback til ujevnet rute slår inn.
    assert result["search_stats"]["smoothed"] is False


def test_raises_when_grid_too_large():
    dem = make_flat_dem(size=50)
    start = latlon_for_rowcol(dem, 5, 5)
    end = latlon_for_rowcol(dem, 5, 30)
    with pytest.raises(RoutingError):
        suggest_route(dem, [start, end], RouteOptions(max_grid_nodes=100))


def test_raises_when_start_and_end_same_cell():
    dem = make_flat_dem()
    start = latlon_for_rowcol(dem, 5, 5)
    with pytest.raises(RoutingError):
        suggest_route(dem, [start, start], RouteOptions())


def test_raises_when_start_point_outside_dem_instead_of_silently_clamping():
    """Regresjonstest: et punkt utenfor DEM-dekningen skal gi tydelig feil,
    ikke stille "klemmes" til nærmeste kant (som ga en trasé som startet et
    annet sted enn brukeren faktisk klikket)."""
    dem = make_flat_dem(size=40, cell=5.0)  # dekker 200x200 m
    far_outside_x, far_outside_y = dem.rowcol_to_xy(-50, -50)
    lon, lat = to_wgs84.transform(far_outside_x, far_outside_y)
    start = (float(lat), float(lon))
    end = latlon_for_rowcol(dem, 20, 20)

    with pytest.raises(RoutingError, match="utenfor DEM-området"):
        suggest_route(dem, [start, end], RouteOptions())


def test_raises_when_end_point_outside_dem():
    dem = make_flat_dem(size=40, cell=5.0)
    start = latlon_for_rowcol(dem, 5, 5)
    far_outside_x, far_outside_y = dem.rowcol_to_xy(500, 500)
    lon, lat = to_wgs84.transform(far_outside_x, far_outside_y)
    end = (float(lat), float(lon))

    with pytest.raises(RoutingError, match="utenfor DEM-området"):
        suggest_route(dem, [start, end], RouteOptions())


def test_route_passes_through_via_point_and_smoothing_does_not_move_it():
    """Mellompunkt (f.eks. for å styre unna en grunneiers areal) skal alltid
    ligge på ruten, uendret av glattingen som ellers kutter hjørner."""
    dem = make_flat_dem()
    start = latlon_for_rowcol(dem, 5, 5)
    via = latlon_for_rowcol(dem, 30, 10)
    end = latlon_for_rowcol(dem, 5, 30)

    result = suggest_route(dem, [start, via, end], RouteOptions())

    assert result["search_stats"]["num_legs"] == 2

    to_dem = Transformer.from_crs("EPSG:4326", UTM, always_xy=True)
    via_x, via_y = to_dem.transform(via[1], via[0])
    via_row, via_col = dem.xy_to_nearest_rowcol(via_x, via_y)

    hit = False
    for lat, lon in result["points"]:
        x, y = to_dem.transform(lon, lat)
        row, col = dem.xy_to_nearest_rowcol(x, y)
        if row == via_row and col == via_col:
            hit = True
            break

    assert hit, "forventet at ruten faktisk går gjennom mellompunktet"


def make_hilly_dem(size: int = 100, cell: float = 5.0) -> DemSampler:
    """DEM med en stor kolle midt i gitteret pluss to mindre kuler -
    terreng som tvinger søket til å manøvrere rundt hindringer i flere
    retninger (relevant for å teste selv-kryssende ruter)."""
    yy, xx = np.mgrid[0:size, 0:size]
    cx, cy = size * 0.5, size * 0.5
    hill = 60 * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (size * 0.18) ** 2)))
    bump1 = 25 * np.exp(-(((xx - size * 0.25) ** 2 + (yy - size * 0.7) ** 2) / (2 * (size * 0.1) ** 2)))
    bump2 = 25 * np.exp(-(((xx - size * 0.75) ** 2 + (yy - size * 0.3) ** 2) / (2 * (size * 0.1) ** 2)))
    array = 1000.0 + hill + bump1 + bump2
    transform = Affine(cell, 0, 500000, 0, -cell, 6600000)
    return DemSampler(array=array, transform=transform, crs=UTM)


def test_route_around_hilly_terrain_does_not_self_intersect():
    """Regresjonstest: A*-søket besøker aldri samme rutenett-celle to ganger,
    men den geometriske linjen kunne likevel krysse/gå innom seg selv - f.eks.
    når det er billigere å sveipe rundt en kolle enn å justere kursen
    underveis, eller når en tilstand med retning gjorde at samme celle dukket
    opp to ganger i den rekonstruerte stien (nådd via to ulike retninger).
    Se _remove_self_intersections og _dedupe_position_revisits."""
    dem = make_hilly_dem()
    start = latlon_for_rowcol(dem, 15, 15)
    via = latlon_for_rowcol(dem, 50, 48)
    end = latlon_for_rowcol(dem, 85, 85)

    result = suggest_route(dem, [start, via, end], RouteOptions())

    line = LineString([(lo, la) for la, lo in result["points"]])
    assert line.is_simple, "ruten krysser/overlapper seg selv geometrisk"
    assert result["search_stats"]["self_intersects"] is False


def make_tilted_plane_dem(size: int = 40, cell: float = 5.0) -> DemSampler:
    """DEM som heller jevnt nedover mot siste rad - laveste celle er
    entydig (rad, kolonne) = (size - 1, 0), siden np.nanargmin plukker
    første forekomst i rekkefølge ved uavgjort."""
    rows = np.arange(size)[:, None]
    array = np.tile(1000.0 - 0.5 * rows, (1, size)).astype(float)
    transform = Affine(cell, 0, 500000, 0, -cell, 6600000)
    return DemSampler(array=array, transform=transform, crs=UTM)


def test_single_waypoint_auto_suggests_lowest_point_as_endpoint():
    """Når bare startpunkt oppgis, skal ruten automatisk søke mot det
    laveste punktet i DEM-en (fysisk fornuftig utløps-gjetning), og
    search_stats skal markere at dette skjedde."""
    dem = make_tilted_plane_dem()
    start = latlon_for_rowcol(dem, 5, 20)

    result = suggest_route(dem, [start], RouteOptions())

    assert result["search_stats"]["auto_endpoint"] is True
    assert result["search_stats"]["num_legs"] == 1

    to_dem = Transformer.from_crs("EPSG:4326", UTM, always_xy=True)
    last_lat, last_lon = result["points"][-1]
    x, y = to_dem.transform(last_lon, last_lat)
    row, col = dem.xy_to_nearest_rowcol(x, y)
    assert (row, col) == (39, 0)


def test_multi_waypoint_route_reports_auto_endpoint_false():
    dem = make_flat_dem()
    start = latlon_for_rowcol(dem, 5, 5)
    end = latlon_for_rowcol(dem, 5, 30)

    result = suggest_route(dem, [start, end], RouteOptions())

    assert result["search_stats"]["auto_endpoint"] is False


def test_raises_when_start_point_is_already_lowest_point():
    dem = make_tilted_plane_dem()
    start = latlon_for_rowcol(dem, 39, 0)

    with pytest.raises(RoutingError, match="allerede det laveste punktet"):
        suggest_route(dem, [start], RouteOptions())


def test_raises_when_no_waypoints_given():
    dem = make_flat_dem()
    with pytest.raises(RoutingError, match="minst et startpunkt"):
        suggest_route(dem, [], RouteOptions())
