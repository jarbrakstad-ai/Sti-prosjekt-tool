"""Kjerneanalyse: vurderer en gitt trasé opp mot beste praksis for
bærekraftig stibygging (IMBA Trail Solutions-prinsipper, tilpasset
sykkelsti/flytsti).

Terskelverdiene under er **veiledende heuristikker**, ikke en offisiell norsk
standard. De er hentet fra allment brukte tommelfingerregler i internasjonal
stibyggingslitteratur (Half Rule, Ten Percent Guideline, Grade Reversals,
Avoid the Fall Line) og bør kalibreres mot lokale grunnforhold, klima og
gjeldende retningslinjer fra grunneier/kommune før traséen bygges.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from pyproj import Transformer

from .dem import DemSampler
from .gpx_io import TrailPoint
from .terrain_metrics import segment_metrics

EPS = 1e-9


@dataclass
class Thresholds:
    half_rule_max_ratio: float = 0.5
    """Half Rule: stigrad bør ikke overstige denne andelen av sidehellingen."""

    min_cross_slope_for_half_rule_pct: float = 3.0
    """Under denne sidehellingen er half-rule lite meningsfull (nær flatt terreng)."""

    avg_grade_warn_pct: float = 10.0
    """Ten Percent Guideline: varsel over dette for gjennomsnittlig helning."""

    sustained_grade_max_pct: float = 15.0
    """Grense for enkeltsegment-helning før det flagges som for bratt uten videre kontekst."""

    fall_line_bad_deg: float = 15.0
    """Vinkel mellom sti og fallretning under dette = høy erosjonsrisiko (følger fallinjen)."""

    fall_line_warn_deg: float = 30.0
    """Vinkel under dette = moderat risiko."""

    fall_line_min_terrain_slope_pct: float = 5.0
    """Fall-line-vurdering er kun relevant der terrenget faktisk heller."""

    reversal_base_interval_m: float = 50.0
    """Maks avstand mellom drenerende motfall ("grade reversal") ved ~5 % helning."""

    reversal_reference_grade_pct: float = 5.0

    reversal_min_interval_m: float = 15.0

    abrupt_transition_delta_pct: float = 8.0
    """Endring i helning (prosentpoeng) mellom naboseg­menter som flagges for flytsti-rytme."""

    elevation_mismatch_m: float = 8.0
    """Avvik mellom GPX-oppgitt høyde og DEM-høyde som flagges som informasjon."""


@dataclass
class SegmentResult:
    index: int
    start: tuple[float, float]  # lat, lon
    end: tuple[float, float]
    length_m: float
    grade_pct: float
    cross_slope_pct: float | None
    half_rule_ratio: float | None
    fall_line_angle_deg: float | None
    flags: list[str] = field(default_factory=list)


def _project_points(points: list[TrailPoint], dem_crs) -> tuple[np.ndarray, np.ndarray]:
    transformer = Transformer.from_crs("EPSG:4326", dem_crs, always_xy=True)
    lons = np.array([p.lon for p in points])
    lats = np.array([p.lat for p in points])
    xs, ys = transformer.transform(lons, lats)
    return np.asarray(xs), np.asarray(ys)


def _reversal_threshold(avg_grade_pct: float, t: Thresholds) -> float:
    grade = max(abs(avg_grade_pct), 0.5)
    threshold = t.reversal_base_interval_m * (t.reversal_reference_grade_pct / grade)
    return float(np.clip(threshold, t.reversal_min_interval_m, t.reversal_base_interval_m))


def analyze_trail(
    points: list[TrailPoint],
    dem: DemSampler,
    thresholds: Thresholds | None = None,
) -> dict:
    if len(points) < 2:
        raise ValueError("Traséen må ha minst 2 punkter.")

    t = thresholds or Thresholds()

    xs, ys = _project_points(points, dem.crs)
    dem_elevations = dem.sample_elevation(xs, ys)
    dzdx, dzdy = dem.sample_gradient(xs, ys)

    n = len(points)
    seg_len = np.hypot(np.diff(xs), np.diff(ys))
    seg_len = np.where(seg_len < EPS, EPS, seg_len)
    cum_dist = np.concatenate([[0.0], np.cumsum(seg_len)])

    ux = np.diff(xs) / seg_len
    uy = np.diff(ys) / seg_len

    dzdx_mid = (dzdx[:-1] + dzdx[1:]) / 2.0
    dzdy_mid = (dzdy[:-1] + dzdy[1:]) / 2.0

    delta_z = np.diff(dem_elevations)
    grade_pct = 100.0 * delta_z / seg_len

    cross_slope_pct, terrain_slope_pct, fall_line_angle_deg = segment_metrics(
        ux, uy, dzdx_mid, dzdy_mid
    )

    segments: list[SegmentResult] = []
    for i in range(n - 1):
        flags: list[str] = []

        cross_val = float(cross_slope_pct[i])
        half_ratio: float | None = None
        if cross_val >= t.min_cross_slope_for_half_rule_pct:
            half_ratio = abs(float(grade_pct[i])) / cross_val
            if half_ratio > t.half_rule_max_ratio:
                flags.append("half_rule_violation")

        if abs(float(grade_pct[i])) > t.sustained_grade_max_pct:
            flags.append("steep_grade")

        fall_angle: float | None = None
        if terrain_slope_pct[i] >= t.fall_line_min_terrain_slope_pct and not np.isnan(fall_line_angle_deg[i]):
            fall_angle = float(fall_line_angle_deg[i])
            if fall_angle < t.fall_line_bad_deg:
                flags.append("fall_line_high_risk")
            elif fall_angle < t.fall_line_warn_deg:
                flags.append("fall_line_moderate_risk")

        if points[i].ele is not None:
            if abs(points[i].ele - float(dem_elevations[i])) > t.elevation_mismatch_m:
                flags.append("elevation_mismatch")

        segments.append(
            SegmentResult(
                index=i,
                start=(points[i].lat, points[i].lon),
                end=(points[i + 1].lat, points[i + 1].lon),
                length_m=float(seg_len[i]),
                grade_pct=float(grade_pct[i]),
                cross_slope_pct=cross_val,
                half_rule_ratio=half_ratio,
                fall_line_angle_deg=fall_angle,
                flags=flags,
            )
        )

    # Grade reversals: lokale høydeminima langs traséen (dreneringspunkter).
    is_local_min = np.zeros(n, dtype=bool)
    is_local_min[1:-1] = (dem_elevations[1:-1] < dem_elevations[:-2]) & (
        dem_elevations[1:-1] < dem_elevations[2:]
    )

    last_reversal_dist = 0.0
    descent_start_dist = None
    descent_start_idx = None
    for i in range(n - 1):
        if grade_pct[i] < -0.5:
            if descent_start_dist is None:
                descent_start_dist = cum_dist[i]
                descent_start_idx = i
        else:
            descent_start_dist = None
            descent_start_idx = None

        if is_local_min[i + 1]:
            last_reversal_dist = cum_dist[i + 1]
            descent_start_dist = None
            descent_start_idx = None
            continue

        if descent_start_dist is not None:
            run_len = cum_dist[i + 1] - descent_start_dist
            avg_grade_in_run = float(
                np.mean(grade_pct[descent_start_idx : i + 1])
            )
            allowed = _reversal_threshold(avg_grade_in_run, t)
            since_reversal = cum_dist[i + 1] - last_reversal_dist
            if since_reversal > allowed and run_len > allowed:
                segments[i].flags.append("missing_grade_reversal")

    # Flyt-konsistens: brå endring i helning mellom naboseg­menter.
    for i in range(1, n - 1):
        delta = abs(grade_pct[i] - grade_pct[i - 1])
        if delta > t.abrupt_transition_delta_pct:
            segments[i].flags.append("abrupt_grade_transition")

    total_length = float(np.sum(seg_len))
    elevation_gain = float(np.sum(delta_z[delta_z > 0]))
    elevation_loss = float(-np.sum(delta_z[delta_z < 0]))
    weighted_avg_grade = float(np.sum(np.abs(grade_pct) * seg_len) / total_length) if total_length > 0 else 0.0
    max_grade = float(np.max(np.abs(grade_pct))) if len(grade_pct) else 0.0

    flag_counts: dict[str, int] = {}
    for s in segments:
        for f in s.flags:
            flag_counts[f] = flag_counts.get(f, 0) + 1

    flagged_segments = sum(1 for s in segments if s.flags)
    fraction_clean = 1.0 - (flagged_segments / len(segments) if segments else 0)
    score = round(100.0 * fraction_clean, 1)

    recommendations = _build_recommendations(flag_counts, weighted_avg_grade, t)

    return {
        "summary": {
            "total_length_m": round(total_length, 1),
            "elevation_gain_m": round(elevation_gain, 1),
            "elevation_loss_m": round(elevation_loss, 1),
            "avg_grade_pct": round(weighted_avg_grade, 2),
            "max_grade_pct": round(max_grade, 2),
            "num_segments": len(segments),
            "flagged_segments": flagged_segments,
            "flag_counts": flag_counts,
            "sustainability_score": score,
        },
        "recommendations": recommendations,
        "waypoints": [
            {
                "index": i,
                "lat": round(points[i].lat, 6),
                "lon": round(points[i].lon, 6),
                "elevation_m": round(float(dem_elevations[i]), 1),
                "distance_from_start_m": round(float(cum_dist[i]), 1),
            }
            for i in range(n)
        ],
        "segments": [
            {
                "index": s.index,
                "start": s.start,
                "end": s.end,
                "length_m": round(s.length_m, 1),
                "grade_pct": round(s.grade_pct, 2),
                "cross_slope_pct": round(s.cross_slope_pct, 2) if s.cross_slope_pct is not None else None,
                "half_rule_ratio": round(s.half_rule_ratio, 2) if s.half_rule_ratio is not None else None,
                "fall_line_angle_deg": round(s.fall_line_angle_deg, 1) if s.fall_line_angle_deg is not None else None,
                "flags": s.flags,
            }
            for s in segments
        ],
    }


_FLAG_MESSAGES = {
    "half_rule_violation": (
        "Half Rule brytes på {n} segment(er): stigraden overstiger halvparten av "
        "sidehellingen. Vann vil renne langs stien i stedet for av den – vurder å "
        "flytte traséen til brattere sideterreng eller redusere stigraden der."
    ),
    "steep_grade": (
        "{n} segment(er) har helning over anbefalt maksgrense. Vurder lengre "
        "svinger/traversering for å redusere helningen."
    ),
    "fall_line_high_risk": (
        "{n} segment(er) følger fallinjen tett (høy erosjonsrisiko). Traséen bør "
        "legges mer på tvers av hellingen."
    ),
    "fall_line_moderate_risk": (
        "{n} segment(er) har moderat fall-line-risiko – vurder om vinkelen mot "
        "hellingen kan økes noe."
    ),
    "missing_grade_reversal": (
        "{n} segment(er) mangler drenerende motfall (grade reversal) på sammenhengende "
        "nedoverbakke. Legg inn flere dip/motfall for å lede vann av stien."
    ),
    "abrupt_grade_transition": (
        "{n} segment(er) har brå endring i helning mellom naboseg­menter, noe som gir "
        "ujevn flyt/rytme for syklist."
    ),
    "elevation_mismatch": (
        "{n} punkt(er) har stort avvik mellom oppgitt GPX-høyde og DEM-høyde – "
        "sjekk om dette skyldes GPS-unøyaktighet eller bru/kunstig konstruksjon."
    ),
}


def _build_recommendations(flag_counts: dict[str, int], avg_grade: float, t: Thresholds) -> list[str]:
    recs = []
    if avg_grade > t.avg_grade_warn_pct:
        recs.append(
            f"Gjennomsnittlig helning ({avg_grade:.1f} %) overstiger tommelfingerregelen på "
            f"{t.avg_grade_warn_pct:.0f} % (Ten Percent Guideline)."
        )
    for flag, n in flag_counts.items():
        template = _FLAG_MESSAGES.get(flag)
        if template:
            recs.append(template.format(n=n))
    if not recs:
        recs.append("Ingen brudd på de sjekkede tommelfingerreglene ble funnet.")
    return recs
