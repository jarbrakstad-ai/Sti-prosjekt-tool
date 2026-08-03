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
- **Hopplinje-muligheter**: sammenhengende, jevne nedoverbakke-partier (moderat
  helning, lite variasjon, lav sidehelling) der et hopp/tabletop kan få en
  naturlig landing i stedet for en flat/hard landing. Dette er en grov
  geometrisk heuristikk (helning + konsistens), **ikke** en fysisk
  hopp-/banesimulering – den tar ikke hensyn til innkjørselsfart, faktisk
  sprangvidde/trajectory eller sikt. Markeres med lilla stiplet linje i
  kartet og listes i rapporten; må detaljprosjekteres og kontrolleres i felt
  av kompetent hopplinje-/stibygger før bygging. Terskler kan justeres i
  `backend/app/jump_features.py`.
- **Svinger – dosering (berm)**: for hver sving skarpere enn en vinkelterskel
  anslås svingradius (fra punktgeometrien) og en anbefalt doseringsvinkel,
  basert på en antatt hastighet (justert noe opp for lokalt fallende terreng
  rundt svingen). Målet er jevn flyt gjennom svingen uten hard sidekraft eller
  behov for kraftig oppbremsing. Dette er en grov fysisk/geometrisk heuristikk
  (ikke en kjøredynamikk-simulering) – faktisk komfortabel dosering avhenger
  også av underlag, sikt og syklistens erfaring. Markeres som fargede punkter
  i kartet med anbefalt gradtall (turkis = normalt, rødt = vurder heller
  større svingradius enn enda brattere berm). Terskler/antatt fart kan
  justeres i `backend/app/corner_features.py`.

Både denne modusen og trasé-forslag under viser en **liste over GPS-punkter**
(lat/lon, høyde, avstand fra start) for hvert punkt langs traséen – i en
tabell på siden og som nummererte punkter i kartet – slik at du kan ta med
koordinatene ut i felt for å gå opp/kontrollere linjen. Traséen kan også
lastes ned direkte som **GPX** eller **GeoJSON** for bruk i en GPS-enhet
eller turapp.

### 2. Foreslå en ny trasé mellom to (eller flere) punkter

Du laster opp en høydemodell og velger et startpunkt og et sluttpunkt ved å
klikke i kartet. Du kan også klikke inn ett eller flere **mellompunkt**
mellom disse – nyttig for å styre hvilken retning traséen skal gå, f.eks. for
å holde seg innenfor en bestemt grunneiers areal eller unngå et areal du ikke
har avtale om. Klikkrekkefølgen blir rutepunktene i tur og orden (siste klikk
er alltid sluttpunktet); bruk "Angre siste punkt" eller "Nullstill punkter"
til å korrigere. Mot API-et sendes punktene som `waypoints_json`, en
JSON-liste med `[lat, lon]`-par (minst 2 – start og slutt).

Mellompunkt behandles som faste rutepunkt: A*-søket kjøres separat for hvert
delstrekk mellom to påfølgende punkter, og hvert delstrekk glattes for seg –
slik at et mellompunkt aldri flyttes av glattingen, uansett hvor mange
mellompunkt du legger inn.

Verktøyet søker etter den linjen gjennom terrenget som gir lavest "kostnad"
for hvert delstrekk, der kostnaden straffer:

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

### 3. Sammenlign flere alternativer

Etter en vellykket analyse/forslag kan du trykke **"Lagre som alternativ"**
for å legge resultatet til i en sammenligningstabell (lengde, snitt/maks
helning, bærekraft-score, antall hopplinje-/svingfunn). Hvert alternativ får
en egen farge og kan vises/skjules i kartet uavhengig av de andre, slik at
du kan sammenligne flere trasé-alternativer visuelt og tallmessig side om
side. Alternativene lagres i nettleserens `localStorage` – de er altså
knyttet til denne enheten/nettleseren og følger ikke automatisk med hvis du
bytter maskin eller sletter nettleserdata.

### 4. 3D-visning av trasé og terreng

Etter en vellykket analyse/forslag kan du trykke **"🏔️ Vis trasé i 3D"** for
å åpne en interaktiv 3D-visning (Three.js) av terrenget med traséen modellert
oppå – ikke bare som en tynn strek, men som et fysisk sti-bånd:

- **Reell bredde** (~1,2 m, typisk singletrack), fargekodet likt som
  2D-kartet (jordfarge for funn-frie partier, gul/rød ved funn).
- **Fysisk dosering i svinger**: der backend har beregnet en anbefalt
  berm-vinkel (se "Svinger – dosering" i analysen), helles sti-båndets
  tverrsnitt faktisk i 3D, med jevn opp-/nedramping inn og ut av svingen.
- **Stiliserte hopp-ramper**: ved hopplinje-mulighetene bygges en
  opptaksrampe (kicker) som løfter seg over terrenget, en luft-gap, og en
  landing som fortsetter ned den naturlige nedoverbakken.

