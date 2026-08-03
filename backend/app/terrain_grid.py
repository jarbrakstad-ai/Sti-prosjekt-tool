"""Bygger et nedskalert høydegitter for 3D-visning av terrenget i frontend
(Three.js).

Gitteret bruker samme lokale koordinatsystem (meter fra DEM-ens
øvre venstre hjørne: `origin_x_m`/`origin_y_m` + rad/kolonne * cellestørrelse)
som trasépunktenes `x_m`/`y_m` i analyze_trail sitt "waypoints"-felt. Så
lenge terrenggitteret og trasépunktene kommer fra samme DEM-fil, vil de
alltid stemme overens geometrisk - selv om de hentes i separate API-kall.
"""
from __future__ import annotations

import numpy as np

from .dem import DemSampler

MAX_GRID_DIM = 150
"""Maks antall rader/kolonner i det nedskalerte gitteret (holder JSON-responsen liten)."""


def build_terrain_grid(dem: DemSampler, max_dim: int = MAX_GRID_DIM) -> dict:
    n_rows, n_cols = dem.shape()
    row_stride = max(1, int(np.ceil(n_rows / max_dim)))
    col_stride = max(1, int(np.ceil(n_cols / max_dim)))

    sub_array = dem.array[::row_stride, ::col_stride]
    if np.isnan(sub_array).any():
        fill_value = float(np.nanmedian(dem.array)) if not np.isnan(dem.array).all() else 0.0
        sub_array = np.nan_to_num(sub_array, nan=fill_value)

    origin_x, origin_y = dem.rowcol_to_xy(np.array([0]), np.array([0]))
    origin_x_m = float(origin_x[0]) - dem.transform.c
    origin_y_m = dem.transform.f - float(origin_y[0])

    dx, dy = dem.pixel_size()
    cell_size_x = abs(dx) * col_stride
    cell_size_y = abs(dy) * row_stride

    return {
        "rows": int(sub_array.shape[0]),
        "cols": int(sub_array.shape[1]),
        "cell_size_x_m": round(float(cell_size_x), 3),
        "cell_size_y_m": round(float(cell_size_y), 3),
        "origin_x_m": round(origin_x_m, 2),
        "origin_y_m": round(origin_y_m, 2),
        "elevations": np.round(sub_array, 1).tolist(),
    }
