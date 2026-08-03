"""Delt vektorgeometri for å vurdere en bevegelsesretning mot terrenghelningen.

Brukes både av analysen av en gitt trasé (analysis.py) og av
trasé-forslag-algoritmen (routing.py), slik at de to bruker samme definisjon
av sidehelling og fall-line-vinkel.
"""
from __future__ import annotations

import numpy as np

EPS = 1e-9


def segment_metrics(
    ux: np.ndarray,
    uy: np.ndarray,
    dzdx: np.ndarray,
    dzdy: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Gitt enhetsretning (ux, uy) langs et sti-segment og terrenggradienten
    (dzdx, dzdy) der, returner (cross_slope_pct, terrain_slope_pct, fall_line_angle_deg).

    cross_slope_pct: sidehelling (terreng på tvers av stien), i prosent.
    terrain_slope_pct: total terrenghelning i punktet, i prosent.
    fall_line_angle_deg: vinkel mellom stiretning og fallretning (0 = følger
        fallinjen direkte, 90 = følger høydekoten/konturen).
    """
    cross_component = -uy * dzdx + ux * dzdy
    cross_slope_pct = np.abs(cross_component) * 100.0

    terrain_slope_pct = np.hypot(dzdx, dzdy) * 100.0

    downhill_norm = np.hypot(dzdx, dzdy)
    with np.errstate(invalid="ignore", divide="ignore"):
        cos_angle = -(ux * dzdx + uy * dzdy) / np.where(downhill_norm < EPS, np.nan, downhill_norm)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    fall_line_angle_deg = np.degrees(np.arccos(np.abs(cos_angle)))

    return cross_slope_pct, terrain_slope_pct, fall_line_angle_deg