Dra for å rotere, scroll for å zoome, og juster "Høyde-overdrivelse"-glideren
for å gjøre terrengformen tydeligere. Dette er en **stilisert visualisering**
av hvordan traséen kan se ut – ikke en presis fysisk simulering (spesielt
hopp-rampene er en forenklet representasjon, siden verktøyet ikke beregner
faktisk sprangvidde/trajectory).

Teknisk: et nytt endepunkt (`POST /api/dem/terrain-grid`) returnerer et
nedskalert høydegitter for den samme DEM-filen, i det samme lokale
koordinatsystemet (meter fra DEM-ens hjørne) som trasépunktenes `x_m`/`y_m`
i analyse-responsen – slik at terreng og trasé alltid stemmer geometrisk
overens, selv om de hentes i separate kall. Selve sti-båndet (bredde,
dosering, hopp-ramper) bygges helt i frontend (`buildTrailRibbon` i
`frontend/app.js`), siden all nødvendig geometri (posisjon, doserings-vinkel,
hopp-indekser) allerede følger med i analyse-responsen.

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

## Driftsatt backend (Render.com, gratis)

Repoet inneholder en `render.yaml` ("Blueprint") som lar Render sette opp
backend-tjenesten automatisk:

1. Opprett en konto på [render.com](https://render.com) (gratis, ingen
   kredittkort normalt nødvendig for gratis-tier – sjekk gjeldende vilkår).
2. Dashboard → **New** → **Blueprint**.
3. Koble til GitHub og velg dette repoet
   (`jarbrakstad-ai/Sti-prosjekt-tool`), grenen
   `claude/stisykling-trail-analysis-tool-gik9ya` (eller `main` når/hvis
   endringene er merget dit).
4. Render leser `render.yaml` og foreslår én tjeneste
   (`sti-prosjekt-tool-api`, gratis-plan) – trykk **Apply**/**Create**.
5. Vent til build/deploy er ferdig (kan ta noen minutter første gang), og
   kopier URL-en Render gir deg (noe sånt som
   `https://sti-prosjekt-tool-api.onrender.com`).
6. Lim inn URL-en i **"API-adresse"**-feltet på
   https://jarbrakstad-ai.github.io/Sti-prosjekt-tool/ – da fungerer siden
   helt uten noe lokalt.

**Verdt å vite om gratis-tieren på Render:** tjenesten "sovner" etter ca.
15 minutter uten trafikk, og det første kallet etterpå kan ta 30–60
sekunder mens den våkner igjen (påfølgende kall er raske). Dette er en
begrensning i gratis-tieren, ikke en feil i appen.

Første gang: workflowen krever at **GitHub Pages er skrudd på i repoet**
(Settings → Pages → "Build and deployment" → Source: **GitHub Actions**).
Dette er en engangs-innstilling som må gjøres av en med admin-tilgang til
repoet – selve deployen kjører deretter automatisk ved hver push.

## Arkitektur

```
backend/    FastAPI-tjeneste som gjør selve geodata-analysen
  app/
    main.py             API: POST /api/analyze, POST /api/suggest, POST /api/dem/fetch,
                        POST /api/dem/terrain-grid
    gpx_io.py            Parsing av GPX/GeoJSON til punktliste
    dem.py               Lesing/sampling av DEM (høyde + terrenggradient)
    dem_fetch.py          Automatisk henting av DEM fra Kartverkets WCS-tjeneste
    terrain_grid.py       Nedskalert høydegitter for 3D-visning (samme lokale koordinater som waypoints)
    terrain_metrics.py   Delt vektorgeometri (sidehelling, fall-line-vinkel)
    analysis.py          Vurder gitt trasé: half-rule, helning, reversals
    jump_features.py      Finner mulige hopplinje-partier (jevn nedoverbakke)
    corner_features.py    Anbefaler dosering (berm) for skarpe svinger
    routing.py           Foreslå ny trasé: A*-søk med samme kostnadsprinsipper
    schemas.py           Pydantic-modeller for /api/analyze-respons
  tests/
    test_analysis.py     Enhetstester for trasé-vurdering (syntetisk DEM)
    test_routing.py      Enhetstester for trasé-forslag (syntetisk DEM)
    test_dem_fetch.py     Enhetstester for DEM-henting (mocket HTTP, ingen ekte kall)
    test_terrain_grid.py  Enhetstester for 3D-terrenggitter + justering mot trasépunkter
    test_api.py           Integrasjonstester av alle endepunktene (ekte GeoTIFF / mock)

frontend/   Enkel statisk nettside (Leaflet-kart + Three.js for 3D-visning)
            som laster opp filer, kaller backend og visualiserer traséen
            fargekodet etter funn, i 2D og 3D.
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
