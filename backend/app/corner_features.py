"""Finner skarpe svinger langs en trasé og anbefaler dosering (berm-vinkel)
for jevn flyt gjennom svingen, basert på anslått svingradius og en antatt
hastighet.

Dette er en grov geometrisk/fysisk heuristikk – **ikke** en presis
kjøredynamikk-simulering. Svingradius anslås fra diskrete GPS-/DEM-punkter
(korde-lengde / vinkel), og hastigheten er en antakelse (justert noe opp
for lokalt fallende terreng), ikke en målt eller simulert fart. Faktisk
komfortabel dosering avhenger også av underlag, sikt og syklistens
erfaringsnivå. Bruk forslagene som utgangspunkt, ikke fasit – kontroller og
detaljprosjekter i felt.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .gpx_io import TrailPoint

_G = 9.81  # tyngdeakselerasjon, m/s^2


@dataclass
class CornerCriteria:
    min_turn_angle_deg: float = 20.0
    """Under denne retningsendringen regnes svingen som en slak bue - ingen dosering nødvendig."""

    design_speed_kmh: float = 20.0
    """Antatt "grunnfart" gjennom svinger, typisk for en flytsti. Juster etter kontekst."""

    grade_speed_boost_per_pct: float = 1.0 / 50.0
    """Hvor mye antatt fart øker per prosentpoeng lokal nedoverbakke (0.02 = 2 % fartsøkning per 1 % helning)."""

    max_comfortable_bank_deg: float = 25.0
    """Over denne anbefalte doseringsvinkelen bør svingradiusen økes i stedet for enda brattere berm."""


def find_corner_recommendations(
    points: list[TrailPoint],
    ux: np.ndarray,
    uy: np.ndarray,
    seg_len: np.ndarray,
    grade_pct: np.ndarray,
    criteria: CornerCriteria | None = None,
) -> list[dict]:
    """Skanner retningsendring mellom naboseg­menter (allerede beregnet av
    analyze_trail) og anbefaler dosering for svinger over vinkelterskelen."""
    c = criteria or CornerCriteria()
    n_segments = len(ux)
    recommendations: list[dict] = []

    for i in range(1, n_segments):
        cos_turn = np.clip(ux[i - 1] * ux[i] + uy[i - 1] * uy[i], -1.0, 1.0)
        turn_angle_deg = float(np.degrees(np.arccos(cos_turn)))
        if turn_angle_deg < c.min_turn_angle_deg:
            continue

        turn_angle_rad = np.radians(turn_angle_deg)
        local_len = float((seg_len[i - 1] + seg_len[i]) / 2.0)
        radius_m = local_len / turn_angle_rad if turn_angle_rad > 1e-6 else float("inf")

        local_grade_pct = float((grade_pct[i - 1] + grade_pct[i]) / 2.0)
        descending_pct = max(0.0, -local_grade_pct)
        speed_factor = 1.0 + descending_pct * c.grade_speed_boost_per_pct
        speed_kmh = c.design_speed_kmh * speed_factor
        speed_ms = speed_kmh / 3.6

        bank_deg = float(np.degrees(np.arctan((speed_ms**2) / (_G * radius_m)))) if radius_m > 0 else 90.0

        flags: list[str] = []
        note = (
            f"Sving på ~{turn_angle_deg:.0f}°, anslått radius {radius_m:.1f} m ved antatt fart "
            f"~{speed_kmh:.0f} km/t – anbefalt dosering (berm-vinkel) ca. {bank_deg:.0f}° for jevn "
            "flyt uten hard sidekraft/bremsing."
        )
        if bank_deg > c.max_comfortable_bank_deg:
            flags.append("bank_angle_high")
            note += (
                f" Anbefalt vinkel overstiger {c.max_comfortable_bank_deg:.0f}° – vurder å øke "
                "svingradiusen i stedet for en svært bratt berm."
            )

        recommendations.append(
            {
                "point_index": i,
                "location": (points[i].lat, points[i].lon),
                "turn_angle_deg": round(turn_angle_deg, 1),
                "estimated_radius_m": round(radius_m, 1),
                "assumed_speed_kmh": round(speed_kmh, 1),
                "recommended_bank_deg": round(bank_deg, 1),
                "flags": flags,
                "note": note,
            }
        )

    return recommendations
