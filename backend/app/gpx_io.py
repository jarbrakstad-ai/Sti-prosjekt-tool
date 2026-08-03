"""Parsing av trasé-input (GPX-spor eller GeoJSON LineString) til punktliste."""
from __future__ import annotations

import json
from dataclasses import dataclass

import gpxpy


@dataclass
class TrailPoint:
    lat: float
    lon: float
    ele: float | None = None  # høyde oppgitt i kildefilen, kan mangle


class TrailParseError(ValueError):
    pass


def parse_trail(filename: str, content: bytes) -> list[TrailPoint]:
    """Parser GPX eller GeoJSON ut fra filendelse/innhold og returnerer punkter i rekkefølge."""
    lower = filename.lower()
    if lower.endswith(".gpx"):
        return _parse_gpx(content)
    if lower.endswith((".json", ".geojson")):
        return _parse_geojson(content)

    # Fallback: prøv å tolke innholdet.
    stripped = content.lstrip()[:1]
    if stripped in (b"{", b"["):
        return _parse_geojson(content)
    return _parse_gpx(content)


def _parse_gpx(content: bytes) -> list[TrailPoint]:
    try:
        gpx = gpxpy.parse(content.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise TrailParseError(f"Klarte ikke å tolke GPX-fil: {exc}") from exc

    points: list[TrailPoint] = []
    for track in gpx.tracks:
        for segment in track.segments:
            for p in segment.points:
                points.append(TrailPoint(lat=p.latitude, lon=p.longitude, ele=p.elevation))
    if not points:
        for route in gpx.routes:
            for p in route.points:
                points.append(TrailPoint(lat=p.latitude, lon=p.longitude, ele=p.elevation))

    if len(points) < 2:
        raise TrailParseError("GPX-filen inneholder ingen sammenhengende spor/rute med minst 2 punkter.")
    return points


def _parse_geojson(content: bytes) -> list[TrailPoint]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TrailParseError(f"Klarte ikke å tolke GeoJSON: {exc}") from exc

    geometry = data
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
        if not features:
            raise TrailParseError("GeoJSON FeatureCollection inneholder ingen features.")
        geometry = features[0].get("geometry")
    elif data.get("type") == "Feature":
        geometry = data.get("geometry")

    if not geometry or geometry.get("type") != "LineString":
        raise TrailParseError("Fant ingen LineString-geometri i GeoJSON-filen.")

    coords = geometry.get("coordinates", [])
    if len(coords) < 2:
        raise TrailParseError("Traséen må ha minst 2 punkter.")

    points = []
    for c in coords:
        lon, lat = c[0], c[1]
        ele = c[2] if len(c) > 2 else None
        points.append(TrailPoint(lat=lat, lon=lon, ele=ele))
    return points
