"""Foreslå en trasé mellom to punkter ved å søke etter den "billigste" linjen
gjennom terrenget, der kostnaden straffer brudd på beste praksis for
bærekraftig stibygging (jf. analysis.py): for bratt helning, fall-line-følging,
half-rule-brudd og brå retningsskift. Implementert som A* over DEM-rutenettet
(16 retninger for finere vinkeloppløsning enn ren 8-nabo-gitter).

Dette er en heuristisk foreslått linje – ikke en ferdig prosjektert trasé.
Resultatet bør alltid kontrolleres i felt og av fagkyndig, og kjøres gjennom
`analyze_trail` (gjøres automatisk her) for å se gjenværende funn.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np
from pyproj import Transformer

from .analysis import Thresholds, analyze_trail
from .dem import DemSampler
from .gpx_io import TrailPoint
from .terrain_metrics import segment_metrics

# 16 retninger: de 8 vanlige gitter-naboene pluss 8 "springer"-trekk
# (±1,±2 / ±2,±1), som gir ~22.5° vinkeloppløsning i stedet for 45°.
# Dette reduserer sikksakk-artefakter fra rene diagonale/rette gitter-trekk.
_NEIGHBORS = [
    (-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1),
    (-2, -1), (-1, -2), (-2, 1), (-1, 2), (2, -1), (1, -2), (2, 1), (1, 2),
]


class RoutingError(ValueError):
    pass


@dataclass
class RouteOptions:
    trail_type: str = "flow"  # "flow" eller "xc"
    target_grade_pct: float = 6.0
    """For flow-stier: ønsket jevn helning (fortegn ignoreres, brukes som mål-|grade|)."""

    max_grade_pct: float = 15.0
    """Helning over dette straffes hardt (samme ånd som Thresholds.sustained_grade_max_pct)."""

    distance_weight: float = 1.0
    """Kostnad per meter reist – holder søket fra å ta unødvendige omveier."""

    grade_penalty_weight: float = 8.0
    fall_line_penalty_weight: float = 6.0
    half_rule_penalty_weight: float = 4.0

    turn_penalty_weight: float = 5.0
    """Straffer brå retningsskift. Høyere for flytstier (ønsker jevn rytme/flyt)."""

    max_grid_nodes: int = 400 * 400
    """Sikkerhetsgrense: for store DEM-er gir et enormt søkerom og bør beskjæres først."""

    smooth_iterations: int = 2
    """Antall Chaikin-glattingsrunder på den ferdige ruten (0 = ingen glatting)."""

    smooth_ratio: float = 0.25
    """Hvor mye hvert hjørne kuttes per Chaikin-runde (0-0.5)."""


def _edge_cost(
    grade_pct: float,
    cross_slope_pct: float,
    terrain_slope_pct: float,
    fall_line_angle_deg: float,
    dist_m: float,
    turn_angle_deg: float,
    opt: RouteOptions,
) -> float:
    cost = opt.distance_weight * dist_m

    if opt.trail_type == "flow":
        deviation = abs(abs(grade_pct) - opt.target_grade_pct)
    else:
        deviation = max(0.0, abs(grade_pct) - opt.target_grade_pct)
    cost += opt.grade_penalty_weight * (deviation ** 1.5) * (dist_m / 10.0)

    if abs(grade_pct) > opt.max_grade_pct:
        cost += opt.grade_penalty_weight * 50.0 * (dist_m / 10.0)

    if terrain_slope_pct >= 5.0 and not np.isnan(fall_line_angle_deg):
        fall_line_risk = max(0.0, (30.0 - fall_line_angle_deg) / 30.0)  # 0..1
        cost += opt.fall_line_penalty_weight * fall_line_risk * (terrain_slope_pct / 10.0) * (dist_m / 10.0)

    if cross_slope_pct >= 3.0:
        ratio = abs(grade_pct) / cross_slope_pct
        if ratio > 0.5:
            cost += opt.half_rule_penalty_weight * (ratio - 0.5) * (dist_m / 10.0)

    if turn_angle_deg > 0:
        cost += opt.turn_penalty_weight * (turn_angle_deg / 180.0) ** 2 * dist_m

    return max(cost, EPS_COST)


EPS_COST = 1e-6


def _astar(
    dem: DemSampler,
    start_rc: tuple[int, int],
    goal_rc: tuple[int, int],
    opt: RouteOptions,
) -> list[tuple[int, int]]:
    n_rows, n_cols = dem.shape()
    dx, dy = dem.pixel_size()
    cell = (abs(dx) + abs(dy)) / 2.0

    goal_x, goal_y = dem.rowcol_to_xy(*goal_rc)

    def heuristic(rc: tuple[int, int]) -> float:
        x, y = dem.rowcol_to_xy(*rc)
        straight_dist = float(np.hypot(x - goal_x, y - goal_y))
        return opt.distance_weight * straight_dist

    start = start_rc
    goal = goal_rc

    g_score: dict[tuple[int, int], float] = {start: 0.0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    open_heap: list[tuple[float, tuple[int, int]]] = [(heuristic(start), start)]
    visited: set[tuple[int, int]] = set()

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current in visited:
            continue
        visited.add(current)

        if current == goal:
            path = [current]
            while path[-1] in came_from:
                path.append(came_from[path[-1]])
            path.reverse()
            return path

        row, col = current
        elev_current = float(dem.array[row, col])
        dzdx_c = float(dem.dzdx_grid[row, col])
        dzdy_c = float(dem.dzdy_grid[row, col])
        x_c, y_c = dem.rowcol_to_xy(row, col)

        prev_dir = None
        parent = came_from.get(current)
        if parent is not None:
            px, py = dem.rowcol_to_xy(*parent)
            pd = float(np.hypot(x_c - px, y_c - py))
            if pd > EPS_COST:
                prev_dir = ((x_c - px) / pd, (y_c - py) / pd)

        for drow, dcol in _NEIGHBORS:
            nrow, ncol = row + drow, col + dcol
            if not (0 <= nrow < n_rows and 0 <= ncol < n_cols):
                continue
            neighbor = (nrow, ncol)
            if neighbor in visited:
                continue

            elev_n = float(dem.array[nrow, ncol])
            if np.isnan(elev_current) or np.isnan(elev_n):
                continue

            x_n, y_n = dem.rowcol_to_xy(nrow, ncol)
            seg_dist = float(np.hypot(x_n - x_c, y_n - y_c))
            if seg_dist < EPS_COST:
                continue
            ux, uy = (x_n - x_c) / seg_dist, (y_n - y_c) / seg_dist

            dzdx_n = float(dem.dzdx_grid[nrow, ncol])
            dzdy_n = float(dem.dzdy_grid[nrow, ncol])
            dzdx_mid = (dzdx_c + dzdx_n) / 2.0
            dzdy_mid = (dzdy_c + dzdy_n) / 2.0

            cross_slope_pct, terrain_slope_pct, fall_line_angle_deg = segment_metrics(
                np.array([ux]), np.array([uy]), np.array([dzdx_mid]), np.array([dzdy_mid])
            )
            grade_pct = 100.0 * (elev_n - elev_current) / seg_dist

            turn_angle_deg = 0.0
            if prev_dir is not None:
                cos_turn = np.clip(prev_dir[0] * ux + prev_dir[1] * uy, -1.0, 1.0)
                turn_angle_deg = float(np.degrees(np.arccos(cos_turn)))

            cost = _edge_cost(
                grade_pct,
                float(cross_slope_pct[0]),
                float(terrain_slope_pct[0]),
                float(fall_line_angle_deg[0]),
                seg_dist,
                turn_angle_deg,
                opt,
            )

            tentative_g = g_score[current] + cost
            if tentative_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = tentative_g
                came_from[neighbor] = current
                heapq.heappush(open_heap, (tentative_g + heuristic(neighbor), neighbor))

    raise RoutingError(
        "Fant ingen mulig rute mellom start- og sluttpunkt (kan skyldes NaN/manglende "
        "høydedata mellom punktene)."
    )


def _chaikin_smooth(
    xs: np.ndarray, ys: np.ndarray, iterations: int, ratio: float
) -> tuple[np.ndarray, np.ndarray]:
    """Chaikins hjørnekutting, med start- og sluttpunkt låst fast. Gjør en
    gitter-hakkete linje til en jevnere kurve som er bedre egnet for flyt-rytme."""
    if iterations <= 0 or len(xs) < 3:
        return xs, ys

    pts = list(zip(xs.tolist(), ys.tolist()))
    ratio = min(max(ratio, 0.0), 0.5)

    for _ in range(iterations):
        new_pts = [pts[0]]
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            qx, qy = x0 + ratio * (x1 - x0), y0 + ratio * (y1 - y0)
            rx, ry = x0 + (1 - ratio) * (x1 - x0), y0 + (1 - ratio) * (y1 - y0)
            new_pts.append((qx, qy))
            new_pts.append((rx, ry))
        new_pts.append(pts[-1])
        pts = new_pts

    new_xs = np.array([p[0] for p in pts])
    new_ys = np.array([p[1] for p in pts])
    return new_xs, new_ys


def suggest_route(
    dem: DemSampler,
    start_latlon: tuple[float, float],
    end_latlon: tuple[float, float],
    options: RouteOptions | None = None,
) -> dict:
    opt = options or RouteOptions()

    n_rows, n_cols = dem.shape()
    if n_rows * n_cols > opt.max_grid_nodes:
        raise RoutingError(
            f"DEM-en er for stor for trasé-forslag ({n_rows}x{n_cols} celler). "
            f"Beskjær til et mindre område (maks {opt.max_grid_nodes} celler, f.eks. "
            f"{int(opt.max_grid_nodes ** 0.5)}x{int(opt.max_grid_nodes ** 0.5)})."
        )

    to_dem = Transformer.from_crs("EPSG:4326", dem.crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(dem.crs, "EPSG:4326", always_xy=True)

    start_x, start_y = to_dem.transform(start_latlon[1], start_latlon[0])
    end_x, end_y = to_dem.transform(end_latlon[1], end_latlon[0])

    start_rc = dem.xy_to_nearest_rowcol(start_x, start_y)
    end_rc = dem.xy_to_nearest_rowcol(end_x, end_y)

    if start_rc == end_rc:
        raise RoutingError("Start- og sluttpunkt havner i samme DEM-celle. Velg punkter lenger fra hverandre.")

    path_rc = _astar(dem, start_rc, end_rc, opt)

    rows = np.array([p[0] for p in path_rc])
    cols = np.array([p[1] for p in path_rc])
    xs_raw, ys_raw = dem.rowcol_to_xy(rows, cols)

    def to_points(xs: np.ndarray, ys: np.ndarray) -> list[TrailPoint]:
        lons, lats = to_wgs84.transform(xs, ys)
        return [TrailPoint(lat=float(la), lon=float(lo)) for la, lo in zip(lats, lons)]

    raw_points = to_points(xs_raw, ys_raw)
    raw_analysis = analyze_trail(raw_points, dem, Thresholds())

    points, analysis, smoothed = raw_points, raw_analysis, False
    if opt.smooth_iterations > 0:
        xs_smooth, ys_smooth = _chaikin_smooth(xs_raw, ys_raw, opt.smooth_iterations, opt.smooth_ratio)
        smooth_points = to_points(xs_smooth, ys_smooth)
        smooth_analysis = analyze_trail(smooth_points, dem, Thresholds())

        # Glatting er ren geometri og kjenner ikke til terrenget – den kan i
        # prinsippet kutte hjørner inn i terreng søket egentlig unngikk (f.eks.
        # en bratt kant). Faller tilbake til ujevnet rute hvis det skjer.
        raw_max = raw_analysis["summary"]["max_grade_pct"]
        smooth_max = smooth_analysis["summary"]["max_grade_pct"]
        if smooth_max <= max(raw_max * 1.5, raw_max + 10.0, opt.max_grade_pct):
            points, analysis, smoothed = smooth_points, smooth_analysis, True

    lons = [p.lon for p in points]
    lats = [p.lat for p in points]

    return {
        "route": {
            "type": "LineString",
            "coordinates": [[lo, la] for la, lo in zip(lats, lons)],
        },
        "points": [[la, lo] for la, lo in zip(lats, lons)],
        "search_stats": {
            "grid_shape": [n_rows, n_cols],
            "raw_path_nodes": len(path_rc),
            "final_points": len(points),
            "smoothed": smoothed,
        },
        "analysis": analysis,
    }
