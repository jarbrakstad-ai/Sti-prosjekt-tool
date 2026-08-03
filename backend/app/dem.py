"""Lesing og sampling av høydemodell (DEM): høyde og terrenggradient i punkter.

DEM må være i et projisert, nord-orientert CRS i meter (f.eks. UTM). Dette
holder finite-difference-gradienten enkel: y øker nordover, x øker østover,
og pikselstørrelse er konstant i meter.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from affine import Affine


class DemError(ValueError):
    pass


def _box_blur(array: np.ndarray, radius_px: int) -> np.ndarray:
    """Nabolagsgjennomsnitt (separabel boks-smoothing), NaN-trygg.

    Reelle høydemodeller (spesielt 1 m LiDAR-avledede DTM-er) har typisk noen
    cm vertikal støy pr. piksel. Rådata-gradienten (np.gradient/finite-difference
    på nabopiksler) forsterker denne støyen kraftig - et par cm feil over 1 m
    kan gi flere prosentpoeng falsk helning. Denne funksjonen bygger et
    utjevnet gitter (over ~radius_px piksler, altså en avstand relevant for
    stibygging, ikke pikselnivå) som brukes til gradient/helnings-baserte
    vurderinger, slik at analysen reflekterer terrengets faktiske trend i
    stedet for målestøy."""
    if radius_px <= 0:
        return array.copy()

    valid = ~np.isnan(array)
    fill_value = float(np.nanmedian(array)) if valid.any() else 0.0
    filled = np.where(valid, array, fill_value)

    kernel = np.ones(2 * radius_px + 1) / (2 * radius_px + 1)

    def blur_axis(a: np.ndarray, axis: int) -> np.ndarray:
        padded = np.pad(a, [(radius_px, radius_px) if ax == axis else (0, 0) for ax in range(a.ndim)], mode="edge")
        return np.apply_along_axis(lambda v: np.convolve(v, kernel, mode="valid"), axis, padded)

    blurred = blur_axis(blur_axis(filled, axis=1), axis=0)
    return np.where(valid, blurred, np.nan)


@dataclass
class DemSampler:
    array: np.ndarray  # shape (rows, cols), float, NaN der data mangler
    transform: Affine
    crs: object  # rasterio CRS eller pyproj CRS-kompatibel
    grade_smoothing_radius_m: float = 2.0
    """Utjevningsradius (meter) brukt for gradient/helnings-baserte vurderinger
    (cross-slope, fall-line, langsgående helning) - dempet mot DEM-målestøy.
    Selve høydeverdiene (elevation_m per punkt) forblir rå/upåvirket. Bare
    virksom når pikselstørrelsen er finere enn radiusen (grov-oppløste DEM-er,
    f.eks. 5-10 m/piksel, er allerede et romlig snitt og trenger ikke dette) -
    ellers ville avrunding oppover til minimum 1 piksel smurt ut ekte
    stibygging-relevante trekk (t.d. drenerende motfall hvert 15-50 m)."""

    def __post_init__(self) -> None:
        if self.transform.b != 0 or self.transform.d != 0:
            raise DemError(
                "DEM må være nord-orientert (ingen rotasjon/skjevhet i transformen)."
            )
        dx, dy = self.pixel_size()
        pixel_m = (abs(dx) + abs(dy)) / 2.0
        radius_px = int(self.grade_smoothing_radius_m // pixel_m) if pixel_m > 0 else 0
        self.smoothed_array = _box_blur(self.array, radius_px)
        self.dzdx_grid = np.gradient(self.smoothed_array, axis=1) / dx
        self.dzdy_grid = np.gradient(self.smoothed_array, axis=0) / dy

    @classmethod
    def from_geotiff_bytes(cls, content: bytes) -> "DemSampler":
        import rasterio
        from rasterio.io import MemoryFile

        try:
            with MemoryFile(content) as memfile, memfile.open() as ds:
                if ds.crs is None:
                    raise DemError("DEM-filen mangler CRS (koordinatreferansesystem).")
                if ds.crs.is_geographic:
                    raise DemError(
                        "DEM er i geografisk CRS (grader). Last opp en DEM i et "
                        "projisert CRS i meter, f.eks. UTM."
                    )
                array = ds.read(1, masked=True).astype("float64")
                array = np.ma.filled(array, np.nan)
                return cls(array=array, transform=ds.transform, crs=ds.crs)
        except rasterio.errors.RasterioIOError as exc:
            raise DemError(f"Klarte ikke å lese DEM-fil: {exc}") from exc

    def pixel_size(self) -> tuple[float, float]:
        """Returnerer (dx, dy) i meter per piksel; dy er negativ (nord-orientert)."""
        return self.transform.a, self.transform.e

    def _fractional_rowcol(self, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        inv = ~self.transform
        cols, rows = inv * (xs, ys)
        # transform kartlegger pikselhjørne -> senter-baserte indekser for interpolasjon
        return np.asarray(rows) - 0.5, np.asarray(cols) - 0.5

    def _bilinear(self, grid: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        rows, cols = self._fractional_rowcol(xs, ys)
        n_rows, n_cols = grid.shape

        rows = np.clip(rows, 0, n_rows - 1.0001)
        cols = np.clip(cols, 0, n_cols - 1.0001)

        r0 = np.floor(rows).astype(int)
        c0 = np.floor(cols).astype(int)
        r1 = r0 + 1
        c1 = c0 + 1
        fr = rows - r0
        fc = cols - c0

        v00 = grid[r0, c0]
        v01 = grid[r0, c1]
        v10 = grid[r1, c0]
        v11 = grid[r1, c1]

        top = v00 * (1 - fc) + v01 * fc
        bottom = v10 * (1 - fc) + v11 * fc
        return top * (1 - fr) + bottom * fr

    def sample_elevation(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        return self._bilinear(self.array, xs, ys)

    def sample_elevation_smoothed(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Som sample_elevation, men fra det utjevnede gitteret (se
        grade_smoothing_radius_m) - brukes til langsgående helning/stigning
        for å unngå at DEM-målestøy gir falske stibygging-brudd."""
        return self._bilinear(self.smoothed_array, xs, ys)

    def sample_gradient(self, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Returnerer (dz/dx, dz/dy) i meter høyde per meter, i punktene (xs, ys)."""
        dzdx = self._bilinear(self.dzdx_grid, xs, ys)
        dzdy = self._bilinear(self.dzdy_grid, xs, ys)
        return dzdx, dzdy

    def shape(self) -> tuple[int, int]:
        return self.array.shape

    def rowcol_to_xy(self, row: np.ndarray, col: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Pikselsenter-koordinater (x, y) for gitt (row, col)."""
        x = self.transform.c + self.transform.a * (np.asarray(col) + 0.5)
        y = self.transform.f + self.transform.e * (np.asarray(row) + 0.5)
        return x, y

    def contains_xy(self, x: float, y: float) -> bool:
        """Om punktet (x, y) faktisk ligger innenfor DEM-ens dekningsområde."""
        inv = ~self.transform
        col, row = inv * (x, y)
        n_rows, n_cols = self.shape()
        return 0 <= col <= n_cols and 0 <= row <= n_rows

    def xy_to_nearest_rowcol(self, x: float, y: float) -> tuple[int, int]:
        if not self.contains_xy(x, y):
            raise DemError(
                "Punktet ligger utenfor høydemodellens dekningsområde. Velg et punkt "
                "innenfor DEM-området (evt. hent/last opp høydedata på nytt for riktig område)."
            )
        rows, cols = self._fractional_rowcol(np.array([x]), np.array([y]))
        n_rows, n_cols = self.shape()
        row = int(np.clip(round(float(rows[0])), 0, n_rows - 1))
        col = int(np.clip(round(float(cols[0])), 0, n_cols - 1))
        return row, col
