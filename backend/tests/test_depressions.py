"""Tester for søkk-/forsenkningsdeteksjon ("selvdrenerende mark"-sjekk)."""
from __future__ import annotations

import numpy as np
import pytest
from affine import Affine

from app.dem import DemSampler
from app.depressions import depressions_to_response, find_depressions

UTM = "EPSG:32633"


def make_dem(array: np.ndarray, cell: float = 5.0) -> DemSampler:
    """Bygger en DemSampler direkte fra et ferdig høydegitter. NB: dem.array
    må IKKE muteres etter konstruksjon i disse testene - DemSampler beregner
    dem.smoothed_array (som find_depressions bruker) kun én gang i
    __post_init__, så senere endringer på dem.array ville ikke reflekteres."""
    transform = Affine(cell, 0, 500000, 0, -cell, 6600000)
    return DemSampler(array=array.astype(float), transform=transform, crs=UTM)


def make_tilted_plane_dem(size: int = 40, cell: float = 5.0) -> DemSampler:
    rows = np.arange(size)[:, None]
    array = np.tile(1000.0 - 0.1 * rows, (1, size))
    return make_dem(array, cell)


def make_flat_dem(size: int = 40, cell: float = 5.0) -> DemSampler:
    array = np.full((size, size), 1000.0)
    return make_dem(array, cell)


def test_perfectly_sloped_plane_has_no_depressions():
    dem = make_tilted_plane_dem()
    depressions = find_depressions(dem)
    assert depressions == []


def test_detects_an_engineered_pit_not_touching_the_boundary():
    # Flatt underlag (ikke hellende) gir en entydig, jevn "skål" - på et
    # hellende underlag ville deler av et likt nedsenket parti smelte sammen
    # med den naturlige nedstrøms-hellingen og ikke telle som eget søkk
    # (riktig oppførsel, se test_min_depth_threshold_filters_shallow_noise
    # for et eksempel der akkurat dette utnyttes bevisst).
    array = np.full((40, 40), 1000.0)
    # Grav et 6x6-punkt basseng midt i gitteret, 0.5 m under det flate nivået -
    # ingen sammenhengende nedadgående vei ut derfra uten å "fylles" opp igjen.
    array[15:21, 15:21] -= 0.5
    dem = make_dem(array)

    depressions = find_depressions(dem)

    assert len(depressions) == 1
    d = depressions[0]
    assert d.cell_count == 36
    assert d.max_depth_m == pytest.approx(0.5)
    expected_area = 36 * 5.0 * 5.0
    assert d.area_m2 == pytest.approx(expected_area)
    expected_volume = 0.5 * expected_area
    assert d.volume_m3 == pytest.approx(expected_volume)


def test_depression_touching_dem_boundary_is_not_flagged():
    """En forsenkning som når helt til kanten av DEM-en har (i denne
    heuristikken) en fri utløpsvei ut av det kartlagte området, og skal
    derfor ikke telles som et lukket søkk."""
    rows = np.arange(40)[:, None]
    array = np.tile(1000.0 - 0.1 * rows, (1, 40))
    array[0:6, 0:6] -= 0.5  # berører hjørnet/kanten av gitteret
    dem = make_dem(array)

    depressions = find_depressions(dem)
    assert depressions == []


def test_min_depth_threshold_filters_shallow_noise():
    array = np.full((40, 40), 1000.0)
    array[15:18, 15:18] -= 0.01  # under standard-terskelen (0.03 m)
    dem = make_dem(array)

    depressions = find_depressions(dem)
    assert depressions == []

    depressions_low_threshold = find_depressions(dem, min_depth_m=0.005)
    assert len(depressions_low_threshold) == 1


def test_depressions_to_response_shape():
    array = np.full((40, 40), 1000.0)
    array[15:21, 15:21] -= 0.5
    array[25:29, 5:9] -= 0.3
    dem = make_dem(array)

    depressions = find_depressions(dem)
    response = depressions_to_response(dem, depressions)

    assert response["grid_shape"] == [40, 40]
    assert len(response["depressions"]) == 2
    # størst areal først
    assert response["depressions"][0]["area_m2"] >= response["depressions"][1]["area_m2"]
    assert response["depression_area_fraction_pct"] > 0
    assert response["total_area_m2"] == pytest.approx(40 * 40 * 5.0 * 5.0)
