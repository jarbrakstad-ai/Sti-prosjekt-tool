"""Areal-basert masseberegning for planering: finner den flateste/jevneste
plane flaten (helt flat, eller en jevn ønsket helningsgrad) som balanserer
skjæring (kutt) mot fylling over et helt kartutsnitt - til forskjell fra
routing.py sitt linje-baserte grøfteforslag og depressions.py sin søkk-
deteksjon.

Metode: minste kvadraters plantilpasning (z = a*x + b*y + c) gjennom DEM-ens
faktiske overflate. Denne planen har alltid null gjennomsnittlig avvik fra
terrenget (en egenskap ved minste kvadraters metode når skjæringspunktet c
er fritt), som betyr at total kuttet masse == total fylt masse for den
naturlige (ubegrensede) tilpasningen. For en spesifikk ønsket helningsgrad
beholdes den naturlige helningsretningen (den terrenget allerede "peker" mot
i gjennomsnitt), men helningens størrelse skaleres til ønsket verdi, og
skjæringspunktet beregnes på nytt for fortsatt å balansere kutt/fylling.

Dette er en forenklet overslagsberegning, ikke en byggeklar planeringsplan:
den kjenner ikke til jordart/bæreevne, tar ikke hensyn til hindringer
(bygninger, trær, stein) innenfor arealet, og forutsetter at all kuttet masse
kan gjenbrukes som fylling internt på stedet (ikke kjørt bort/inn)."""
from __future__ import annotations

import numpy as np
from pyproj import Transformer

from .dem import DemSampler

MAX_GRID_DIM = 150
"""Maks antall rader/kolonner i det returnerte kutt/fyll-gitteret (holder JSON-responsen liten)."""


def _local_xy_grid(dem: DemSampler) -> tuple[np.ndarray, np.ndarray]:
    """Lokale x/y-koordinater (meter) for hver celle i DEM-en, i samme
    lokale koordinatsystem som x_m/y_m i analysis.py sitt waypoints-felt og
    terrain_grid.py sitt høydegitter (meter fra DEM-ens øvre venstre hjørne)."""
    n_rows, n_cols = dem.shape()
    rows, cols = np.meshgrid(np.arange(n_rows), np.arange(n_cols), indexing="ij")
    xs, ys = dem.rowcol_to_xy(rows.ravel(), cols.ravel())
    local_x = (xs - dem.transform.c).reshape(n_rows, n_cols)
    local_y = (dem.transform.f - ys).reshape(n_rows, n_cols)
    return local_x, local_y


def compute_grading(dem: DemSampler, target_grade_pct: float | None = None) -> dict:
    """Beregner kutt/fylling for å oppnå en flat (target_grade_pct=0 eller
    None) eller jevnt hellende (target_grade_pct>0) overflate over hele
    DEM-området. Bruker DEM-ens utjevnede høydegitter (samme som gradient-
    beregningene i analysis.py/depressions.py) for å dempe DEM-målestøy."""
    array = dem.smoothed_array
    valid = ~np.isnan(array)
    if not valid.any():
        raise ValueError("Høydemodellen mangler gyldige høydeverdier.")

    local_x, local_y = _local_xy_grid(dem)
    x = local_x[valid]
    y = local_y[valid]
    z = array[valid]

    design = np.column_stack([x, y, np.ones_like(x)])
    coeffs, *_ = np.linalg.lstsq(design, z, rcond=None)
    a, b, c = (float(v) for v in coeffs)
    natural_grade_pct = 100.0 * float(np.hypot(a, b))

    if target_grade_pct is not None and target_grade_pct > 0:
        magnitude = float(np.hypot(a, b))
        if magnitude > 1e-9:
            scale = (target_grade_pct / 100.0) / magnitude
            a, b = a * scale, b * scale
        else:
            # Naturlig terreng er (nær) helt flatt allerede - ingen entydig
            # helningsretning å skalere opp. Faller tilbake til flatt (a=b=0).
            a, b = 0.0, 0.0
        c = float(np.mean(z - a * x - b * y))
    elif target_grade_pct is not None and target_grade_pct == 0:
        a, b = 0.0, 0.0
        c = float(np.mean(z))

    target_full = a * local_x + b * local_y + c
    diff = np.where(valid, array - target_full, 0.0)  # >0 = kutt, <0 = fylling

    dx, dy = dem.pixel_size()
    cell_area_m2 = abs(dx) * abs(dy)
    cut_m3 = float(np.sum(diff[diff > 0]) * cell_area_m2)
    fill_m3 = float(np.sum(-diff[diff < 0]) * cell_area_m2)
    total_area_m2 = float(valid.sum()) * cell_area_m2

    return {
        "plane": {"a": a, "b": b, "c": c},
        "natural_grade_pct": round(natural_grade_pct, 2),
        "applied_grade_pct": round(100.0 * float(np.hypot(a, b)), 2),
        "cut_m3": round(cut_m3, 1),
        "fill_m3": round(fill_m3, 1),
        "total_area_m2": round(total_area_m2, 1),
        "diff_grid": diff,
        "valid_grid": valid,
    }


