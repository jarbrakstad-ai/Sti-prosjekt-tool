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
import math
from dataclasses import dataclass

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString

from .analysis import Thresholds, analyze_trail
from .dem import DemError, DemSampler
from .gpx_io import TrailPoint

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
    """Sikkerhetsgrense: for store DEM-er gir et enormt søkerom og bør beskjæres først.
    A*-tilstanden inkluderer retning (16 varianter pr. celle, se _astar) for å
    unngå unødvendige omveier/sikksakk - det gjør søket mer presist, men også
    tyngre pr. celle enn en enkel (rad, kolonne)-tilstand, så et søk nær denne
    grensen kan ta betydelig tid (titalls sekunder til noen minutter)."""

    smooth_iterations: int = 2
    """Antall Chaikin-glattingsrunder på den ferdige ruten (0 = ingen glatting)."""

    smooth_ratio: float = 0.25
    """Hvor mye hvert hjørne kuttes per Chaikin-runde (0-0.5)."""

    leg_overlap_penalty_weight: float = 50.0
    """Straffer å gjenbruke celler et tidligere delstrekk (mellom to
    påfølgende rutepunkter) allerede har brukt, ved traséer med mellompunkt.
    Uten dette søkes hvert delstrekk helt uavhengig av de andre, og kan derfor
    ende opp med å konvergere på samme korridor/hylle i terrenget som et annet
    delstrekk - synlig som en trasé som løper oppå/krysser seg selv i kartet.
    Straffen er myk (ikke et forbud), slik at et delstrekk fortsatt kan bruke
    korridoren hvis det faktisk er eneste farbare vei (f.eks. et smalt skar)."""


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


