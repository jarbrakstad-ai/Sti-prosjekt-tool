"""FastAPI-tjeneste: POST /api/analyze tar imot en trasé + DEM og returnerer
en analyse basert på beste praksis for bærekraftig stibygging."""
from __future__ import annotations

import json

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .analysis import Thresholds, analyze_trail
from .dem import DemError, DemSampler
from .dem_fetch import DemFetchError, fetch_dem_geotiff
from .gpx_io import TrailParseError, parse_trail
from .routing import RouteOptions, RoutingError, suggest_route
from .schemas import AnalyzeResponse
from .terrain_grid import build_terrain_grid

app = FastAPI(title="Sti-prosjekt-tool API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(
    trail: UploadFile = File(..., description="GPX-spor eller GeoJSON LineString"),
    dem: UploadFile = File(..., description="Høydemodell, GeoTIFF i projisert CRS (meter)"),
) -> dict:
    trail_bytes = await trail.read()
    dem_bytes = await dem.read()

    try:
        points = parse_trail(trail.filename or "trail.gpx", trail_bytes)
    except TrailParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        dem_sampler = DemSampler.from_geotiff_bytes(dem_bytes)
    except DemError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = analyze_trail(points, dem_sampler, Thresholds())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result


@app.post("/api/dem/fetch")
async def dem_fetch(
    min_lat: float = Form(...),
    min_lon: float = Form(...),
    max_lat: float = Form(...),
    max_lon: float = Form(...),
    resolution_m: float = Form(10.0),
) -> Response:
    """Henter en GeoTIFF-DEM automatisk fra Kartverkets høydedata-tjeneste for
    det gitte lat/lon-kartutsnittet, som alternativ til manuell opplasting."""
    try:
        tiff_bytes = await fetch_dem_geotiff(min_lat, min_lon, max_lat, max_lon, resolution_m)
    except DemFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(content=tiff_bytes, media_type="image/tiff")


@app.post("/api/dem/terrain-grid")
async def dem_terrain_grid(
    dem: UploadFile = File(..., description="Høydemodell, GeoTIFF i projisert CRS (meter)"),
) -> dict:
    """Returnerer et nedskalert høydegitter for 3D-visning av terrenget i
    frontend, i samme lokale koordinatsystem som waypoints' x_m/y_m fra
    /api/analyze og /api/suggest (så lenge det er samme DEM-fil)."""
    dem_bytes = await dem.read()
    try:
        dem_sampler = DemSampler.from_geotiff_bytes(dem_bytes)
    except DemError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return build_terrain_grid(dem_sampler)


@app.post("/api/suggest")
async def suggest(
    dem: UploadFile = File(..., description="Høydemodell, GeoTIFF i projisert CRS (meter)"),
    waypoints_json: str = Form(
        ...,
        description=(
            "JSON-liste med [lat, lon]-par: start, ev. mellompunkt(er), slutt. "
            "Kun ett punkt (bare start) foreslår automatisk sluttpunkt som laveste "
            "punkt i DEM-en (se search_stats.auto_endpoint i svaret)."
        ),
    ),
    trail_type: str = Form("flow", description="'flow' eller 'xc'"),
    target_grade_pct: float = Form(6.0),
) -> dict:
    if trail_type not in ("flow", "xc"):
        raise HTTPException(status_code=400, detail="trail_type må være 'flow' eller 'xc'.")

    try:
        raw_waypoints = json.loads(waypoints_json)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="waypoints_json er ikke gyldig JSON.") from exc

    if not isinstance(raw_waypoints, list) or len(raw_waypoints) < 1:
        raise HTTPException(
            status_code=400,
            detail="waypoints_json må være en liste med minst 1 punkt (startpunktet).",
        )

    try:
        waypoints = [(float(p[0]), float(p[1])) for p in raw_waypoints]
    except (TypeError, ValueError, IndexError) as exc:
        raise HTTPException(
            status_code=400, detail="Hvert punkt i waypoints_json må være [lat, lon]."
        ) from exc

    dem_bytes = await dem.read()
    try:
        dem_sampler = DemSampler.from_geotiff_bytes(dem_bytes)
    except DemError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    options = RouteOptions(trail_type=trail_type, target_grade_pct=target_grade_pct)

    try:
        result = suggest_route(dem_sampler, waypoints, options)
    except RoutingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result