def grading_to_response(dem: DemSampler, result: dict, max_dim: int = MAX_GRID_DIM) -> dict:
    """Bygger API-responsen, inkludert et nedskalert kutt/fyll-gitter for
    visualisering i frontend (samme nedskaleringsmønster som terrain_grid.py)."""
    n_rows, n_cols = dem.shape()
    row_stride = max(1, int(np.ceil(n_rows / max_dim)))
    col_stride = max(1, int(np.ceil(n_cols / max_dim)))

    diff = result["diff_grid"][::row_stride, ::col_stride]
    valid = result["valid_grid"][::row_stride, ::col_stride]
    diff = np.where(valid, diff, 0.0)

    origin_x, origin_y = dem.rowcol_to_xy(np.array([0]), np.array([0]))
    origin_x_m = float(origin_x[0]) - dem.transform.c
    origin_y_m = dem.transform.f - float(origin_y[0])

    dx, dy = dem.pixel_size()
    cell_size_x = abs(dx) * col_stride
    cell_size_y = abs(dy) * row_stride

    # Faktisk lat/lon pr. celle (ikke bare lokale meter) - nødvendig for å
    # tegne gitteret direkte på et Leaflet-kart i frontend. Samme
    # nedskalerte oppløsning som selve kutt/fyll-gitteret (maks 150x150,
    # samme størrelsesorden som terrain_grid.py sitt høydegitter).
    out_rows, out_cols = diff.shape
    rows_idx = np.arange(out_rows) * row_stride
    cols_idx = np.arange(out_cols) * col_stride
    rr, cc = np.meshgrid(rows_idx, cols_idx, indexing="ij")
    xs, ys = dem.rowcol_to_xy(rr.ravel(), cc.ravel())
    to_wgs84 = Transformer.from_crs(dem.crs, "EPSG:4326", always_xy=True)
    lons, lats = to_wgs84.transform(xs, ys)
    lats = lats.reshape(out_rows, out_cols)
    lons = lons.reshape(out_rows, out_cols)

    return {
        "natural_grade_pct": result["natural_grade_pct"],
        "applied_grade_pct": result["applied_grade_pct"],
        "cut_m3": result["cut_m3"],
        "fill_m3": result["fill_m3"],
        "total_area_m2": result["total_area_m2"],
        "grid": {
            "rows": int(diff.shape[0]),
            "cols": int(diff.shape[1]),
            "cell_size_x_m": round(float(cell_size_x), 3),
            "cell_size_y_m": round(float(cell_size_y), 3),
            "origin_x_m": round(origin_x_m, 2),
            "origin_y_m": round(origin_y_m, 2),
            "cut_fill_m": np.round(diff, 2).tolist(),
            "lats": np.round(lats, 6).tolist(),
            "lons": np.round(lons, 6).tolist(),
        },
    }
