"""Finner mulige hopplinje-partier langs en trasé: korte, jevne
nedoverbakke-strekk der et hopp/tabletop kan få en naturlig landing (i
motsetning til et flatt/hardt landingspunkt).

Dette er en grov geometrisk heuristikk basert på helning, helnings-
konsistens og sidehelling langs traséen – **ikke** en fysisk hopp-/
banesimulering. Den tar ikke hensyn til innkjørselsfart, faktisk
sprangvidde/trajectory, siktlinjer, eller landingsvinkel presist. Alle
forslag er utgangspunkt for videre vurdering, og må detaljprosjekteres og
kontrolleres i felt av kompetent hopplinje-/stibygger før bygging –
spesielt med tanke på fart inn og faktisk oppnåelig sprangvidde.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .gpx_io import TrailPoint


@dataclass
class JumpCriteria:
    min_grade_pct: float = 8.0
    """Under denne helningen gir nedoverbakken for lite fart/fallhøyde til et naturlig hopp."""

    max_grade_pct: float = 35.0
    """Over denne helningen blir det for bratt/utrygt for et enkelt naturlig hopp uten videre tilpasning."""

    max_grade_variation_pct: float = 6.0
    """Maks variasjon (i prosentpoeng) i helning innenfor partiet – vi vil ha en jevn, forutsigbar skråning."""

    max_cross_slope_pct: float = 15.0
    """Over denne sidehellingen krever det vesentlig oppbygging/planering for en rettvendt hopplandingsplattform."""

    min_run_length_m: float = 5.0
    """Minste sammenhengende lengde for at partiet skal regnes som en reell mulighet."""


def find_jump_opportunities(
    points: list[TrailPoint],
    grade_pct: np.ndarray,
    cross_slope_pct: np.ndarray,
    seg_len: np.ndarray,
    cum_dist: np.ndarray,
    criteria: JumpCriteria | None = None,
) -> list[dict]:
    """Skanner segment-for-segment-dataene (allerede beregnet av analyze_trail)
    for sammenhengende, jevne nedoverbakke-partier som egner seg som
    hopplinje-utgangspunkt."""
    c = criteria or JumpCriteria()
    n_segments = len(grade_pct)
    if n_segments == 0:
        return []

    friendly = (
        (grade_pct < 0)
        & (np.abs(grade_pct) >= c.min_grade_pct)
        & (np.abs(grade_pct) <= c.max_grade_pct)
        & (cross_slope_pct <= c.max_cross_slope_pct)
    )

    opportunities: list[dict] = []
    i = 0
    while i < n_segments:
        if not friendly[i]:
            i += 1
            continue
        j = i
        while j + 1 < n_segments and friendly[j + 1]:
            j += 1

        run_grades = grade_pct[i : j + 1]
        run_length = float(cum_dist[j + 1] - cum_dist[i])
        variation = float(np.max(run_grades) - np.min(run_grades))

        if run_length >= c.min_run_length_m and variation <= c.max_grade_variation_pct:
            avg_grade = float(np.average(run_grades, weights=seg_len[i : j + 1]))
            opportunities.append(
                {
                    "start_index": i,
                    "end_index": j + 1,
                    "start": (points[i].lat, points[i].lon),
                    "end": (points[j + 1].lat, points[j + 1].lon),
                    "length_m": round(run_length, 1),
                    "avg_grade_pct": round(avg_grade, 2),
                    "grade_variation_pct": round(variation, 2),
                    "note": (
                        f"Jevn nedoverbakke (~{abs(avg_grade):.0f} % helning) over "
                        f"{run_length:.0f} m – naturlig egnet for hopp/tabletop med jevn landing. "
                        "Detaljprosjekter og kontroller i felt (innkjørselsfart, sprangvidde, sikt)."
                    ),
                }
            )
        i = j + 1

    return opportunities
