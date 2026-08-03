"""FastAPI-tjeneste: POST /api/analyze tar imot en trasé + DEM og returnerer
en analyse basert på beste praksis for bærekraftig stibygging."""
from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .analysis import Thresholds, analyze_trail
from .dem import DemError, DemSampler
from .gpx_io import TrailParseError, parse_trail
from .schemas import AnalyzeResponse

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
