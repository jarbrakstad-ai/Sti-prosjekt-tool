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

**Om DEM-målestøy og stabilitet:** Høyoppløste DEM-er (spesielt ~1 m
LiDAR-avledede terrengmodeller) har typisk noen centimeters vertikal
usikkerhet per piksel. Rå punkt-til-punkt-gradient forsterker denne støyen
kraftig – noen få cm avvik over 1-2 m kan gi flere prosentpoeng falsk helning,
noe som tidligere kunne gi ustabile/fabrikkerte funn (f.eks. half-rule-brudd
eller brå helningsendringer som ikke er reelle) på en trasé som i
virkeligheten er en jevn skråning. Gradient/helnings-baserte vurderinger
(sidehelling, fall-line, langsgående helning) beregnes derfor fra et utjevnet
gitter (`DemSampler.grade_smoothing_radius_m`, standard 2 m) – kun virksomt
når DEM-oppløsningen er finere enn utjevningsradiusen, slik at grov-oppløste
DEM-er (5-10 m/piksel, allerede et romlig snitt) ikke påvirkes og ekte
stibygging-relevante trekk (f.eks. drenerende motfall hvert 15-50 m) ikke
viskes ut. Rapporterte punkthøyder (`elevation_m`) forblir upåvirket/rå.

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
flytsti-kontekst. De samme retningslinjene gjengis på norsk i
[NOTS (Norsk organisasjon for terrengsykling) sin Stibyggerhåndbok](https://www.nots.no/vart-arbeid/stibyggerhandboka/),
og terskelverdiene i koden er kryssjekket mot denne: halv-regelen (maks
stigning = halvparten av sidehelling), gjennomsnittlig stigning maks 10 %,
maks stigning under 15 % (med steinsetting/forsterkning anbefalt der
stigningen likevel må overgå 15 %). Dette er **veiledende terskler**, ikke en
offisiell norsk standard — juster konstantene i `backend/app/analysis.py` og
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

## Grøfteplanlegger (eksperimentell egen frontend, samme backend)

`frontend-grofting/` er en separat, ferdig ombygget frontend for et annet bruksområde:
å finne en fornuftig linje for en grøft/vannvei på et jorde (for å gjøre våt/dårlig
produserende mark tørrere), i stedet for sykkelsti. Den bruker **samme backend** (samme
`/api/suggest`/`/api/analyze` osv.) – bare med andre standardverdier (svakt ønsket fall,
typisk 0,5–1 % i stedet for 6 %), egen merkevare/tekst, og uten de sykkelsti-spesifikke
elementene (hopplinje, sving-dosering). Kjøres på samme måte:

```bash
cd frontend-grofting
python -m http.server 5174
# åpne http://localhost:5174
```

Rapporten viser, i tillegg til lengde/fall-sammendrag og GPS-punktliste:
- **Merknader**: enkle fall-baserte observasjoner (for slakt/bratt et sted).
- **Oppbyggingsforslag**: konkrete byggeråd ut fra
  [NLR (Norsk Landbruksrådgiving) sin veiledning om drenering og åpne kanaler](https://www.nlr.no/kunnskap/fagartikler/hydroteknikk/korn/drenering) -
  rørdimensjon (basert på traséens faktiske snittfall/lengde), grøftedybde,
  kapasitet, grøfteavstand, utløpsutforming og sidehelning i åpen kanal. Se
  `buildConstructionSuggestions()` i `frontend-grofting/app.js` for kildehenvisning
  og terskelverdier.
- **Profiltegning**: to skjematiske SVG-tverrsnitt (rørlagt grøft med filtermasse/rør,
  og åpen kanal med sidehelning) som visualiserer tallene over. Ikke i målestokk -
  viser prinsippet, ikke en byggeklar tegning. Sidehelningen i kanaltegningen kan
  justeres via jordart-nedtrekksmenyen i grensesnittet (leire/sand-silt/finsand).
  Se `buildProfileDrawing()` i `frontend-grofting/app.js`.

**Følg trasé i felt** ("📍 Følg trasé i felt"-knappen etter en analyse/forslag): åpner en
fullskjerms live-visning som bruker nettleserens posisjons-API
(`navigator.geolocation.watchPosition`) til å vise hvor du står i kartet i sanntid mens
du går ute på jordet, sammen med:
- Avstand fra deg til nærmeste punkt på traséen (til venstre/høyre)
- Fremdrift langs traséen (meter og prosent av total lengde)

Nyttig for å stikke ut/kontrollere den foreslåtte linja med mobilen i hånden, uten
GPS-enhet. Krever HTTPS (fungerer også på `localhost` ved lokal testing) og at du gir
nettleseren tilgang til posisjon. Se `nearestPointOnRoute()` i
`frontend-grofting/app.js` (planær meter-tilnærming, testet numerisk med kjente
avstander/retninger - ikke egnet for svært store avstander).

**Automatisk utløpspunkt**: kryss av "La algoritmen foreslå utløpspunkt automatisk"
under "Foreslå grøftetrasé" for å bare klikke ett startpunkt. Backend søker da
(med samme terrengfølgende A*-kostnadsfunksjon som ellers) mot det **laveste punktet
i kartutsnittet** som utløp - fysisk fornuftig siden vann uansett søker dit, men
DEM-en vet ingenting om hvor det faktisk finnes en bekk/kum/eksisterende grøft å
lede vannet til i virkeligheten. Svaret markeres med `search_stats.auto_endpoint: true`,
grensesnittet varsler tydelig og markerer utløpspunktet spesielt i kartet - **må
alltid bekreftes i felt før graving**. Se `_lowest_point_rc()` i `backend/app/routing.py`.
Fungerer likt i hoved-frontenden (`frontend/`) siden det er samme `/api/suggest`-endepunkt,
men er foreløpig kun eksponert i grensesnittet til Grøfteplanlegger.

### Analyse 2: Sjekk selvdrenering

Ny fane ("Sjekk selvdrenering") som svarer på et litt annet spørsmål enn "hvor bør jeg
grave": *trenger jordet grøft i det hele tatt, eller drenerer det av seg selv* pga.
naturlig fall i terrenget? Bruker samme DEM (hele det innlastede kartutsnittet - ingen
egen områdemarkering nødvendig) og finner **søkk/lavpunkter**: celler uten
sammenhengende nedadgående vei ut til kanten av det kartlagte området, der vann
realistisk vil bli stående.

Implementert med "priority-flood"-algoritmen (Barnes, Lehman & Mulla 2014, samme
prinsipp som WhiteboxTools/RichDEM sin "Fill Depressions") i
`backend/app/depressions.py` (`POST /api/dem/depressions`) - flommer terrenget innover
fra kanten av DEM-en og registrerer hvor mye hver celle måtte "fylles" for å få en
utløpsvei. Bruker DEM-ens utjevnede høydegitter (samme som gradient/helnings-
beregningene i analysis.py), ikke rådata - testet empirisk at rå punktvis DEM-målestøy
(noen cm/piksel) ellers ga hundrevis av falske mikro-søkk på reelt jevnt terreng
(729 falske søkk på en 200×200 DEM med 5 cm støy, mot 0 på utjevnet data).

Resultatet vises som fargede sirkler i kartet (størrelse = areal, farge = dybde) og en
liste sortert etter størst areal først. **Kjenner ikke til jordart/infiltrasjonsevne**,
som også avgjør om et areal faktisk drenerer selv - dette er en heuristisk indikasjon
basert kun på høydedata, ikke en fasit.

### Feltnotater (grunnforhold observert i felt)

Siden verktøyet ikke kjenner til grunnforhold (jordart, dybde til fjell osv.) fra
høydedata alene, kan du legge inn egne observasjoner **etter en faktisk befaring**:

- **"📝 Legg til feltnotat"**-knappen (nede til høyre på kartet, alle moduser) - klikk
  knappen, så et sted i kartet, og et lite skjema åpnes for kategori (fjell i
  dagen/stein, myr/våtmark, leire/tett jord, tørr/fast grunn, annet) og fritekst.
- **"📝 Notat her"** i "Følg trasé i felt"-visningen - registrerer notatet på din
  *nåværende GPS-posisjon* direkte mens du går befaringen, uten å måtte klikke i kartet.

Notatene lagres i nettleserens localStorage (samme mønster som "Sammenlign
alternativer" - følger ikke med hvis du bytter enhet/nettleser), vises som fargede
punkter i kartet (lag "Feltnotater (grunnforhold)"), og kan slettes fra egen popup.
Notatene er knyttet til *stedet*, ikke til én bestemt foreslått trasé, og vises uansett
hvilken modus/trasé du har lastet. Se `FIELD_NOTE_CATEGORIES`/`saveFieldNote()` i
`frontend-grofting/app.js`.

### Masseberegning

Egen seksjon i rapporten ("Masseberegning") som regner om traséens lengde til
gravevolum, i **fast masse** (volumet slik det ligger i bakken) og **løs masse**
(volumet etter oppgraving/lasting - det som faktisk avgjør antall lastebillass).
Beregnes for begge oppbyggingsvariantene fra profiltegningen:

- **Rørlagt grøft**: rektangulært tverrsnitt (bredde × dybde, justerbare inputfelt,
  standard 0,8 × 1,1 m) × traséens lengde.
- **Åpen kanal**: trapes-tverrsnitt (bunnbredde 0,4 m, dybde 0,8 m, sidehelning fra
  jordart-valget - samme tall som profiltegningen bruker).

**Type masse**-nedtrekksmenyen velger omregningsfaktor fast → løs masse: jord/sand/grus
(× 1,5), leire (× 1,3, mer usikker pga. vanninnholdsavhengighet), fjell/sprengstein
(× 2,0) - kilder: NVE Sikringshåndboka modul G2.001 og alminnelig anleggsteknisk
tommelfingerregel. Grovt overslag, ikke NS 3420-presist - egnet til å anslå
lastebilbehov/kostnadsstørrelsesorden, ikke som grunnlag for anbud. Se
`buildMassCalculation()`/`MASS_BULKING_FACTORS` i `frontend-grofting/app.js`
(regnestykket er verifisert numerisk mot håndberegnede tverrsnittsareal).

### Planering (areal-basert kutt/fyll)

Ny fane ("Planering (kutt/fyll)") som svarer på et annet spørsmål enn både
grøfteforslaget og selvdrenerings-sjekken: *hvor mye masse må flyttes for å gjøre hele
jordet flatt eller jevnt hellende* - polygon-/areal-basert i stedet for linje-basert.
Bruker hele det innlastede kartutsnittet (samme "ingen egen områdemarkering
nødvendig"-mønster som selvdrenerings-sjekken).

Metode (`backend/app/grading.py`, `POST /api/dem/grading`): minste kvadraters
plantilpasning (z = a·x + b·y + c) gjennom DEM-ens utjevnede høydegitter. En slik
tilpasning har en nyttig matematisk egenskap: gjennomsnittlig avvik fra terrenget er
alltid null når skjæringspunktet c er fritt valgt, som betyr at **kuttet volum alltid
balanserer eksakt mot fylt volum** - verifisert som en eksplisitt invariant i testene
(`test_cut_always_balances_fill_by_construction`), både for terrengets naturlige
helning og for en påtvunget mål-helning (flatt eller en spesifikk %). For en ønsket
helningsgrad beholdes terrengets egen naturlige helningsretning, men størrelsen
skaleres til ønsket verdi og skjæringspunktet beregnes på nytt for fortsatt å
balansere kutt/fylling.

Resultatet vises som et fargelagt gitter i kartet (rødt = kutt/skjæring, blått =
fylling, styrke = mengde) og en rapport med kuttet/fylt volum i fast masse, pluss løs
masse (samme "type masse"-omregningsfaktor som i grøfte-masseberegningen over) for å
anslå maskin-/lastebilbehov ved å flytte massene internt på jordet. Ytelse målt:
~0,5 s for 1 000×1 000 celler (mye billigere enn både A*-ruteforslaget og
søkk-deteksjonen).

**Grov overslagsberegning, ikke en byggeklar planeringsplan**: kjenner ikke til
jordart/bæreevne, tar ikke hensyn til hindringer (bygninger, trær, stein) i arealet,
og forutsetter at all kuttet masse gjenbrukes som fylling internt på stedet (ikke
kjørt bort/inn).

Status: **idé-/valideringsstadiet**, ikke produksjonsklar. Noen kjente begrensninger:
- Analysen bruker fortsatt sykkelsti-terskelverdiene i `backend/app/analysis.py`
  (half-rule, fall-line) under panseret – de vises ikke i denne frontenden, men er
  heller ikke erstattet med noe drenerings-spesifikt ennå. Grensesnittet viser i
  stedet enkle, egne fall-baserte merknader (se `TOO_FLAT_PCT`/`STEEP_WARN_PCT`/
  `STEEP_BAD_PCT` i `frontend-grofting/app.js`) – grove tommelfingerregler, ikke
  autoritative ingeniørverdier.
- Oppbyggingsforslagene mangler areal/nedbørsfelt (kapasitet) og jordart
  (grøfteavstand, sidehelning, rørdimensjon) som egne datainnhentinger – disse
  vises som generell referanseinfo, ikke beregnet spesifikt for ditt jorde.
- Tar **ikke hensyn til grunnforhold** (jordart, dybde til fjell) – kun høydedata.
  Et NIBIO jordsmonnkart-lag (WMS) er lagt til som eksperimentelt kartlag
  (`layer-jordsmonn`), men det nøyaktige WMS-lagnavnet er ikke verifisert mot en
  live GetCapabilities-respons (blokkert i utviklingsmiljøet her) – sjekk
  `https://wms.nibio.no/cgi-bin/jordsmonn?service=WMS&request=GetCapabilities`
  og juster `layers`-parameteren i `frontend-grofting/app.js` ved behov. NIBIOs
  jordsmonnkart dekker uansett bare deler av Norge (mest Østlandet, Trøndelag, Jæren).

## Kjøre tester

```bash
cd backend
pip install -r requirements.txt
pytest
```

## Begrensninger / videre arbeid

- Trasé-forslaget er et grid-basert A*-søk – det gir en heuristisk linje,
  ikke en ferdig prosjektert trasé, og bør etterbehandles/kontrolleres i
  felt (og evt. glattes) før bygging. Søket bruker en retnings-bevisst
  A*-tilstand (16 innkommende retninger pr. celle) for å unngå unødvendige
  omveier/sikksakk som en enklere (rad, kolonne)-tilstand kan gi. Rene
  selv-krysninger (der ruten sveiper rundt en kolle og skjærer sin egen
  tidligere strekning) fjernes automatisk. Ved flere rutepunkter kan to
  delstrekk i sjeldne tilfeller likevel møtes/krysse akkurat ved et
  mellompunkt der terrenget tvinger begge delstrekk gjennom samme smale
  korridor – siden mellompunktet er obligatorisk og aldri flyttes, er ikke
  dette alltid løsbart uten å velge et annet mellompunkt.
  `search_stats.self_intersects` i API-svaret forteller om dette har skjedd.
- For store DEM-er (mer enn ca. 400×400 celler) avvises forslag-søket med en
  feilmelding – beskjær DEM til analyseområdet først. Den retnings-bevisste
  A*-tilstanden er tyngre pr. celle enn en enkel (rad, kolonne)-tilstand, så
  et søk nær denne grensen kan ta i overkant av to minutter (målt: ~150 s for
  et hjørne-til-hjørne-søk over 380×380 celler). Sett `max_grid_nodes` lavere
  i `backend/app/routing.py` (`RouteOptions`) hvis du heller vil prioritere
  responstid over å kunne foreslå trasé over et større område. Vær også obs
  på at enkelte gratis hosting-plattformer (bl.a. Render sin gratis-plan) kan
  ha en egen forespørsel-timeout (typisk i størrelsesorden 30–100 sekunder)
  som kan kutte et søk nær maksgrensen før det er ferdig – test gjerne mot et
  realistisk stort område etter deploy.
- DEM må være i et projisert CRS i meter (f.eks. UTM). Geografisk DEM
  (grader) støttes ikke ennå.
- Ingen automatisk henting fra hoydedata.no/OSM ennå — bruker laster opp
  filer selv. Dette unngår avhengighet av eksterne API-nøkler/rate-limits i
  MVP, men kan legges til som eget datalag senere.
- Vegetasjon, verneområder og våtmark (arealtype) er ikke del av analysen
  ennå — kun terrenggeometri.
