# Sti-prosjekt-tool

Verktøy for å analysere en foreslått eller eksisterende sykkelsti (terrengsykkel /
flytsti) opp mot anerkjent beste praksis for bærekraftig stibygging, basert på
høydedata (DEM).

## Hva verktøyet gjør

Verktøyet har to modus:

### 1. Vurder en gitt trasé

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

### 2. Foreslå en ny trasé mellom to punkter

Du laster opp en høydemodell og velger et start- og sluttpunkt (klikk i
kartet, eller `start_lat/start_lon/end_lat/end_lon` mot API-et direkte).
Verktøyet søker etter den linjen gjennom terrenget som gir lavest "kostnad",
der kostnaden straffer:

- Avvik fra ønsket helning (flytsti: jevn helning rundt et mål, f.eks. 6 %;
  terrengsykkelsti: alt over maksgrensen straffes progressivt)
- Å følge fallinjen tett (oppmuntrer til at traséen legges mer på tvers av
  hellingen – konturering)
- Half Rule-brudd (stigrad i forhold til sidehelling)
- Reiseavstand (for å unngå unødvendige omveier)

Søket er implementert som A* over DEM-rutenettet (8-naboer). Den foreslåtte
traséen kjøres automatisk gjennom samme analyse som modus 1, slik at du
umiddelbart ser gjenværende funn/score for forslaget.

**Dette er et heuristisk startforslag, ikke en ferdig prosjektert trasé.**
Grid-baserte snarveier kan gi noe "hakkete" linjeføring, og resultatet må
alltid kontrolleres i felt og av fagkyndig før bygging.

Referansegrunnlag: IMBA Trail Solutions (2004) sine prinsipper for
bærekraftig stibygging ("Half Rule", "Ten Percent Guideline",
"Grade Reversals", "Avoid the Fall Line"), tilpasset for sykkelsti-/
flytsti-kontekst. Dette er **veiledende terskler**, ikke en offisiell norsk
standard — juster konstantene i `backend/app/analysis.py` og
`backend/app/routing.py` etter lokale forhold og eventuelt gjeldende
retningslinjer (f.eks. fra kommune/grunneier/NOTS).

## Arkitektur

```
backend/    FastAPI-tjeneste som gjør selve geodata-analysen
  app/
    main.py             API: POST /api/analyze, POST /api/suggest
    gpx_io.py            Parsing av GPX/GeoJSON til punktliste
    dem.py               Lesing/sampling av DEM (høyde + terrenggradient)
    terrain_metrics.py   Delt vektorgeometri (sidehelling, fall-line-vinkel)
    analysis.py          Vurder gitt trasé: half-rule, helning, reversals
    routing.py           Foreslå ny trasé: A*-søk med samme kostnadsprinsipper
    schemas.py           Pydantic-modeller for /api/analyze-respons
  tests/
    test_analysis.py  Enhetstester for trasé-vurdering (syntetisk DEM)
    test_routing.py   Enhetstester for trasé-forslag (syntetisk DEM)
    test_api.py       Integrasjonstester av begge endepunktene (ekte GeoTIFF)

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

- Trasé-forslaget er et grid-basert A*-søk – det gir en heuristisk linje,
  ikke en ferdig prosjektert trasé, og bør etterbehandles/kontrolleres i
  felt (og evt. glattes) før bygging.
- For store DEM-er (mer enn ca. 400×400 celler) avvises forslag-søket med en
  feilmelding – beskjær DEM til analyseområdet først.
- DEM må være i et projisert CRS i meter (f.eks. UTM). Geografisk DEM
  (grader) støttes ikke ennå.
- Ingen automatisk henting fra hoydedata.no/OSM ennå — bruker laster opp
  filer selv. Dette unngår avhengighet av eksterne API-nøkler/rate-limits i
  MVP, men kan legges til som eget datalag senere.
- Vegetasjon, verneområder og våtmark (arealtype) er ikke del av analysen
  ennå — kun terrenggeometri.
