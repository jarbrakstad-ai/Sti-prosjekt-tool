# Sti-prosjekt-tool

Verktøy for å analysere en foreslått eller eksisterende sykkelsti (terrengsykkel /
flytsti) opp mot anerkjent beste praksis for bærekraftig stibygging, basert på
høydedata (DEM).

## Hva verktøyet gjør

Verktøyet har to modus:

### 0. Høydedata (DEM) – opplasting eller automatisk henting

Begge modiene under trenger en høydemodell (DEM). Du kan enten:
- **Laste opp** en GeoTIFF DEM selv (projisert CRS i meter, f.eks. UTM33N — kan
  lastes ned manuelt fra [hoydedata.no](https://hoydedata.no)), eller
- **Hente den automatisk**: panorer/zoom kartet til ønsket område og trykk
  "Hent høydedata for kartutsnittet". Backend henter da en GeoTIFF fra
  Kartverkets WCS-tjeneste (nasjonal høydemodell) for akkurat det synlige
  kartutsnittet, i valgt oppløsning (standard 10 m/piksel). Praktisk for raskt
  å komme i gang uten å måtte finne/laste ned data manuelt først.

  **Begrensning:** kartutsnittet må være rimelig lite (maks ca. 600×600 piksler
  ved valgt oppløsning) – zoom inn til området du faktisk vil analysere. Denne
  integrasjonen dekker kun Norge (Kartverkets data), og WCS-endepunktet/
  dekningsnavnet i `backend/app/dem_fetch.py` er satt opp etter beste
  kjennskap men ikke verifisert mot en live respons i utviklingsmiljøet (se
  forbehold i modulens docstring) – juster der ved behov. Manuell opplasting
  fungerer uavhengig av dette.

### 1. Vurder en gitt trasé

Du laster opp:
1. En **tras**é som GPX-spor eller GeoJSON `LineString`
2. En høydemodell, se punkt 0 over

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

Både denne modusen og trasé-forslag under viser en **liste over GPS-punkter**
(lat/lon, høyde, avstand fra start) for hvert punkt langs traséen – i en
tabell på siden og som nummererte punkter i kartet – slik at du kan ta med
koordinatene ut i felt for å gå opp/kontrollere linjen. Traséen kan også
lastes ned direkte som **GPX** eller **GeoJSON** for bruk i en GPS-enhet
eller turapp.

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
- Brå retningsskift (straffer sikksakk, oppmuntrer til jevn flyt-rytme)
- Reiseavstand (for å unngå unødvendige omveier)

Søket er implementert som A* over DEM-rutenettet med 16 retninger (8 vanlige
naboer + 8 "springer"-trekk) for finere vinkeloppløsning enn et rent 8-nabo-
gitter. Den rå gitterruten glattes deretter med Chaikins hjørnekutting for en
mer flytvennlig linje – med en sikkerhetssjekk: siden glatting er ren
geometri og ikke kjenner til terrenget, kan den i prinsippet kutte hjørner inn
i terreng søket egentlig unngikk (f.eks. rundt en bratt kant). Hvis glattingen
gjør maks helning vesentlig verre enn den ujevnede ruten, forkastes glattingen
og du får den ujevnede (men terreng-sikre) ruten i stedet (`search_stats.smoothed`
i responsen forteller hvilken som ble brukt). Traséen kjøres automatisk gjennom
samme analyse som modus 1, slik at du umiddelbart ser gjenværende funn/score
for forslaget, og kan lastes ned som GPX eller GeoJSON fra nettsiden.

**Dette er et heuristisk startforslag, ikke en ferdig prosjektert trasé.**
Resultatet må alltid kontrolleres i felt og av fagkyndig før bygging.

Referansegrunnlag: IMBA Trail Solutions (2004) sine prinsipper for
bærekraftig stibygging ("Half Rule", "Ten Percent Guideline",
"Grade Reversals", "Avoid the Fall Line"), tilpasset for sykkelsti-/
flytsti-kontekst. Dette er **veiledende terskler**, ikke en offisiell norsk
standard — juster konstantene i `backend/app/analysis.py` og
`backend/app/routing.py` etter lokale forhold og eventuelt gjeldende
retningslinjer (f.eks. fra kommune/grunneier/NOTS).

## Driftsatt frontend (GitHub Pages)

`frontend/` er ren statisk HTML/JS/CSS og deployes automatisk til GitHub
Pages via `.github/workflows/deploy-pages.yml` ved push til `main` (og denne
grenen). **Merk:** GitHub Pages kan kun være vert for frontenden – backend-
API-et (FastAPI) må kjøre et annet sted (lokalt hos deg, eller på en tjeneste
som Render/Fly.io/en egen server), siden Pages bare serverer statiske filer.
Skriv adressen til din kjørende backend inn i "API-adresse"-feltet på siden.
Kjører backend lokalt på `http://localhost:8000`, fungerer det fint å peke dit
selv fra en `https://`-side, siden nettlesere regner `localhost` som en
"trygg" opprinnelse.

Første gang: workflowen krever at **GitHub Pages er skrudd på i repoet**
(Settings → Pages → "Build and deployment" → Source: **GitHub Actions**).
Dette er en engangs-innstilling som må gjøres av en med admin-tilgang til
repoet – selve deployen kjører deretter automatisk ved hver push.

## Arkitektur

```
backend/    FastAPI-tjeneste som gjør selve geodata-analysen
  app/
    main.py             API: POST /api/analyze, POST /api/suggest, POST /api/dem/fetch
    gpx_io.py            Parsing av GPX/GeoJSON til punktliste
    dem.py               Lesing/sampling av DEM (høyde + terrenggradient)
    dem_fetch.py          Automatisk henting av DEM fra Kartverkets WCS-tjeneste
    terrain_metrics.py   Delt vektorgeometri (sidehelling, fall-line-vinkel)
    analysis.py          Vurder gitt trasé: half-rule, helning, reversals
    routing.py           Foreslå ny trasé: A*-søk med samme kostnadsprinsipper
    schemas.py           Pydantic-modeller for /api/analyze-respons
  tests/
    test_analysis.py  Enhetstester for trasé-vurdering (syntetisk DEM)
    test_routing.py   Enhetstester for trasé-forslag (syntetisk DEM)
    test_dem_fetch.py Enhetstester for DEM-henting (mocket HTTP, ingen ekte kall)
    test_api.py       Integrasjonstester av alle endepunktene (ekte GeoTIFF / mock)

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
