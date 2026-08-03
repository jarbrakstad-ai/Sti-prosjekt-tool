"""Tester for automatisk DEM-henting fra Kartverkets WCS-tjeneste.

Bruker httpx.MockTransport slik at ingen ekte nettverkskall gjøres - vi
verifiserer at vi bygger riktig forespørsel og håndterer svar/feil riktig,
uavhengig av om selve Kartverket-endepunktet er nådbart fra testmiljøet.
"""
from __future__ import annotations

import httpx
import pytest

from app.dem_fetch import DemFetchError, _choose_utm_epsg, fetch_dem_geotiff


def test_choose_utm_epsg():
    assert _choose_utm_epsg(6.0) == 25832
    assert _choose_utm_epsg(11.9) == 25832
    assert _choose_utm_epsg(12.0) == 25833
    assert _choose_utm_epsg(15.0) == 25833
    assert _choose_utm_epsg(20.0) == 25835
    assert _choose_utm_epsg(28.0) == 25835


@pytest.mark.asyncio
async def test_area_too_large_raises_without_network():
    with pytest.raises(DemFetchError, match="for stort"):
        await fetch_dem_geotiff(59.0, 10.0, 61.0, 12.0, resolution_m=10.0)


@pytest.mark.asyncio
async def test_area_too_small_raises_without_network():
    with pytest.raises(DemFetchError, match="for lite"):
        await fetch_dem_geotiff(59.0000, 10.0000, 59.00001, 10.00001, resolution_m=10.0)


@pytest.mark.asyncio
async def test_invalid_bbox_raises():
    with pytest.raises(DemFetchError, match="Ugyldig kartutsnitt"):
        await fetch_dem_geotiff(60.0, 10.0, 59.0, 10.1)


@pytest.mark.asyncio
async def test_successful_fetch_returns_bytes_and_builds_expected_request():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url
        return httpx.Response(200, content=b"FAKE-TIFF-BYTES", headers={"content-type": "image/tiff"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await fetch_dem_geotiff(59.90, 10.70, 59.91, 10.72, resolution_m=10.0, client=client)

    assert result == b"FAKE-TIFF-BYTES"
    params = dict(captured["url"].params)
    assert params["SERVICE"] == "WCS"
    assert params["REQUEST"] == "GetCoverage"
    assert params["CRS"] == "EPSG:25832"  # senter-lengdegrad 10.71 -> sone 32
    assert params["FORMAT"] == "GeoTIFF"
    assert "BBOX" in params


@pytest.mark.asyncio
async def test_unexpected_response_raises_dem_fetch_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            content=b"<ServiceExceptionReport>bad request</ServiceExceptionReport>",
            headers={"content-type": "application/vnd.ogc.se_xml"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(DemFetchError, match="uventet"):
        await fetch_dem_geotiff(59.90, 10.70, 59.91, 10.72, resolution_m=10.0, client=client)
