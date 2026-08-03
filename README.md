# Sti-prosjekt-tool

Verktøy for å analysere en foreslått eller eksisterende sykkelsti (terrengsykkel /
flytsti) opp mot anerkjent beste praksis for bærekraftig stibygging, basert på
høydedata (DEM).

## Hva verktøyet gjør (MVP)

Du laster opp:
1. En **tras**é som GPX-spor eller GeoJSON `LineString`
2. En **høydemodell** (GeoTIFF DEM, projisert CRS i meter, f.eks. UTM33N —
   kan lastes ned fra [hoydedata.no](https://hoydedata.no))

Verktøyet sampler terrenget langs og på tvers av traséen og rapporterer, per
segment og samlet:

- **Half Rule**: stiens helning bør ikke overstige ca. 50 % av sidehellingen
  (terrenghelningen på tvers av stien). Brytes denne, renner vann langs stien
  i stedet for av den → erosjon.
- **Maks/gjennomsnittlig helning**: gjennomsnittlig helning bør normalt holdes
  under ca. 10 %, med kortere partier opp til 15–20 % akseptabelt dersom det
  finnes drenering (grade reversals).
- **Fall-line-avvik**: hvor mye stiens retning avviker fra fallretningen
  (retning rett ned bakken). Sti som følger fallinjen for tett gir rask
  erosjon og er også dårlig for flyt/lesbarhet i sykkelsti-sammenheng.
- **Grade reversals**: naturlige "dip"-punkter (lokalt motfall) som drenerer
  vann av stien. Lange, sammenhengende fall uten reversal flagges.
- **Flyt-konsistens** (tillegg for flytstier): variasjon i helning over et
  glidende vindu — flytstier ønsker jevn, forutsigbar rytme fremfor brå
  skifter i gradient.

Referansegrunnlag: IMBA Trail Solutions (2004) sine prinsipper for
bærekraftig stibygging ("Half Rule", "Ten Percent Guideline",
"Grade Reversals", "Avoid the Fall Line"), tilpasset for sykkelsti-/
flytsti-kontekst. Dette er **veiledende terskler**, ikke en offisiell norsk
standard — juster konstantene i `backend/app/analysis.py` etter lokale forhold
og eventuelt gjeldende retningslinjer (f.eks. fra kommune/grunneier/NOTS).

## Arkitektur

```
backend/    FastAPI-tjeneste som gjør selve geodata-analysen
  app/
    main.py       API: POST /api/analyze
    gpx_io.py      Parsing av GPX/GeoJSON til punktliste
    dem.py         Lesing/sampling av DEM (høyde + terrenggradient)
    analysis.py    Kjernelogikk: half-rule, helning, fall-line, reversals
    schemas.py      Pydantic-modeller for request/response
  tests/
    test_analysis.py  Enhetstester med syntetisk DEM (ingen fil nødvendig)

frontend/   Enkel statisk nettside (Leaflet-kart) som laster opp filer,
            kaller backend og visualiserer traséen fargekodet etter funn.
```

## Kjøre lokalt

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend (statiske filer, kan åpnes direkte eller serves enkelt):

```bash
cd frontend
python -m http.server 5173
# åpne http://localhost:5173
```

Frontend forventer backend på `http://localhost:8000` (se `API_BASE` øverst i
`frontend/app.js`).

## Kjøre tester

```bash
cd backend
pip install -r requirements.txt
pytest
```

## Begrensninger / videre arbeid

- MVP evaluerer en **gitt** trasé. Automatisk *forslag* til ny trasé mellom
  to punkter (minste-kost-sti på helning/fallinje) er en naturlig
  videreføring, men ikke del av denne leveransen.
- DEM må være i et projisert CRS i meter (f.eks. UTM). Geografisk DEM
  (grader) støttes ikke ennå.
- Ingen automatisk henting fra hoydedata.no/OSM ennå — bruker laster opp
  filer selv. Dette unngår avhengighet av eksterne API-nøkler/rate-limits i
  MVP, men kan legges til som eget datalag senere.
- Vegetasjon, verneområder og våtmark (arealtype) er ikke del av analysen
  ennå — kun terrenggeometri.
