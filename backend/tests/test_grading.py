"""Tester for areal-basert masseberegning (planering: flatt eller jevn helning)."""
from __future__ import annotations

import numpy as np
import pytest
from affine import Affine

from app.dem import DemSampler
from app.grading import compute_grading, grading_to_response

UTM = "EPSG:32633"


def make_dem(array: np.ndarray, cell: float = 5.0) -> DemSampler:
    transform = Affine(cell, 0, 500000, 0, -cell, 6600000)
    return DemSampler(array=array.astype(float), transform=transform, crs=UTM)


def make_flat_dem(size: int = 40, cell: float = 5.0) -> DemSampler:
    return make_dem(np.full((size, size), 1000.0), cell)


def make_tilted_plane_dem(size: int = 40, cell: float = 5.0, grade_pct: float = 6.0) -> DemSampler:
    """Jevn helning sørover (langs rad-aksen) med kjent stigningsgrad."""
    k = (grade_pct / 100.0) * cell  # høydeendring pr. rad-steg
    rows = np.arange(size)[:, None]
    array = np.tile(1000.0 - k * rows, (1, size))
    return make_dem(array, cell)


def test_flat_dem_has_zero_natural_grade_and_no_cut_fill():
    dem = make_flat_dem()
    result = compute_grading(dem)
    assert result["natural_grade_pct"] == pytest.approx(0.0, abs=1e-6)
    assert result["cut_m3"] == pytest.approx(0.0, abs=1e-6)
    assert result["fill_m3"] == pytest.approx(0.0, abs=1e-6)


def test_perfect_plane_fits_exactly_no_cut_fill_needed():
    dem = make_tilted_plane_dem(grade_pct=6.0)
    result = compute_grading(dem)
    assert result["natural_grade_pct"] == pytest.approx(6.0, abs=0.05)
    # En perfekt plan flate krever ingen utjevning for å bli en (annen) plan flate
    assert result["cut_m3"] == pytest.approx(0.0, abs=0.5)
    assert result["fill_m3"] == pytest.approx(0.0, abs=0.5)


def test_cut_always_balances_fill_by_construction():
    """Kjerneegenskapen ved minste kvadraters plantilpasning med fritt
    skjæringspunkt: gjennomsnittlig avvik er null, så kuttet volum skal
    balansere eksakt mot fylt volum - både for naturlig tilpasning og for en
    påtvunget helningsgrad (flatt eller en spesifikk %)."""
    array = np.full((40, 40), 1000.0)
    array[10:16, 10:16] += 0.8  # kolle
    array[25:30, 5:10] -= 0.4  # forsenkning
    dem = make_dem(array)

    for target in (None, 0.0, 2.5):
        result = compute_grading(dem, target_grade_pct=target)
        assert result["cut_m3"] == pytest.approx(result["fill_m3"], abs=1e-6), (
            f"cut/fill ubalansert for target_grade_pct={target}"
        )


def test_bumpy_terrain_flagged_for_cut_when_target_is_flat():
    array = np.full((40, 40), 1000.0)
    array[10:16, 10:16] += 0.8  # kolle - skal kuttes ved flat målflate
    dem = make_dem(array)

    result = compute_grading(dem, target_grade_pct=0.0)
    assert result["applied_grade_pct"] == pytest.approx(0.0, abs=1e-6)
    assert result["cut_m3"] > 0
    assert result["fill_m3"] > 0  # resten av det flate arealet må fylles litt for å balansere


def test_target_grade_scales_magnitude_but_keeps_natural_direction():
    dem = make_tilted_plane_dem(grade_pct=4.0)
    result_natural = compute_grading(dem)
    result_half = compute_grading(dem, target_grade_pct=2.0)

    assert result_half["applied_grade_pct"] == pytest.approx(2.0, abs=0.05)
    # Samme retning (a, b) skalert - forholdet a/b skal være likt (innenfor toleranse)
    a1, b1 = result_natural["plane"]["a"], result_natural["plane"]["b"]
    a2, b2 = result_half["plane"]["a"], result_half["plane"]["b"]
    if abs(b1) > 1e-9:
        assert (a2 / b2) == pytest.approx(a1 / b1, rel=1e-3)


def test_grading_to_response_shape():
    array = np.full((40, 40), 1000.0)
    array[10:16, 10:16] += 0.8
    dem = make_dem(array)

    result = compute_grading(dem, target_grade_pct=0.0)
    response = grading_to_response(dem, result)

    assert response["cut_m3"] > 0
    assert response["fill_m3"] > 0
    assert response["grid"]["rows"] == 40
    assert response["grid"]["cols"] == 40
    assert len(response["grid"]["cut_fill_m"]) == 40
    assert len(response["grid"]["cut_fill_m"][0]) == 40
    assert len(response["grid"]["lats"]) == 40 and len(response["grid"]["lons"]) == 40
    assert -90 <= response["grid"]["lats"][0][0] <= 90
    assert -180 <= response["grid"]["lons"][0][0] <= 180
    # Kolle-cellene skal ha positiv kutt-verdi i gitteret
    assert response["grid"]["cut_fill_m"][12][12] > 0