def _dedupe_position_revisits(path_rc: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Kutter ut løkker der samme (rad, kolonne) forekommer flere ganger i en
    rekonstruert sti (se reconstruct() i _astar for hvorfor det kan skje)."""
    while True:
        seen: dict[tuple[int, int], int] = {}
        cut = None
        for idx, rc in enumerate(path_rc):
            if rc in seen:
                cut = (seen[rc], idx)
                break
            seen[rc] = idx
        if cut is None:
            return path_rc
        i, j = cut
        path_rc = path_rc[: i + 1] + path_rc[j + 1 :]


def _direction_vectors(dem: DemSampler) -> list[tuple[float, float, float]]:
    """Forhåndsberegner (ux, uy, avstand_m) for hver av de 16 retningene.

    Gitteret er akse-orientert med konstant pikselstørrelse, så disse er like
    for et gitt retningsindeks uansett hvor i gitteret man er - beregnes derfor
    kun én gang pr. søk i stedet for på nytt for hver kant (stor gevinst siden
    et retnings-utvidet tilstandsrom besøker hver celle opptil 16 ganger)."""
    dx, dy = dem.pixel_size()
    out = []
    for drow, dcol in _NEIGHBORS:
        wx = dcol * dx
        wy = drow * dy
        dist = math.hypot(wx, wy)
        out.append((wx / dist, wy / dist, dist))
    return out


def _astar(
    dem: DemSampler,
    start_rc: tuple[int, int],
    goal_rc: tuple[int, int],
    opt: RouteOptions,
    avoid_cells: frozenset[tuple[int, int]] = frozenset(),
) -> list[tuple[int, int]]:
    """A*-søk der tilstanden inkluderer innkommende retning (indeks i
    _NEIGHBORS, -1 for startpunktet som ennå ikke har en retning).

    Svingstraffen i _edge_cost avhenger av retningen inn til en celle. Uten et
    utvidet tilstandsrom ville A* "kollapse" hver (rad, kolonne) til én
    vilkårlig ankomstretning (den som først ga lavest kostnad dit) - og kunne
    dermed gå glipp av en litt lengre, men rettere innkomst som egentlig gir en
    betydelig billigere fortsettelse. Det viste seg i praksis som unødvendige
    omveier og sikksakk i foreslåtte traséer. Med retning som del av
    tilstanden søker A* korrekt gjennom alle relevante (celle, retning)-par.

    `avoid_cells` er celler tidligere delstrekk (ved mellompunkt) allerede har
    brukt - en myk straff (RouteOptions.leg_overlap_penalty_weight) holder
    dette delstrekket unna samme korridor når et alternativ finnes."""
    n_rows, n_cols = dem.shape()
    dir_vecs = _direction_vectors(dem)

    goal_x, goal_y = dem.rowcol_to_xy(*goal_rc)

    def heuristic(rc: tuple[int, int]) -> float:
        x, y = dem.rowcol_to_xy(*rc)
        straight_dist = float(np.hypot(x - goal_x, y - goal_y))
        return opt.distance_weight * straight_dist

    goal = goal_rc

    # Tilstand: (row, col, innkommende_retningsindeks). -1 = ingen retning ennå.
    State = tuple[int, int, int]
    start_state: State = (start_rc[0], start_rc[1], -1)

    g_score: dict[State, float] = {start_state: 0.0}
    came_from: dict[State, State] = {}
    open_heap: list[tuple[float, State]] = [(heuristic(start_rc), start_state)]
    visited: set[State] = set()

    def reconstruct(state: State) -> list[tuple[int, int]]:
        path = [(state[0], state[1])]
        while state in came_from:
            state = came_from[state]
            path.append((state[0], state[1]))
        path.reverse()
        # Tilstanden inkluderer retning, så samme (rad, kolonne) kan i
        # prinsippet forekomme flere ganger i stien (nådd via to ulike
        # retninger) selv om ingen tilstand er besøkt to ganger - det gir en
        # sti som bokstavelig talt går innom samme punkt igjen. Kutt ut slike
        # løkker (behold første besøk, hopp over til rett etter siste besøk).
        return _dedupe_position_revisits(path)

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current in visited:
            continue
        visited.add(current)

        row, col, in_dir = current
        if (row, col) == goal:
            return reconstruct(current)

        elev_current = float(dem.array[row, col])
        if math.isnan(elev_current):
            continue
        dzdx_c = float(dem.dzdx_grid[row, col])
        dzdy_c = float(dem.dzdy_grid[row, col])

        prev_ux = prev_uy = None
        if in_dir >= 0:
            prev_ux, prev_uy, _ = dir_vecs[in_dir]

        g_current = g_score[current]

        for dir_idx, (drow, dcol) in enumerate(_NEIGHBORS):
            nrow, ncol = row + drow, col + dcol
            if not (0 <= nrow < n_rows and 0 <= ncol < n_cols):
                continue
            neighbor = (nrow, ncol, dir_idx)
            if neighbor in visited:
                continue

            elev_n = float(dem.array[nrow, ncol])
            if math.isnan(elev_n):
                continue

            ux, uy, seg_dist = dir_vecs[dir_idx]

            dzdx_n = float(dem.dzdx_grid[nrow, ncol])
            dzdy_n = float(dem.dzdy_grid[nrow, ncol])
            dzdx_mid = (dzdx_c + dzdx_n) / 2.0
            dzdy_mid = (dzdy_c + dzdy_n) / 2.0

            cross_slope_pct = abs(-uy * dzdx_mid + ux * dzdy_mid) * 100.0
            downhill_norm = math.hypot(dzdx_mid, dzdy_mid)
            terrain_slope_pct = downhill_norm * 100.0
            if downhill_norm < 1e-9:
                fall_line_angle_deg = float("nan")
            else:
                cos_angle = -(ux * dzdx_mid + uy * dzdy_mid) / downhill_norm
                cos_angle = min(max(cos_angle, -1.0), 1.0)
                fall_line_angle_deg = math.degrees(math.acos(abs(cos_angle)))

            grade_pct = 100.0 * (elev_n - elev_current) / seg_dist

            turn_angle_deg = 0.0
            if prev_ux is not None:
                cos_turn = min(max(prev_ux * ux + prev_uy * uy, -1.0), 1.0)
                turn_angle_deg = math.degrees(math.acos(cos_turn))

            cost = _edge_cost(
                grade_pct,
                cross_slope_pct,
                terrain_slope_pct,
                fall_line_angle_deg,
                seg_dist,
                turn_angle_deg,
                opt,
            )
            if (nrow, ncol) in avoid_cells:
                cost += opt.leg_overlap_penalty_weight * seg_dist

            tentative_g = g_current + cost
            if tentative_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = tentative_g
                came_from[neighbor] = current
                heapq.heappush(open_heap, (tentative_g + heuristic((nrow, ncol)), neighbor))

    raise RoutingError(
        "Fant ingen mulig rute mellom start- og sluttpunkt (kan skyldes NaN/manglende "
        "høydedata mellom punktene)."
    )


def _segment_intersection(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> tuple[float, float] | None:
    """Skjæringspunkt mellom linjestykkene a1-a2 og b1-b2, hvis de faktisk
    krysser hverandre i det indre (ikke bare deler et endepunkt). None hvis
    parallelle/ikke-krysende."""
    x1, y1 = a1
    x2, y2 = a2
    x3, y3 = b1
    x4, y4 = b2
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-12:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / d
    if 0.0 < t < 1.0 and 0.0 < u < 1.0:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def _remove_self_intersections(
    xs: np.ndarray,
    ys: np.ndarray,
    protected_points: frozenset[tuple[float, float]] = frozenset(),
    max_cuts: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """Fjerner løkker der ruten krysser seg selv i planet.

    A*-søket besøker aldri samme rutenett-celle to ganger, men den
    resulterende linjen kan likevel krysse seg selv geometrisk - f.eks. når
    det er billigere å sveipe rundt en hel kolle på én side enn å justere
    kursen, og sveipen ender opp med å skjære gjennom traséens egen tidligere
    strekning. Denne funksjonen finner par av ikke-nabo-liggende linjestykker
    som krysser hverandre, og kutter ut løkken mellom dem (erstatter med selve
    skjæringspunktet), gjentatt til ruten er selv-skjæringsfri (eller max_cuts
    er nådd, som sikkerhetsgrense). `protected_points` (f.eks. obligatoriske
    mellompunkt ved en flerpunkts-trasé) fjernes aldri av et kutt - kandidater
    som ville fjernet et beskyttet punkt hoppes over til fordel for et annet
    kryssende par, om et slikt finnes."""
    pts = list(zip(xs.tolist(), ys.tolist()))

    for _ in range(max_cuts):
        n = len(pts)
        cut = None
        for i in range(n - 1):
            for j in range(i + 2, n - 1):
                if protected_points and any(p in protected_points for p in pts[i + 1 : j + 1]):
                    continue
                ip = _segment_intersection(pts[i], pts[i + 1], pts[j], pts[j + 1])
                if ip is not None:
                    cut = (i, j, ip)
                    break
            if cut is not None:
                break
        if cut is None:
            break
        i, j, ip = cut
        pts = pts[: i + 1] + [ip] + pts[j + 1 :]

    new_xs = np.array([p[0] for p in pts])
    new_ys = np.array([p[1] for p in pts])
    return new_xs, new_ys


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


def _lowest_point_rc(dem: DemSampler) -> tuple[int, int]:
    """Finner (rad, kolonne) for det laveste gyldige punktet i hele DEM-en -
    brukt som automatisk foreslått "utløp" når bare et startpunkt er oppgitt
    (se suggest_route). DEM-en gir ingen informasjon om hvor det faktisk
    finnes en bekk/kum/grøft i virkeligheten - det laveste punktet er bare en
    fysisk fornuftig gjetning (vann søker uansett dit) som må bekreftes i
    felt før bygging."""
    array = dem.array
    if np.all(np.isnan(array)):
        raise RoutingError("Høydemodellen mangler gyldige høydeverdier - kan ikke finne laveste punkt.")
    idx = int(np.nanargmin(array))
    row, col = np.unravel_index(idx, array.shape)
    return int(row), int(col)


def suggest_route(
    dem: DemSampler,
    waypoints_latlon: list[tuple[float, float]],
    options: RouteOptions | None = None,
) -> dict:
    """Foreslår en trasé gjennom en rekkefølge av punkter: `waypoints_latlon[0]`
    er startpunkt, `waypoints_latlon[-1]` er sluttpunkt, og eventuelle punkter
    i mellom er faste mellompunkter ruten *skal* gå gjennom (f.eks. for å styre
    linjeføringen unna et areal, eller innenfor en bestemt grunneiers eiendom).
    A* kjøres separat for hvert delstrekk (mellom to påfølgende punkter) og
    settes sammen til én sammenhengende trasé.

    Hvis kun ETT punkt oppgis (startpunkt), foreslås sluttpunktet automatisk
    som det laveste punktet i DEM-en - se _lowest_point_rc. Dette er en
    fysisk fornuftig gjetning, ikke en bekreftelse på at det faktisk finnes
    et gyldig utløp (bekk/kum/grøft) der i virkeligheten - `search_stats`
    i svaret markerer at sluttpunktet ble valgt automatisk, slik at brukeren
    kan varsles om å kontrollere det i felt."""
    opt = options or RouteOptions()

    if len(waypoints_latlon) < 1:
        raise RoutingError("Trenger minst et startpunkt.")

    n_rows, n_cols = dem.shape()
    if n_rows * n_cols > opt.max_grid_nodes:
        raise RoutingError(
            f"DEM-en er for stor for trasé-forslag ({n_rows}x{n_cols} celler). "
            f"Beskjær til et mindre område (maks {opt.max_grid_nodes} celler, f.eks. "
            f"{int(opt.max_grid_nodes ** 0.5)}x{int(opt.max_grid_nodes ** 0.5)})."
        )

    to_dem = Transformer.from_crs("EPSG:4326", dem.crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(dem.crs, "EPSG:4326", always_xy=True)

    rc_points: list[tuple[int, int]] = []
    for i, (lat, lon) in enumerate(waypoints_latlon):
        x, y = to_dem.transform(lon, lat)
        try:
            rc_points.append(dem.xy_to_nearest_rowcol(x, y))
        except DemError as exc:
            if i == 0:
                label = "Startpunktet"
            elif i == len(waypoints_latlon) - 1:
                label = "Sluttpunktet"
            else:
                label = f"Mellompunkt {i}"
            raise RoutingError(f"{label} ligger utenfor DEM-området: {exc}") from exc

    auto_endpoint = False
    if len(rc_points) == 1:
        auto_endpoint = True
        goal_rc = _lowest_point_rc(dem)
        if goal_rc == rc_points[0]:
            raise RoutingError(
                "Startpunktet er allerede det laveste punktet i høydemodellen - "
                "kan ikke foreslå et automatisk utløp herfra."
            )
        rc_points.append(goal_rc)

    for i in range(len(rc_points) - 1):
        if rc_points[i] == rc_points[i + 1]:
            raise RoutingError(
                f"Punkt {i + 1} og {i + 2} havner i samme DEM-celle. Velg punkter lenger fra hverandre."
            )

    def to_points(xs: np.ndarray, ys: np.ndarray) -> list[TrailPoint]:
        lons, lats = to_wgs84.transform(xs, ys)
        return [TrailPoint(lat=float(la), lon=float(lo)) for la, lo in zip(lats, lons)]

    total_raw_nodes = 0
    # Celler brukt av tidligere delstrekk - se leg_overlap_penalty_weight:
    # holder påfølgende delstrekk unna å konvergere på samme korridor som et
    # tidligere delstrekk (uten å forby det, hvis det faktisk er nødvendig).
    used_cells: set[tuple[int, int]] = set()

    leg_xy: list[tuple[np.ndarray, np.ndarray]] = []
    for leg in range(len(rc_points) - 1):
        leg_path_rc = _astar(
            dem, rc_points[leg], rc_points[leg + 1], opt, avoid_cells=frozenset(used_cells)
        )
        total_raw_nodes += len(leg_path_rc)
        used_cells.update(leg_path_rc)

        rows = np.array([p[0] for p in leg_path_rc])
        cols = np.array([p[1] for p in leg_path_rc])
        xs_raw, ys_raw = dem.rowcol_to_xy(rows, cols)
        # A* besøker aldri samme celle to ganger, men søket kan likevel finne
        # det billigst å sveipe rundt et hinder (f.eks. en kolle) på en måte
        # som gjør at selve linjen krysser sin egen tidligere strekning
        # geometrisk. Kutt ut slike løkker (innad i delstrekket) før de settes
        # sammen og analyseres.
        xs_raw, ys_raw = _remove_self_intersections(xs_raw, ys_raw)
        leg_xy.append((xs_raw, ys_raw))

    # Delstrekkene søkes uavhengig av hverandre (avoid_cells over er kun en
    # myk kostnad), så to delstrekk kan i sjeldne tilfeller likevel krysse
    # hverandre der de møtes nær et mellompunkt. Sett sammen hele traséen og
    # kjør en global løkke-fjerning på tvers av delstrekk-grensene - med
    # rutepunktene selv beskyttet, slik at de aldri fjernes av et kutt.
    combined_x: list[float] = []
    combined_y: list[float] = []
    junction_xy: list[tuple[float, float]] = []
    for leg, (xs_raw, ys_raw) in enumerate(leg_xy):
        xs_list, ys_list = xs_raw.tolist(), ys_raw.tolist()
        if leg == 0:
            combined_x.extend(xs_list)
            combined_y.extend(ys_list)
            junction_xy.append((xs_list[0], ys_list[0]))
        else:
            combined_x.extend(xs_list[1:])
            combined_y.extend(ys_list[1:])
        junction_xy.append((xs_list[-1], ys_list[-1]))

    combined_x_arr, combined_y_arr = _remove_self_intersections(
        np.array(combined_x), np.array(combined_y), protected_points=frozenset(junction_xy)
    )
    combined_x, combined_y = combined_x_arr.tolist(), combined_y_arr.tolist()

    raw_points_all = to_points(combined_x_arr, combined_y_arr)
    smooth_points_all: list[TrailPoint] = []

    # Del den (evt. rensede) sammensatte traséen tilbake i delstrekk ved
    # rutepunktene, slik at glatting fortsatt kan låse hvert delstrekks egne
    # endepunkter fast (obligatoriske mellompunkter flyttes aldri).
    split_indices = [0]
    search_from = 0
    for jx, jy in junction_xy[1:]:
        idx = search_from
        while (combined_x[idx], combined_y[idx]) != (jx, jy):
            idx += 1
        split_indices.append(idx)
        search_from = idx

    for leg in range(len(split_indices) - 1):
        start_i, end_i = split_indices[leg], split_indices[leg + 1]
        xs_leg = np.array(combined_x[start_i : end_i + 1])
        ys_leg = np.array(combined_y[start_i : end_i + 1])

        # Glatt hvert delstrekk for seg, med endepunktene (rutepunktene) låst
        # fast - slik at obligatoriske mellompunkter aldri flyttes av glattingen.
        if opt.smooth_iterations > 0:
            xs_smooth, ys_smooth = _chaikin_smooth(xs_leg, ys_leg, opt.smooth_iterations, opt.smooth_ratio)
            leg_smooth_points = to_points(xs_smooth, ys_smooth)
        else:
            leg_smooth_points = to_points(xs_leg, ys_leg)

        if leg == 0:
            smooth_points_all.extend(leg_smooth_points)
        else:
            # Hopp over første punkt i hvert nye delstrekk - det er identisk
            # med forrige delstrekks siste punkt (rutepunktet de deler).
            smooth_points_all.extend(leg_smooth_points[1:])

    raw_analysis = analyze_trail(raw_points_all, dem, Thresholds())

    points, analysis, smoothed = raw_points_all, raw_analysis, False
    if opt.smooth_iterations > 0:
        smooth_analysis = analyze_trail(smooth_points_all, dem, Thresholds())

        # Glatting er ren geometri og kjenner ikke til terrenget – den kan i
        # prinsippet kutte hjørner inn i terreng søket egentlig unngikk (f.eks.
        # en bratt kant). Faller tilbake til ujevnet rute hvis det skjer.
        raw_max = raw_analysis["summary"]["max_grade_pct"]
        smooth_max = smooth_analysis["summary"]["max_grade_pct"]
        if smooth_max <= max(raw_max * 1.5, raw_max + 10.0, opt.max_grade_pct):
            points, analysis, smoothed = smooth_points_all, smooth_analysis, True

    lons = [p.lon for p in points]
    lats = [p.lat for p in points]

    # Selv-kryssende løkker fjernes der det er mulig (se _remove_self_intersections),
    # men ved flere rutepunkter kan to delstrekk i sjeldne tilfeller likevel
    # møtes/krysse akkurat ved et mellompunkt der terrenget tvinger begge
    # delstrekk gjennom samme smale korridor - siden mellompunktet er
    # obligatorisk og aldri flyttes, er dette ikke alltid løsbart uten å velge
    # et annet mellompunkt. Rapporter det i stedet for å skjule det.
    self_intersects = False
    if len(points) >= 4:
        try:
            self_intersects = not LineString(list(zip(lons, lats))).is_simple
        except Exception:
            self_intersects = False

    return {
        "route": {
            "type": "LineString",
            "coordinates": [[lo, la] for la, lo in zip(lats, lons)],
        },
        "points": [[la, lo] for la, lo in zip(lats, lons)],
        "search_stats": {
            "grid_shape": [n_rows, n_cols],
            "raw_path_nodes": total_raw_nodes,
            "final_points": len(points),
            "smoothed": smoothed,
            "num_legs": len(rc_points) - 1,
            "self_intersects": self_intersects,
            "auto_endpoint": auto_endpoint,
        },
        "analysis": analysis,
    }
