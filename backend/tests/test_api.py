"""Integrasjonstester av API-et med en ekte GeoTIFF (skrevet/lest via rasterio)."""
from __future__ import annotations

import numpy as np
import rasterio
from affine import Affine
from fastapi.testclient import TestClient
from pyproj import Transformer
from rasterio.crs import CRS

from app.main import app

UTM = "EPSG:32633"
client = TestClient(app)


def make_geotiff_bytes(tmp_path, size: int = 40, cell: float = 5.0) -> bytes:
    array = np.full((size, size), 1000.0, dtype="float64")
    # svak, jevn helning sørover for litt variasjon
    rows = np.arange(size)[:, None]
    array = array - 0.03 * cell * rows

    transform = Affine(cell, 0, 500000, 0, -cell, 6600000)
    path = tmp_path / "dem.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=size,
        width=size,
        count=1,
        dtype="float64",
        crs=CRS.from_string(UTM),
        transform=transform,
    ) as dst:
        dst.write(array, 1)
    return path.read_bytes()


def latlon_for_xy(x: float, y: float) -> tuple[float, float]:
    transformer = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return lat, lon


def make_gpx_bytes(points: list[tuple[float, float]]) -> bytes:
    trkpts = "\n".join(f'<trkpt lat="{lat}" lon="{lon}"></trkpt>' for lat, lon in points)
    gpx = f"""<?xml version="1.0"?>
<gpx version="1.1" creator="test"><trk><trkseg>
{trkpts}
</trkseg></trk></gpx>"""
    return gpx.encode("utf-8")


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_analyze_endpoint_end_to_end(tmp_path):
    dem_bytes = make_geotiff_bytes(tmp_path)
    pts = [latlon_for_xy(500100, y) for y in (6599900, 6599950, 6600000)]
    gpx_bytes = make_gpx_bytes(pts)

    res = client.post(
        "/api/analyze",
        files={
            "trail": ("trail.gpx", gpx_bytes, "application/gpx+xml"),
            "dem": ("dem.tif", dem_bytes, "image/tiff"),
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "summary" in body
    assert body["summary"]["num_segments"] == 2


def test_suggest_endpoint_end_to_end(tmp_path):
    dem_bytes = make_geotiff_bytes(tmp_path)
    start_lat, start_lon = latlon_for_xy(500025, 6599825)
    end_lat, end_lon = latlon_for_xy(500175, 6599975)

    res = client.post(
        "/api/suggest",
        files={"dem": ("dem.tif", dem_bytes, "image/tiff")},
        data={
            "start_lat": start_lat,
            "start_lon": start_lon,
            "end_lat": end_lat,
            "end_lon": end_lon,
            "trail_type": "flow",
            "target_grade_pct": 6.0,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["route"]["type"] == "LineString"
    assert len(body["points"]) >= 2
    assert "analysis" in body


def test_terrain_grid_endpoint_end_to_end(tmp_path):
    dem_bytes = make_geotiff_bytes(tmp_path)

    res = client.post(
        "/api/dem/terrain-grid",
        files={"dem": ("dem.tif", dem_bytes, "image/tiff")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["rows"] > 0
    assert body["cols"] > 0
    assert len(body["elevations"]) == body["rows"]
    assert len(body["elevations"][0]) == body["cols"]
    assert "origin_x_m" in body and "origin_y_m" in body


def test_analyze_rejects_bad_gpx():
    res = client.post(
        "/api/analyze",
        files={
            "trail": ("trail.gpx", b"not a gpx file", "application/gpx+xml"),
            "dem": ("dem.tif", b"not a tiff either", "image/tiff"),
        },
    )
    assert res.status_code == 400


def test_dem_fetch_endpoint_success(monkeypatch):
    async def fake_fetch(min_lat, min_lon, max_lat, max_lon, resolution_m=10.0):
        assert (min_lat, min_lon, max_lat, max_lon) == (59.9, 10.7, 59.91, 10.72)
        return b"FAKE-TIFF"

    monkeypatch.setattr("app.main.fetch_dem_geotiff", fake_fetch)

    res = client.post(
        "/api/dem/fetch",
        data={"min_lat": 59.9, "min_lon": 10.7, "max_lat": 59.91, "max_lon": 10.72},
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "image/tiff"
    assert res.content == b"FAKE-TIFF"


def test_dem_fetch_endpoint_maps_error_to_502(monkeypatch):
    from app.dem_fetch import DemFetchError

    async def fake_fetch(*args, **kwargs):
        raise DemFetchError("området er for stort")

    monkeypatch.setattr("app.main.fetch_dem_geotiff", fake_fetch)

    res = client.post(
        "/api/dem/fetch",
        data={"min_lat": 59.0, "min_lon": 10.0, "max_lat": 61.0, "max_lon": 12.0},
    )
    assert res.status_code == 502
    assert "for stort" in res.json()["detail"]
