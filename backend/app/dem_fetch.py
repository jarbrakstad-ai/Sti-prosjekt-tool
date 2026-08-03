"""Automatisk henting av høydedata (DEM) fra Kartverkets WCS-tjeneste (Geonorge),
som et alternativ til manuell nedlasting fra hoydedata.no + opplasting.

**OBS / viktig forbehold:** WCS-endepunktet og dekningsnavnet (`_COVERAGE_ID`) under
er satt opp etter beste kjennskap til Kartverkets nasjonale høydemodell-tjeneste på
tidspunktet dette ble skrevet. Det er **ikke verifisert mot en live respons** i denne
utviklingssesjonen, fordi utgående nettverk til eksterne vertsnavn var blokkert i
sandkassen koden ble utviklet i. Hvis henting feiler med en feilmelding om uventet
svar/format fra tjenesten, sjekk gjeldende GetCapabilities-dokument fra Kartverket
(se https://hoydedata.no eller https://kartkatalog.geonorge.no, søk etter
"WCS høydedata") og oppdater `_WCS_ENDPOINTS` / `_COVERAGE_ID` deretter. Manuell
opplasting av DEM (se dem.py) fungerer uavhengig av dette og er et trygt fallback.
"""
from __future__ import annotations

import httpx
from pyproj import Transformer

DEFAULT_RESOLUTION_M = 10.0
MAX_DIM_PX = 600
MIN_DIM_PX = 4


class DemFetchError(ValueError):
    pass


# EUREF89/UTM-soner Kartverket bruker for nasjonale datasett (32, 33, 35 -
# sone 34 hoppes normalt over i norske nasjonale datasett pga. overlapp).
_WCS_ENDPOINTS: dict[int, str] = {
    25832: "https://wcs.geonorge.no/skwms1/wcs.hoyde-dtm-nhm-25832",
    25833: "https://wcs.geonorge.no/skwms1/wcs.hoyde-dtm-nhm-25833",
    25835: "https://wcs.geonorge.no/skwms1/wcs.hoyde-dtm-nhm-25835",
}
_COVERAGE_ID = "nhm_dtm_25833"


def _choose_utm_epsg(center_lon: float) -> int:
    if center_lon < 12.0:
        return 25832
    if center_lon < 20.0:
        return 25833
    return 25835


def _project_bbox(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float, epsg: int
) -> tuple[float, float, float, float]:
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    minx, miny = transformer.transform(min_lon, min_lat)
    maxx, maxy = transformer.transform(max_lon, max_lat)
    return minx, miny, maxx, maxy


async def fetch_dem_geotiff(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    resolution_m: float = DEFAULT_RESOLUTION_M,
    client: httpx.AsyncClient | None = None,
) -> bytes:
    """Henter en GeoTIFF-høydemodell for det gitte lat/lon-kartutsnittet.

    Kaster DemFetchError med en brukervennlig forklaring hvis området er for
    stort/lite, eller hvis tjenesten svarer med noe annet enn en GeoTIFF.
    """
    if not (min_lat < max_lat and min_lon < max_lon):
        raise DemFetchError("Ugyldig kartutsnitt (min-verdier må være mindre enn maks-verdier).")
    if resolution_m <= 0:
        raise DemFetchError("Oppløsning må være et positivt tall (meter per piksel).")

    center_lon = (min_lon + max_lon) / 2.0
    epsg = _choose_utm_epsg(center_lon)
    endpoint = _WCS_ENDPOINTS[epsg]

    minx, miny, maxx, maxy = _project_bbox(min_lat, min_lon, max_lat, max_lon, epsg)

    width_px = int(round((maxx - minx) / resolution_m))
    height_px = int(round((maxy - miny) / resolution_m))

    if width_px < MIN_DIM_PX or height_px < MIN_DIM_PX:
        raise DemFetchError(
            "Kartutsnittet er for lite til automatisk henting – zoom litt ut, "
            "eller be om finere oppløsning (lavere resolution_m)."
        )
    if width_px > MAX_DIM_PX or height_px > MAX_DIM_PX:
        raise DemFetchError(
            f"Kartutsnittet er for stort for automatisk henting ved {resolution_m:.0f} m "
            f"oppløsning ({width_px}x{height_px} px, maks {MAX_DIM_PX}x{MAX_DIM_PX} px). "
            "Zoom inn til et mindre område, eller be om grovere oppløsning (høyere resolution_m)."
        )

    params = {
        "SERVICE": "WCS",
        "VERSION": "1.0.0",
        "REQUEST": "GetCoverage",
        "COVERAGE": _COVERAGE_ID,
        "CRS": f"EPSG:{epsg}",
        "BBOX": f"{minx},{miny},{maxx},{maxy}",
        "WIDTH": str(width_px),
        "HEIGHT": str(height_px),
        "FORMAT": "GeoTIFF",
    }

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)
    try:
        try:
            resp = await client.get(endpoint, params=params)
        except httpx.HTTPError as exc:
            raise DemFetchError(
                f"Klarte ikke å nå Kartverkets høydedata-tjeneste ({endpoint}): {exc}"
            ) from exc
    finally:
        if owns_client:
            await client.aclose()

    content_type = resp.headers.get("content-type", "")
    if resp.status_code != 200 or "tiff" not in content_type.lower():
        is_text = content_type.startswith("text") or "xml" in content_type.lower()
        snippet = resp.text[:2000] if is_text else "(binært svar, ikke TIFF)"
        raise DemFetchError(
            f"Høydedata-tjenesten svarte uventet (status {resp.status_code}, "
            f"content-type '{content_type or 'ukjent'}'): {snippet}"
        )

    return resp.content
