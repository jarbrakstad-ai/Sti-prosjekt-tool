"""Finner søkk/forsenkninger i en DEM: celler der vann vil bli stående fordi
det ikke finnes noen sammenhengende nedadgående vei ut til kanten av
DEM-området - relevant for å vurdere om et jorde er "selvdrenerende" (drenerer
av seg selv pga. terrengets fall) eller trenger tiltak (grøft/planering) et
sted.

Bruker "priority-flood"-algoritmen (Barnes, Lehman & Mulla 2014, mye brukt i
GIS-hydrologi, f.eks. WhiteboxTools/RichDEM sin "Fill Depressions"): flommer
terrenget innover fra kanten av DEM-en med en min-heap, og registrerer for
hver celle hvor mye den måtte "fylles" opp før den fikk en sammenhengende
nedadgående (eller flat) vei til kanten. Dette er en heuristisk indikasjon
basert kun på høydedata - ikke en fasit (den kjenner ikke til jordart/
infiltrasjonsevne, som også avgjør om et areal faktisk er selvdrenerende)."""
from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np
from pyproj import Transformer

from .dem import DemSampler

_NEIGHBORS_8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _fill_depressions(array: np.ndarray) -> np.ndarray:
    """Returnerer et "fylt" høydegitter der hver celle er hevet til minimum
    høyde den måtte nå for å ha en nedadgående/flat vei til kanten av
    gitteret. Differansen (filled - array) er søkk-dybden i hver celle."""
    n_rows, n_cols = array.shape
    filled = np.where(np.isnan(array), np.inf, array).astype(float)
    visited = np.zeros((n_rows, n_cols), dtype=bool)
    heap: list[tuple[float, int, int]] = []

    def push_if_valid(r: int, c: int) -> None:
        if visited[r, c] or np.isnan(array[r, c]):
            return
        visited[r, c] = True
        heapq.heappush(heap, (float(array[r, c]), r, c))

    for c in range(n_cols):
        push_if_valid(0, c)
        push_if_valid(n_rows - 1, c)
    for r in range(n_rows):
        push_if_valid(r, 0)
        push_if_valid(r, n_cols - 1)

    while heap:
        elev, r, c = heapq.heappop(heap)
        for dr, dc in _NEIGHBORS_8:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < n_rows and 0 <= nc < n_cols) or visited[nr, nc]:
                continue
            if np.isnan(array[nr, nc]):
                continue
            visited[nr, nc] = True
            filled[nr, nc] = max(float(array[nr, nc]), elev)
            heapq.heappush(heap, (filled[nr, nc], nr, nc))

    return filled


def _label_regions(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Enkel 8-sammenhengende connected-component-merking (flood fill) uten
    scipy-avhengighet. Returnerer et etikett-gitter (0 = ikke i mask) og
    antall regioner."""
    n_rows, n_cols = mask.shape
    labels = np.zeros((n_rows, n_cols), dtype=int)
    next_label = 0

    for start_r in range(n_rows):
        for start_c in range(n_cols):
            if not mask[start_r, start_c] or labels[start_r, start_c] != 0:
                continue
            next_label += 1
            stack = [(start_r, start_c)]
            labels[start_r, start_c] = next_label
            while stack:
                r, c = stack.pop()
                for dr, dc in _NEIGHBORS_8:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < n_rows and 0 <= nc < n_cols and mask[nr, nc] and labels[nr, nc] == 0:
                        labels[nr, nc] = next_label
                        stack.append((nr, nc))

    return labels, next_label


@dataclass
class Depression:
    cell_count: int
    area_m2: float
    max_depth_m: float
    volume_m3: float
    centroid_rc: tuple[float, float]


def find_depressions(dem: DemSampler, min_depth_m: float = 0.03) -> list[Depression]:
    """Finner søkk i DEM-en dypere enn `min_depth_m`. Bruker DemSampler sitt
    utjevnede høydegitter (samme som gradient/helnings-beregningene i
    analysis.py bruker), IKKE rådata - ren punktvis DEM-målestøy (noen cm/
    piksel på en høyoppløst DEM, se DemSampler.grade_smoothing_radius_m)
    ville ellers gitt hundrevis av falske mikro-søkk på reelt jevnt terreng
    (verifisert empirisk: en 200x200 DEM med realistisk 5 cm støy ga 729
    falske søkk på rådata mot et fåtall på utjevnet data). Returnerer én
    Depression per sammenhengende forsenkning, sortert etter største areal
    først."""
    array = dem.smoothed_array
    filled = _fill_depressions(array)
    depth = filled - array
    depth = np.where(np.isnan(array), 0.0, depth)

    mask = depth > min_depth_m
    if not mask.any():
        return []

    labels, n_regions = _label_regions(mask)

    dx, dy = dem.pixel_size()
    cell_area_m2 = abs(dx) * abs(dy)

    depressions: list[Depression] = []
    for label_id in range(1, n_regions + 1):
        region_mask = labels == label_id
        cell_count = int(region_mask.sum())
        rows, cols = np.nonzero(region_mask)
        max_depth = float(depth[region_mask].max())
        volume = float(depth[region_mask].sum() * cell_area_m2)
        centroid_rc = (float(rows.mean()), float(cols.mean()))
        depressions.append(
            Depression(
                cell_count=cell_count,
                area_m2=cell_count * cell_area_m2,
                max_depth_m=max_depth,
                volume_m3=volume,
                centroid_rc=centroid_rc,
            )
        )

    depressions.sort(key=lambda d: d.area_m2, reverse=True)
    return depressions


def depressions_to_response(dem: DemSampler, depressions: list[Depression]) -> dict:
    n_rows, n_cols = dem.shape()
    dx, dy = dem.pixel_size()
    total_area_m2 = n_rows * n_cols * abs(dx) * abs(dy)
    depression_area_m2 = sum(d.area_m2 for d in depressions)

    to_wgs84 = Transformer.from_crs(dem.crs, "EPSG:4326", always_xy=True)

    items = []
    for d in depressions:
        x, y = dem.rowcol_to_xy(d.centroid_rc[0], d.centroid_rc[1])
        lon, lat = to_wgs84.transform(float(x), float(y))
        items.append(
            {
                "cell_count": d.cell_count,
                "area_m2": round(d.area_m2, 1),
                "max_depth_m": round(d.max_depth_m, 3),
                "volume_m3": round(d.volume_m3, 2),
                "lat": round(float(lat), 6),
                "lon": round(float(lon), 6),
                "centroid_x_m": round(float(x) - dem.transform.c, 2),
                "centroid_y_m": round(dem.transform.f - float(y), 2),
            }
        )

    return {
        "grid_shape": [n_rows, n_cols],
        "total_area_m2": round(total_area_m2, 1),
        "depression_area_m2": round(depression_area_m2, 1),
        "depression_area_fraction_pct": round(100.0 * depression_area_m2 / total_area_m2, 2) if total_area_m2 > 0 else 0.0,
        "depressions": items,
    }
