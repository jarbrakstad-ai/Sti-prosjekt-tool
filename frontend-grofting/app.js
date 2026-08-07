// Grade-bånd tilpasset en gravd grøft/vannvei (ikke sykkelsti) - egne,
// grovere tommelfingerregler enn stibygging-tersklene i backend, siden
// bekymringen her er "renner vannet i det hele tatt" og "graver grøfta seg
// ned", ikke sti-erosjon/fall-line/half-rule (som ikke er direkte
// overførbart til en tiltenkt vannvei). Ikke autoritative ingeniørverdier -
// et startpunkt for videre vurdering, se hint i grensesnittet.
const TOO_FLAT_PCT = 0.3;
const STEEP_WARN_PCT = 5.0;
const STEEP_BAD_PCT = 10.0;

// Rørdimensjonerings-terskler fra NLR (Norsk Landbruksrådgiving) sin
// veiledning om drenering: https://www.nlr.no/kunnskap/fagartikler/hydroteknikk/korn/drenering
// - Standard er Ø60/50 mm sugegrøft / Ø100/83 mm samlegrøft.
// - Under 0,33 % fall: øk til Ø110/97 mm i sugegrøft.
// - Under 0,25 % fall: øk dimensjonen ytterligere.
// - Under 0,5 % fall, eller lengde over 200 m: vurder oppgradert dimensjon uansett.
const PIPE_UPSIZE_PCT_A = 0.33;
const PIPE_UPSIZE_PCT_B = 0.25;
const PIPE_UPSIZE_CAUTION_PCT = 0.5;
const PIPE_UPSIZE_LENGTH_M = 200;

function gradeSeverity(gradePct) {
  const g = Math.abs(gradePct);
  if (g < TOO_FLAT_PCT) return "warn"; // kan bli stående vann
  if (g > STEEP_BAD_PCT) return "bad"; // høy erosjonsrisiko
  if (g > STEEP_WARN_PCT) return "warn";
  return "ok";
}

const map = L.map("map").setView([61.0, 9.0], 6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap-bidragsytere",
  maxZoom: 19,
}).addTo(map);

// NIBIO jordsmonnkart (WMS) - eksperimentelt lag, se hint i grensesnittet.
// Lagnavnet er ikke verifisert mot en live GetCapabilities-respons; sjekk
// https://wms.nibio.no/cgi-bin/jordsmonn?service=WMS&request=GetCapabilities
// og juster `layers` under om laget ikke vises riktig.
const jordsmonnLayer = L.tileLayer.wms("https://wms.nibio.no/cgi-bin/jordsmonn", {
  layers: "jordsmonn",
  format: "image/png",
  transparent: true,
  opacity: 0.6,
  attribution: "&copy; NIBIO",
});

window.addEventListener("resize", () => map.invalidateSize());
window.addEventListener("orientationchange", () => setTimeout(() => map.invalidateSize(), 200));

// Egne lag per informasjonstype, slik at de kan skrus av/på uavhengig
// (se "Vis i kart"-panelet) i stedet for å presse alt oppå hverandre.
const trailLineLayer = L.layerGroup().addTo(map);
const trailLabelLayer = L.layerGroup(); // av som standard - kan bli tett ved mange segmenter
const markerLayer = L.layerGroup().addTo(map);
const waypointLayer = L.layerGroup(); // av som standard
const compareLayer = L.layerGroup().addTo(map);
const depressionLayer = L.layerGroup().addTo(map);

const LAYER_BY_CHECKBOX = {
  "layer-trail-lines": trailLineLayer,
  "layer-segment-labels": trailLabelLayer,
  "layer-waypoints": waypointLayer,
  "layer-compare": compareLayer,
  "layer-jordsmonn": jordsmonnLayer,
  "layer-depressions": depressionLayer,
};

for (const [checkboxId, layer] of Object.entries(LAYER_BY_CHECKBOX)) {
  const checkbox = document.getElementById(checkboxId);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) map.addLayer(layer);
    else map.removeLayer(layer);
  });
}

document.getElementById("layer-jordsmonn").addEventListener("change", (e) => {
  document.getElementById("jordsmonn-hint").hidden = !e.target.checked;
});

function severityColor(sev) {
  return { ok: "#2e7d32", warn: "#f9a825", bad: "#c62828" }[sev];
}

function segmentNote(seg) {
  const g = Math.abs(seg.grade_pct);
  if (g < TOO_FLAT_PCT) return "For slakt - vann kan bli stående her.";
  if (g > STEEP_BAD_PCT) return "Bratt - høy erosjonsrisiko, vurder steinsetting/forsterkning.";
  if (g > STEEP_WARN_PCT) return "Noe bratt - hold et øye med erosjon over tid.";
  return "Greit fall.";
}

function segmentMidpoint(seg) {
  return [(seg.start[0] + seg.end[0]) / 2, (seg.start[1] + seg.end[1]) / 2];
}

function renderMap(segments) {
  trailLineLayer.clearLayers();
  trailLabelLayer.clearLayers();
  const bounds = [];
  for (const seg of segments) {
    const sev = gradeSeverity(seg.grade_pct);
    const latlngs = [seg.start, seg.end];
    const color = severityColor(sev);
    const popupHtml = `Segment ${seg.index}: ${seg.length_m} m, fall ${seg.grade_pct}%<br>${segmentNote(seg)}`;

    L.polyline(latlngs, { color, weight: 5 }).addTo(trailLineLayer).bindPopup(popupHtml);

    L.marker(segmentMidpoint(seg), {
      icon: L.divIcon({
        className: `seg-label sev-${sev}`,
        html: `<span style="background:${color}">#${seg.index} ${seg.grade_pct}%</span>`,
        iconSize: null,
      }),
      interactive: true,
    })
      .addTo(trailLabelLayer)
      .bindPopup(popupHtml);

    bounds.push(latlngs[0], latlngs[1]);
  }
  if (bounds.length) map.fitBounds(bounds, { padding: [20, 20] });
}

const MAX_WAYPOINT_ROWS = 500;

function renderWaypointsTable(waypoints) {
  const shown = waypoints.slice(0, MAX_WAYPOINT_ROWS);
  const rows = shown
    .map(
      (w) =>
        `<tr><td>${w.index}</td><td>${w.lat.toFixed(6)}</td><td>${w.lon.toFixed(6)}</td>` +
        `<td>${w.elevation_m.toFixed(1)}</td><td>${w.distance_from_start_m.toFixed(0)}</td></tr>`
    )
    .join("");
  const truncatedNote =
    waypoints.length > MAX_WAYPOINT_ROWS
      ? `<p class="hint">Viser de første ${MAX_WAYPOINT_ROWS} av ${waypoints.length} punkter. Last ned GPX/GeoJSON for hele traséen.</p>`
      : "";
  return `
    <h2>GPS-punkter (${waypoints.length})</h2>
    <p class="hint">Punktene er også markert i kartet. Bruk disse i felt, eller last ned som GPX/GeoJSON under.</p>
    <div class="waypoints-table">
      <table>
        <thead><tr><th>#</th><th>Lat</th><th>Lon</th><th>Høyde (m)</th><th>Dist. (m)</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    ${truncatedNote}
  `;
}

function renderWaypointMarkers(waypoints) {
  waypointLayer.clearLayers();
  const stride = Math.max(1, Math.ceil(waypoints.length / 150));
  waypoints.forEach((w, i) => {
    if (i % stride !== 0 && i !== waypoints.length - 1) return;
    L.circleMarker([w.lat, w.lon], {
      radius: 4,
      color: "#1565c0",
      fillColor: "#1565c0",
      fillOpacity: 0.9,
      weight: 1,
    })
      .addTo(waypointLayer)
      .bindPopup(`Punkt ${w.index}: ${w.lat.toFixed(6)}, ${w.lon.toFixed(6)}<br>Høyde: ${w.elevation_m} m<br>Distanse: ${w.distance_from_start_m} m`);
  });
}

/** Enkle, rene tekstnotater ut fra fallprosent - ikke fra backendens
 * sti-spesifikke flagg (half-rule/fall-line/hopplinje osv. er ikke direkte
 * overførbart til en tiltenkt vannvei/grøft, så vi bruker egne grade-bånd
 * i stedet, se TOO_FLAT_PCT/STEEP_WARN_PCT/STEEP_BAD_PCT over). */
function buildDrainageNotes(segments) {
  const tooFlat = segments.filter((s) => Math.abs(s.grade_pct) < TOO_FLAT_PCT);
  const steep = segments.filter((s) => Math.abs(s.grade_pct) > STEEP_WARN_PCT && Math.abs(s.grade_pct) <= STEEP_BAD_PCT);
  const verysteep = segments.filter((s) => Math.abs(s.grade_pct) > STEEP_BAD_PCT);
  const notes = [];
  if (tooFlat.length) {
    const len = tooFlat.reduce((a, s) => a + s.length_m, 0);
    notes.push(`${len.toFixed(0)} m av traséen har for slakt fall (under ${TOO_FLAT_PCT} %) - vann kan bli stående/gjørmete her.`);
  }
  if (steep.length) {
    const len = steep.reduce((a, s) => a + s.length_m, 0);
    notes.push(`${len.toFixed(0)} m har noe bratt fall (${STEEP_WARN_PCT}–${STEEP_BAD_PCT} %) - hold et øye med erosjon over tid.`);
  }
  if (verysteep.length) {
    const len = verysteep.reduce((a, s) => a + s.length_m, 0);
    notes.push(`${len.toFixed(0)} m har svært bratt fall (over ${STEEP_BAD_PCT} %) - høy erosjonsrisiko, vurder steinsetting/forsterkning eller trinnvis fall.`);
  }
  if (notes.length === 0) {
    notes.push("Jevnt, moderat fall langs hele traséen ut fra høydedataene.");
  }
  return notes;
}

/** Konkrete oppbyggingsforslag ut fra beste praksis for norsk jordbruksdrenering
 * (NLR - Norsk Landbruksrådgiving), tilpasset traséens faktiske fallprofil.
 * Kilder: nlr.no/kunnskap/fagartikler/hydroteknikk (drenering, avskjæringsgrøfter
 * og åpne kanaler). Grove tommelfingerregler for et startpunkt - endelig
 * dimensjonering bør gjøres av NLR/fagperson, spesielt for nedbørsfelt-areal
 * (kapasitet) og jordart (grøfteavstand, sidehelning), som dette verktøyet
 * ikke kjenner til. */
function buildConstructionSuggestions(summary) {
  const avgGrade = Math.abs(summary.avg_grade_pct);
  const suggestions = [];

  if (avgGrade < PIPE_UPSIZE_PCT_B) {
    suggestions.push(
      `Snittfallet (${summary.avg_grade_pct} %) er under ${PIPE_UPSIZE_PCT_B} % - vurder en grovere rørdimensjon ` +
        "enn standard Ø60/50 mm sugegrøft/Ø100/83 mm samlegrøft for å unngå gjengroing/sedimentering."
    );
  } else if (avgGrade < PIPE_UPSIZE_PCT_A) {
    suggestions.push(
      `Snittfallet (${summary.avg_grade_pct} %) er under ${PIPE_UPSIZE_PCT_A} % - vurder å øke til Ø110/97 mm i sugegrøft ` +
        "fremfor standarddimensjon."
    );
  }
  if (avgGrade < PIPE_UPSIZE_CAUTION_PCT || summary.total_length_m > PIPE_UPSIZE_LENGTH_M) {
    suggestions.push(
      `Lavt fall og/eller lang trasé (${summary.total_length_m} m, grense ${PIPE_UPSIZE_LENGTH_M} m) - vurder oppgradert ` +
        "rørdimensjon uansett, og planlegg for jevnlig spyling/vedlikehold."
    );
  }
  suggestions.push(
    "Grøftedybde: vanlig praksis er 1,0–1,2 m til drensrør (med filtermasse rundt røret)."
  );
  suggestions.push(
    "Kapasitet: dimensjoner grøfta for ca. 1–1,5 l/sek. pr. hektar nedbørsfelt (avhenger av areal - " +
      "ikke beregnet av dette verktøyet)."
  );
  suggestions.push(
    "Grøfteavstand mellom parallelle sugegrøfter (for hele jordet, ikke bare denne linja): typisk 6–8 m på tett/leirholdig " +
      "jord, opp mot 20–25 m på grus - avhenger av jordart (se ev. jordsmonn-laget i kartet)."
  );
  suggestions.push(
    "Utløp: rør som munner i åpen kanal/bekk bør stikke 30–40 cm ut i kanalen, gjerne slik at vannet treffer vannspeilet - " +
      "hindrer graving/erosjon ved utløpet."
  );
  suggestions.push(
    "Åpen kanal (ikke rørlagt): sidehelning bør være slakere enn ca. 1:1,25 på leire, 1:1,5 på sand/silt og 1:2,0 på finsand."
  );
  return suggestions;
}

const SIDE_SLOPE_RATIO_BY_JORDART = { leire: 1.25, sand_silt: 1.5, finsand: 2.0 };
const SIDE_SLOPE_LABEL_BY_JORDART = { leire: "leire", sand_silt: "sand/silt", finsand: "finsand" };

/** Skjematisk profiltegning (SVG) av grøfteoppbygging - IKKE i målestokk,
 * kun til å visualisere prinsippet og de faktiske tallene fra
 * buildConstructionSuggestions. To varianter tegnes: rørlagt grøft (med
 * filtermasse rundt drensrøret) og åpen kanal (med sidehelning etter antatt
 * jordart, se jordart-select i grensesnittet). */
function buildProfileDrawing(summary, jordart) {
  const avgGrade = Math.abs(summary.avg_grade_pct);
  const upsized = avgGrade < PIPE_UPSIZE_PCT_A;
  const pipeLabel = avgGrade < PIPE_UPSIZE_PCT_B ? "Ø110/97 mm (oppgradert)" : upsized ? "Ø110/97 mm" : "Ø60/50 mm (standard)";
  const pipeRadius = upsized ? 13 : 9;

  // ---- Diagram A: rørlagt grøft ----
  const wA = 260, hA = 240;
  const groundY = 30, bottomY = 190;
  const topL = 60, topR = 200, botL = 110, botR = 150;
  const pipeCx = (botL + botR) / 2, pipeCy = bottomY - 15;
  const diagramA = `
    <svg viewBox="0 0 ${wA} ${hA}" role="img" aria-label="Tverrsnitt av rørlagt grøft">
      <defs>
        <marker id="profile-arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#5c6b63" />
        </marker>
      </defs>
      <text x="${wA / 2}" y="16" text-anchor="middle" class="profile-title">Rørlagt grøft (tverrsnitt)</text>
      <line x1="10" y1="${groundY}" x2="${wA - 10}" y2="${groundY}" class="profile-ground" />
      <polygon points="${topL},${groundY} ${topR},${groundY} ${botR},${bottomY} ${botL},${bottomY}" class="profile-soil" />
      <circle cx="${pipeCx}" cy="${pipeCy}" r="${pipeRadius + 9}" class="profile-filter" />
      <circle cx="${pipeCx}" cy="${pipeCy}" r="${pipeRadius}" class="profile-pipe" />
      <line x1="22" y1="${groundY}" x2="22" y2="${bottomY}" class="profile-dim" />
      <text x="14" y="${(groundY + bottomY) / 2}" text-anchor="middle" class="profile-dim-label" transform="rotate(-90 14 ${(groundY + bottomY) / 2})">Grøftedybde: 1,0–1,2 m</text>
      <text x="${pipeCx}" y="${pipeCy + pipeRadius + 22}" text-anchor="middle" class="profile-label">${pipeLabel}</text>
      <text x="${pipeCx}" y="${pipeCy + pipeRadius + 36}" text-anchor="middle" class="profile-label-muted">Filtermasse (grus) rundt røret</text>
      <text x="${wA / 2}" y="${groundY - 8}" text-anchor="middle" class="profile-label-muted">Bakkenivå</text>
    </svg>`;

  // ---- Diagram B: åpen kanal (sidehelning etter jordart) ----
  const ratio = SIDE_SLOPE_RATIO_BY_JORDART[jordart] || SIDE_SLOPE_RATIO_BY_JORDART.sand_silt;
  const depthPx = 90, run = ratio * depthPx;
  const bottomWidth = 40;
  const groundYB = 20, bottomYB = groundYB + depthPx;
  const wB = Math.round(bottomWidth + 2 * run + 100);
  const centerX = wB / 2;
  const botLB = centerX - bottomWidth / 2, botRB = centerX + bottomWidth / 2;
  const topLB = botLB - run, topRB = botRB + run;
  const waterFrac = 0.6; // vannlinje, kun illustrativt
  const waterOffset = run * waterFrac;
  const waterY = bottomYB - depthPx * waterFrac;
  const diagramB = `
    <svg viewBox="0 0 ${wB} 220" role="img" aria-label="Tverrsnitt av åpen kanal">
      <text x="${centerX}" y="16" text-anchor="middle" class="profile-title">Åpen kanal (tverrsnitt) – jordart: ${SIDE_SLOPE_LABEL_BY_JORDART[jordart] || "sand/silt"}</text>
      <line x1="${topLB - 20}" y1="${groundYB}" x2="${topRB + 20}" y2="${groundYB}" class="profile-ground" />
      <polygon points="${topLB},${groundYB} ${topRB},${groundYB} ${botRB},${bottomYB} ${botLB},${bottomYB}" class="profile-channel" />
      <line x1="${botLB - waterOffset}" y1="${waterY}" x2="${botRB + waterOffset}" y2="${waterY}" class="profile-water" />
      <text x="${botLB - waterOffset - 6}" y="${waterY + 4}" text-anchor="end" class="profile-label-muted">Vannlinje (illustrativ)</text>
      <text x="${(topLB + botLB) / 2 - 6}" y="${(groundYB + bottomYB) / 2}" text-anchor="end" class="profile-label">1:${ratio}</text>
      <text x="${(topRB + botRB) / 2 + 6}" y="${(groundYB + bottomYB) / 2}" text-anchor="start" class="profile-label">1:${ratio}</text>
      <text x="${centerX}" y="${bottomYB + 16}" text-anchor="middle" class="profile-label-muted">Bunnbredde (skjematisk)</text>
      <text x="${centerX}" y="${groundYB - 6}" text-anchor="middle" class="profile-label-muted">Bakkenivå</text>
    </svg>`;

  return `
    <p class="hint">Skjematisk - ikke i målestokk. Viser prinsippet for oppbyggingen, ikke en ferdig tegning for anbud/bygging.</p>
    <div id="profile-drawings">${diagramA}${diagramB}</div>
  `;
}

function renderReport(result, { suggested } = {}) {
  const s = result.summary;
  const report = document.getElementById("report");
  const notes = buildDrainageNotes(result.segments || []);
  const construction = buildConstructionSuggestions(s);
  const jordart = document.getElementById("jordart-select").value;
  const profileDrawing = buildProfileDrawing(s, jordart);
  report.innerHTML = `
    ${suggested ? "<h2>Foreslått grøftetrasé</h2><p class=\"hint\">Heuristisk forslag - bekreft i felt og vurder grunnforhold (jordart) før graving.</p>" : ""}
    <h2>Sammendrag</h2>
    <table>
      <tr><td>Total lengde</td><td>${s.total_length_m} m</td></tr>
      <tr><td>Stigning / fall</td><td>${s.elevation_gain_m} m / ${s.elevation_loss_m} m</td></tr>
      <tr><td>Snitt fall</td><td>${s.avg_grade_pct} %</td></tr>
      <tr><td>Maks fall</td><td>${s.max_grade_pct} %</td></tr>
    </table>
    <h2>Merknader</h2>
    <ul>${notes.map((n) => `<li>${n}</li>`).join("")}</ul>
    <h2>Oppbyggingsforslag</h2>
    <p class="hint">Basert på NLRs veiledning for drenering/åpne kanaler. Grove tommelfingerregler - endelig
      dimensjonering bør gjøres av NLR eller annen fagperson, spesielt for areal/kapasitet og jordart.</p>
    <ul>${construction.map((c) => `<li>${c}</li>`).join("")}</ul>
    <h2>Profiltegning</h2>
    ${profileDrawing}
    ${renderWaypointsTable(result.waypoints)}
  `;
  renderWaypointMarkers(result.waypoints);
  lastRenderedResult = { result, suggested };
}

let lastRenderedResult = null;
document.getElementById("jordart-select").addEventListener("change", () => {
  if (lastRenderedResult) renderReport(lastRenderedResult.result, { suggested: lastRenderedResult.suggested });
});

function setStatus(message, isError = false) {
  const el = document.getElementById("status");
  el.textContent = message;
  el.className = isError ? "error" : "";
}

function getApiBase() {
  return document.getElementById("api-base").value.replace(/\/$/, "");
}

// ---- Automatisk henting av høydedata (DEM) fra Kartverket ----
let fetchedDemBlob = null;

function setAutoDemStatus(message, kind) {
  const el = document.getElementById("auto-dem-status");
  el.textContent = message;
  el.className = kind || "";
}

function getDemForRequest(fileInputId) {
  const file = document.getElementById(fileInputId).files[0];
  if (file) return { blob: file, filename: file.name };
  if (fetchedDemBlob) return { blob: fetchedDemBlob, filename: "auto-dem.tif" };
  return null;
}

document.getElementById("fetch-dem-btn").addEventListener("click", async () => {
  const apiBase = getApiBase();
  const b = map.getBounds();
  const resolution = document.getElementById("dem-resolution").value || "10";

  const formData = new FormData();
  formData.append("min_lat", b.getSouth());
  formData.append("min_lon", b.getWest());
  formData.append("max_lat", b.getNorth());
  formData.append("max_lon", b.getEast());
  formData.append("resolution_m", resolution);

  setAutoDemStatus("Henter høydedata for kartutsnittet …");
  try {
    const res = await fetch(`${apiBase}/api/dem/fetch`, { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Ukjent feil");
    }
    fetchedDemBlob = await res.blob();
    setAutoDemStatus("Høydedata hentet for synlig kartutsnitt. Kan nå brukes uten opplasting.", "ok");
  } catch (err) {
    fetchedDemBlob = null;
    setAutoDemStatus(`Feil ved henting: ${err.message}`, "error");
  }
});

// ---- Modusbytte ----
const analyzeForm = document.getElementById("analyze-form");
const suggestForm = document.getElementById("suggest-form");
const selfdrainForm = document.getElementById("selfdrain-form");

document.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener("change", (e) => {
    const mode = e.target.value;
    analyzeForm.hidden = mode !== "analyze";
    suggestForm.hidden = mode !== "suggest";
    selfdrainForm.hidden = mode !== "selfdrain";
    setStatus("");
    document.getElementById("report").innerHTML = "";
    document.getElementById("download-buttons").hidden = true;
    document.getElementById("save-alternative").hidden = true;
    document.getElementById("view3d-buttons").hidden = true;
    document.getElementById("follow-gps-buttons").hidden = true;
    lastResultForSave = null;
    trailLineLayer.clearLayers();
    trailLabelLayer.clearLayers();
    markerLayer.clearLayers();
    waypointLayer.clearLayers();
    depressionLayer.clearLayers();
  });
});

// ---- Vurder eksisterende trasé ----
analyzeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const trailFile = document.getElementById("trail-file").files[0];
  const dem = getDemForRequest("dem-file");
  const apiBase = getApiBase();

  if (!trailFile) {
    setStatus("Velg en trasé-fil.", true);
    return;
  }
  if (!dem) {
    setStatus("Velg en DEM-fil, eller hent høydedata automatisk for kartutsnittet over.", true);
    return;
  }

  const formData = new FormData();
  formData.append("trail", trailFile);
  formData.append("dem", dem.blob, dem.filename);

  setStatus("Analyserer …");
  try {
    const res = await fetch(`${apiBase}/api/analyze`, { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Ukjent feil");
    }
    const result = await res.json();
    setStatus("Ferdig.");
    markerLayer.clearLayers();
    renderMap(result.segments);
    renderReport(result);
    lastExportData = {
      points: result.waypoints.map((w) => [w.lat, w.lon]),
      route: {
        type: "LineString",
        coordinates: result.waypoints.map((w) => [w.lon, w.lat]),
      },
    };
    document.getElementById("download-buttons").hidden = false;
    lastResultForSave = { mode: "Vurdert trasé", analysis: result, dem };
    document.getElementById("save-alternative").hidden = false;
    document.getElementById("view3d-buttons").hidden = false;
    document.getElementById("follow-gps-buttons").hidden = false;
  } catch (err) {
    setStatus(`Feil: ${err.message}`, true);
  }
});

// ---- Foreslå trasé ----
// Rekkefølge av klikk: routeWaypoints[0] = start, routeWaypoints[last] = slutt,
// alt i mellom er faste mellompunkt (f.eks. for å styre unna en grunneiers areal).
let routeWaypoints = [];
let lastExportData = null;

function triggerDownload(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function buildGpx(points) {
  const trkpts = points
    .map(([lat, lon]) => `      <trkpt lat="${lat}" lon="${lon}"></trkpt>`)
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Grofteplanlegger" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Grøftetrasé (Grøfteplanlegger)</name>
    <trkseg>
${trkpts}
    </trkseg>
  </trk>
</gpx>
`;
}

document.getElementById("download-gpx").addEventListener("click", () => {
  if (!lastExportData) return;
  triggerDownload("trase.gpx", buildGpx(lastExportData.points), "application/gpx+xml");
});

document.getElementById("download-geojson").addEventListener("click", () => {
  if (!lastExportData) return;
  const geojson = {
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: {}, geometry: lastExportData.route }],
  };
  triggerDownload("trase.geojson", JSON.stringify(geojson, null, 2), "application/geo+json");
});

// ---- Sammenlign alternativer (lagres i localStorage i denne nettleseren) ----
const ALT_STORAGE_KEY = "grofteplanlegger-alternatives-v1";
const ALT_COLORS = ["#e91e63", "#3949ab", "#00897b", "#f4511e", "#6d4c41", "#7cb342", "#fbc02d", "#546e7a"];

let lastResultForSave = null; // { mode, analysis } - settes ved vellykket analyse/forslag

function loadAlternatives() {
  try {
    const raw = localStorage.getItem(ALT_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function persistAlternatives() {
  try {
    localStorage.setItem(ALT_STORAGE_KEY, JSON.stringify(savedAlternatives));
  } catch {
    // localStorage utilgjengelig (f.eks. privat nettlesing) - fortsetter uten lagring
  }
}

let savedAlternatives = loadAlternatives();

function renderCompareLayer() {
  compareLayer.clearLayers();
  for (const alt of savedAlternatives) {
    if (!alt.visible) continue;
    L.polyline(alt.points, { color: alt.color, weight: 4, opacity: 0.85 })
      .addTo(compareLayer)
      .bindTooltip(alt.name, { sticky: true });
  }
}

function renderCompareTable() {
  const wrapper = document.getElementById("compare-table-wrapper");
  if (savedAlternatives.length === 0) {
    wrapper.innerHTML = '<p class="hint">Ingen alternativer lagret ennå. Analyser/foreslå en trasé og trykk "Lagre som alternativ".</p>';
    return;
  }
  const rows = savedAlternatives
    .map(
      (alt) => `
        <tr>
          <td><span class="color-swatch" style="background:${alt.color}"></span></td>
          <td>${alt.name}</td>
          <td>${alt.mode}</td>
          <td>${alt.summary.total_length_m} m</td>
          <td>${alt.summary.avg_grade_pct} %</td>
          <td>${alt.summary.max_grade_pct} %</td>
          <td><input type="checkbox" data-alt-id="${alt.id}" class="alt-visible-toggle" ${alt.visible ? "checked" : ""} /></td>
          <td><button type="button" class="remove-alt-btn" data-alt-id="${alt.id}" title="Slett">✕</button></td>
        </tr>`
    )
    .join("");
  wrapper.innerHTML = `
    <table>
      <thead>
        <tr>
          <th></th><th>Navn</th><th>Type</th><th>Lengde</th><th>Snitt fall</th>
          <th>Maks fall</th><th>Vis</th><th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
  wrapper.querySelectorAll(".alt-visible-toggle").forEach((cb) => {
    cb.addEventListener("change", () => {
      const alt = savedAlternatives.find((a) => a.id === cb.dataset.altId);
      if (alt) {
        alt.visible = cb.checked;
        persistAlternatives();
        renderCompareLayer();
      }
    });
  });
  wrapper.querySelectorAll(".remove-alt-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      savedAlternatives = savedAlternatives.filter((a) => a.id !== btn.dataset.altId);
      persistAlternatives();
      renderCompareTable();
      renderCompareLayer();
    });
  });
}

document.getElementById("save-alternative-btn").addEventListener("click", () => {
  if (!lastResultForSave) return;
  const nameInput = document.getElementById("alternative-name");
  const name = nameInput.value.trim() || `Alternativ ${savedAlternatives.length + 1}`;
  const { mode, analysis } = lastResultForSave;

  const alt = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name,
    mode,
    savedAt: new Date().toISOString(),
    summary: analysis.summary,
    points: analysis.waypoints.map((w) => [w.lat, w.lon]),
    color: ALT_COLORS[savedAlternatives.length % ALT_COLORS.length],
    visible: true,
  };
  savedAlternatives.push(alt);
  persistAlternatives();
  nameInput.value = "";
  renderCompareTable();
  renderCompareLayer();
});

renderCompareTable();
renderCompareLayer();

function pointLabel(i, total) {
  if (i === 0) return "Start";
  if (i === total - 1) return "Slutt";
  return `Mellompunkt ${i}`;
}

function renderRouteWaypointMarkers() {
  markerLayer.clearLayers();
  const total = routeWaypoints.length;
  routeWaypoints.forEach((p, i) => {
    const label = pointLabel(i, total);
    L.marker(p, { title: label }).addTo(markerLayer).bindPopup(label);
  });
}

function updatePickedPointsLabel() {
  const el = document.getElementById("picked-points");
  if (routeWaypoints.length === 0) {
    el.textContent = "Start: –   Slutt: –";
    return;
  }
  const total = routeWaypoints.length;
  el.textContent = routeWaypoints
    .map((p, i) => `${pointLabel(i, total)}: ${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}`)
    .join("   ");
}

map.on("click", (e) => {
  const isSuggestMode = document.querySelector('input[name="mode"]:checked').value === "suggest";
  if (!isSuggestMode) return;

  routeWaypoints.push(e.latlng);
  renderRouteWaypointMarkers();
  updatePickedPointsLabel();
});

document.getElementById("reset-points").addEventListener("click", () => {
  routeWaypoints = [];
  markerLayer.clearLayers();
  updatePickedPointsLabel();
});

document.getElementById("undo-point").addEventListener("click", () => {
  routeWaypoints.pop();
  renderRouteWaypointMarkers();
  updatePickedPointsLabel();
});

document.getElementById("auto-endpoint-checkbox").addEventListener("change", (e) => {
  document.getElementById("auto-endpoint-hint").hidden = !e.target.checked;
});

suggestForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const dem = getDemForRequest("suggest-dem-file");
  const apiBase = getApiBase();
  const targetGrade = document.getElementById("target-grade").value;

  if (!dem) {
    setStatus("Velg en DEM-fil, eller hent høydedata automatisk for kartutsnittet over.", true);
    return;
  }
  const autoEndpoint = document.getElementById("auto-endpoint-checkbox").checked;
  if (routeWaypoints.length < 1) {
    setStatus("Klikk minst et startpunkt i kartet først.", true);
    return;
  }
  if (!autoEndpoint && routeWaypoints.length < 2) {
    setStatus(
      "Klikk minst et startpunkt og et utløpspunkt i kartet først (og ev. mellompunkt mellom dem), " +
        "eller kryss av for automatisk utløpspunkt.",
      true
    );
    return;
  }

  const formData = new FormData();
  formData.append("dem", dem.blob, dem.filename);
  formData.append("waypoints_json", JSON.stringify(routeWaypoints.map((p) => [p.lat, p.lng])));
  // "flow" = søk mot et jevnt ønsket fall (target_grade_pct) - nøyaktig det
  // en grøft/vannvei trenger, bare med en mye slakere målverdi enn sykkelsti.
  formData.append("trail_type", "flow");
  formData.append("target_grade_pct", targetGrade);

  setStatus("Foreslår grøftetrasé …");
  try {
    const res = await fetch(`${apiBase}/api/suggest`, { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Ukjent feil");
    }
    const result = await res.json();
    const stats = result.search_stats;
    let statusMsg = `Ferdig. ${stats.final_points} punkter${stats.smoothed ? " (glattet)" : " (uglattet – se hint under)"}.`;
    let isWarning = false;
    if (stats.auto_endpoint) {
      statusMsg +=
        " Utløpspunktet ble foreslått automatisk (laveste punkt i kartutsnittet) - " +
        "BEKREFT I FELT at det faktisk finnes en bekk/kum/grøft der før du graver.";
      isWarning = true;
    }
    if (stats.self_intersects) {
      statusMsg +=
        " OBS: traséen krysser/overlapper seg selv et sted - terrenget tvinger " +
        "trolig ruten gjennom samme korridor to ganger nær et mellompunkt. " +
        "Prøv å flytte mellompunktet litt, eller sjekk kartet nøye.";
      isWarning = true;
    }
    setStatus(statusMsg, isWarning);
    renderMap(result.analysis.segments);
    renderReport(result.analysis, { suggested: true });
    if (stats.auto_endpoint) {
      const [lat, lon] = result.points[result.points.length - 1];
      L.marker([lat, lon], { title: "Automatisk foreslått utløp" })
        .addTo(markerLayer)
        .bindPopup(
          "<strong>Automatisk foreslått utløp</strong><br>Laveste punkt i kartutsnittet - " +
            "bekreft i felt at det finnes en bekk/kum/grøft her før graving."
        )
        .openPopup();
    }
    lastExportData = { points: result.points, route: result.route };
    document.getElementById("download-buttons").hidden = false;
    lastResultForSave = { mode: "Foreslått trasé", analysis: result.analysis, dem };
    document.getElementById("save-alternative").hidden = false;
    document.getElementById("view3d-buttons").hidden = false;
    document.getElementById("follow-gps-buttons").hidden = false;
  } catch (err) {
    setStatus(`Feil: ${err.message}`, true);
  }
});

// ---- Sjekk selvdrenering (søkk-/lavpunktdeteksjon over hele kartutsnittet) ----
function depressionSeverity(maxDepthM) {
  if (maxDepthM > 0.2) return "bad";
  if (maxDepthM > 0.08) return "warn";
  return "ok";
}

function renderDepressions(response) {
  depressionLayer.clearLayers();
  for (const d of response.depressions) {
    const sev = depressionSeverity(d.max_depth_m);
    const radius = Math.max(6, Math.min(24, Math.sqrt(d.area_m2 / Math.PI)));
    L.circleMarker([d.lat, d.lon], {
      radius,
      color: "#1976d2",
      fillColor: severityColor(sev),
      fillOpacity: 0.6,
      weight: 2,
    })
      .addTo(depressionLayer)
      .bindPopup(
        `<strong>Søkk</strong><br>Areal: ${d.area_m2.toFixed(0)} m²<br>Maks dybde: ${d.max_depth_m.toFixed(2)} m` +
          `<br>Volum: ${d.volume_m3.toFixed(1)} m³`
      );
  }
}

function renderSelfdrainReport(response) {
  const report = document.getElementById("report");
  const n = response.depressions.length;
  const fraction = response.depression_area_fraction_pct;

  let verdict;
  if (n === 0) {
    verdict = "Ingen søkk funnet ut fra høydedataene - jordet ser ut til å ha en sammenhengende nedadgående vei ut fra hele kartutsnittet.";
  } else if (fraction < 1) {
    verdict = `Stort sett selvdrenerende - ${n} mindre søkk funnet, til sammen ${fraction} % av arealet.`;
  } else {
    verdict = `${n} søkk funnet, til sammen ${fraction} % av arealet - vurder tiltak (grøft/planering) på de største/dypeste punktene.`;
  }

  const rows = response.depressions
    .slice(0, 50)
    .map(
      (d, i) =>
        `<tr><td>${i + 1}</td><td>${d.area_m2.toFixed(0)} m²</td><td>${d.max_depth_m.toFixed(2)} m</td><td>${d.volume_m3.toFixed(1)} m³</td></tr>`
    )
    .join("");
  const truncatedNote =
    n > 50 ? `<p class="hint">Viser de 50 største av ${n} søkk.</p>` : "";

  report.innerHTML = `
    <h2>Selvdrenering</h2>
    <p class="hint">Basert kun på høydedata - kjenner ikke til jordart/infiltrasjonsevne, som også
      påvirker om et areal faktisk drenerer selv. Søkk markert i kartet, størst/dypest først under.</p>
    <table>
      <tr><td>Totalt areal</td><td>${response.total_area_m2.toFixed(0)} m²</td></tr>
      <tr><td>Antall søkk</td><td>${n}</td></tr>
      <tr><td>Andel av arealet i søkk</td><td>${fraction} %</td></tr>
    </table>
    <p><strong>${verdict}</strong></p>
    ${
      n > 0
        ? `<table>
            <thead><tr><th>#</th><th>Areal</th><th>Maks dybde</th><th>Volum</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
          ${truncatedNote}`
        : ""
    }
  `;
}

selfdrainForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const dem = getDemForRequest("selfdrain-dem-file");
  const apiBase = getApiBase();
  const minDepth = document.getElementById("min-depth").value;

  if (!dem) {
    setStatus("Velg en DEM-fil, eller hent høydedata automatisk for kartutsnittet over.", true);
    return;
  }

  const formData = new FormData();
  formData.append("dem", dem.blob, dem.filename);
  formData.append("min_depth_m", minDepth);

  setStatus("Sjekker selvdrenering …");
  try {
    const res = await fetch(`${apiBase}/api/dem/depressions`, { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Ukjent feil");
    }
    const result = await res.json();
    setStatus(`Ferdig. ${result.depressions.length} søkk funnet.`);
    renderDepressions(result);
    renderSelfdrainReport(result);
    if (result.depressions.length) {
      const bounds = L.latLngBounds(result.depressions.map((d) => [d.lat, d.lon]));
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 17 });
    }
  } catch (err) {
    setStatus(`Feil: ${err.message}`, true);
  }
});

// ---- 3D-visning av trasé + terreng (Three.js) ----
let threeRenderer = null;
let threeScene = null;
let threeCamera = null;
let threeControls = null;
let threeAnimationId = null;
let threeResizeHandler = null;
let lastTerrainData = null; // { grid, analysis } - cachet slik at eksaggerasjons-slider ikke trenger nytt kall

function setView3DStatus(message, isError = false) {
  const el = document.getElementById("view3d-status");
  el.textContent = message;
  el.style.color = isError ? "#ff8a80" : "";
}

function disposeThreeScene() {
  if (threeAnimationId !== null) {
    cancelAnimationFrame(threeAnimationId);
    threeAnimationId = null;
  }
  if (threeResizeHandler) {
    window.removeEventListener("resize", threeResizeHandler);
    threeResizeHandler = null;
  }
  if (threeRenderer) {
    threeRenderer.dispose();
    if (threeRenderer.domElement && threeRenderer.domElement.parentNode) {
      threeRenderer.domElement.parentNode.removeChild(threeRenderer.domElement);
    }
    threeRenderer = null;
  }
  threeScene = null;
  threeCamera = null;
  threeControls = null;
}

function buildTerrainMesh(grid, exaggeration) {
  const { rows, cols, cell_size_x_m, cell_size_y_m, origin_x_m, origin_y_m, elevations } = grid;
  const flat = elevations.flat();
  const minElev = Math.min(...flat);

  const positions = new Float32Array(rows * cols * 3);
  let p = 0;
  for (let i = 0; i < rows; i++) {
    for (let j = 0; j < cols; j++) {
      const x = origin_x_m + j * cell_size_x_m;
      const z = origin_y_m + i * cell_size_y_m;
      const y = (elevations[i][j] - minElev) * exaggeration;
      positions[p++] = x;
      positions[p++] = y;
      positions[p++] = z;
    }
  }

  const indices = [];
  for (let i = 0; i < rows - 1; i++) {
    for (let j = 0; j < cols - 1; j++) {
      const a = i * cols + j;
      const b = a + 1;
      const c = a + cols;
      const d = c + 1;
      indices.push(a, c, b, b, c, d);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  const material = new THREE.MeshStandardMaterial({
    color: 0x6b8f5e,
    roughness: 0.95,
    metalness: 0.0,
    flatShading: true,
    side: THREE.DoubleSide,
  });
  return { mesh: new THREE.Mesh(geometry, material), minElev };
}

const TRAIL_HALF_WIDTH_M = 0.4; // ~0,8 m grøftebredde (grov visuell antakelse)

/** Sentraldifferanse-tangent (retning) i XZ-planet for hvert trasépunkt. */
function computeTangents(positions) {
  const n = positions.length;
  const tangents = [];
  for (let i = 0; i < n; i++) {
    const a = i === 0 ? positions[0] : positions[i - 1];
    const b = i === n - 1 ? positions[n - 1] : positions[i + 1];
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const len = Math.hypot(dx, dz) || 1;
    tangents.push({ x: dx / len, z: dz / len });
  }
  return tangents;
}

/** Bilineær sampling av terreng-gitterets høyde ved et vilkårlig (x, z)-punkt
 * (samme lokale koordinatsystem som gitterets origin_x_m/origin_y_m). Brukes
 * til å plassere trasé-båndet - slik at det alltid ligger nøyaktig på den
 * (nedskalerte) terrengflaten som faktisk vises, i stedet for på analysens
 * separat presist samplede høyde. De to kan ellers avvike synlig på ekte,
 * ujevnt terreng siden terreng-gitteret er nedskalert for 3D-visningen mens
 * analysen sampler full DEM-oppløsning bilineært i hvert trasépunkt. */
function sampleGridElevation(grid, x, z) {
  const colF = (x - grid.origin_x_m) / grid.cell_size_x_m;
  const rowF = (z - grid.origin_y_m) / grid.cell_size_y_m;
  const c0 = Math.max(0, Math.min(grid.cols - 1, Math.floor(colF)));
  const r0 = Math.max(0, Math.min(grid.rows - 1, Math.floor(rowF)));
  const c1 = Math.min(grid.cols - 1, c0 + 1);
  const r1 = Math.min(grid.rows - 1, r0 + 1);
  const fc = Math.min(1, Math.max(0, colF - c0));
  const fr = Math.min(1, Math.max(0, rowF - r0));
  const e00 = grid.elevations[r0][c0];
  const e01 = grid.elevations[r0][c1];
  const e10 = grid.elevations[r1][c0];
  const e11 = grid.elevations[r1][c1];
  const top = e00 * (1 - fc) + e01 * fc;
  const bottom = e10 * (1 - fc) + e11 * fc;
  return top * (1 - fr) + bottom * fr;
}

/** Bygger grøfta/vannveien som et flatt bånd med reell bredde, farget etter
 * fall (samme grade-bånd som 2D-kartet) - ingen dosering/hopp-ramper her,
 * det er sykkelsti-spesifikke konsepter uten mening for en grøft. */
function buildTrailRibbon(grid, analysis, minElev, exaggeration) {
  const DIRT_COLOR = new THREE.Color(0x8d6e4a);
  const waypoints = analysis.waypoints;
  const n = waypoints.length;

  const positions = waypoints.map((w) => ({
    x: w.x_m,
    y: (sampleGridElevation(grid, w.x_m, w.y_m) - minElev) * exaggeration,
    z: w.y_m,
  }));
  const tangents = computeTangents(positions);

  function makeNode(pos, tangent, color) {
    const nx = -tangent.z;
    const nz = tangent.x;
    return {
      left: new THREE.Vector3(pos.x + nx * TRAIL_HALF_WIDTH_M, pos.y, pos.z + nz * TRAIL_HALF_WIDTH_M),
      right: new THREE.Vector3(pos.x - nx * TRAIL_HALF_WIDTH_M, pos.y, pos.z - nz * TRAIL_HALF_WIDTH_M),
      color,
    };
  }

  const nodes = [];
  for (let i = 0; i < n; i++) {
    const seg = analysis.segments[i] || analysis.segments[i - 1];
    const color = seg ? new THREE.Color(severityColor(gradeSeverity(seg.grade_pct))) : DIRT_COLOR;
    nodes.push(makeNode(positions[i], tangents[i], color));
  }

  const positionsArr = [];
  const colorsArr = [];
  for (let k = 0; k < nodes.length - 1; k++) {
    const a = nodes[k];
    const b = nodes[k + 1];
    if (!a || !b) continue;

    positionsArr.push(a.left.x, a.left.y, a.left.z, a.right.x, a.right.y, a.right.z, b.left.x, b.left.y, b.left.z);
    positionsArr.push(b.left.x, b.left.y, b.left.z, a.right.x, a.right.y, a.right.z, b.right.x, b.right.y, b.right.z);

    for (const c of [a.color, a.color, b.color, b.color, a.color, b.color]) {
      colorsArr.push(c.r, c.g, c.b);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positionsArr, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colorsArr, 3));
  geometry.computeVertexNormals();

  const material = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: 0.9,
    metalness: 0.0,
    side: THREE.DoubleSide,
  });

  const group = new THREE.Group();
  group.add(new THREE.Mesh(geometry, material));

  // Start-/sluttmarkører
  const markerGeom = new THREE.SphereGeometry(Math.max(0.8, TRAIL_HALF_WIDTH_M * 1.5), 12, 12);
  const startMarker = new THREE.Mesh(markerGeom, new THREE.MeshStandardMaterial({ color: 0x2f6b4f }));
  const first = positions[0];
  startMarker.position.set(first.x, first.y + 0.5 * exaggeration, first.z);
  group.add(startMarker);

  const endMarker = new THREE.Mesh(markerGeom, new THREE.MeshStandardMaterial({ color: 0xc62828 }));
  const last = positions[n - 1];
  endMarker.position.set(last.x, last.y + 0.5 * exaggeration, last.z);
  group.add(endMarker);

  return group;
}

function renderThreeScene(grid, analysis, exaggeration) {
  disposeThreeScene();

  const wrapper = document.getElementById("view3d-canvas-wrapper");
  const width = wrapper.clientWidth || 800;
  const height = wrapper.clientHeight || 600;

  threeScene = new THREE.Scene();
  threeScene.background = new THREE.Color(0xbcd4e0);

  const { mesh, minElev } = buildTerrainMesh(grid, exaggeration);
  threeScene.add(mesh);
  threeScene.add(buildTrailRibbon(grid, analysis, minElev, exaggeration));

  const terrainWidth = grid.cols * grid.cell_size_x_m;
  const terrainDepth = grid.rows * grid.cell_size_y_m;
  const terrainSpan = Math.max(terrainWidth, terrainDepth);
  const terrainCenterX = grid.origin_x_m + terrainWidth / 2;
  const terrainCenterZ = grid.origin_y_m + terrainDepth / 2;

  // Fokuser kameraet på traséens eget omfang, ikke hele terrenget - DEM-en
  // kan dekke et mye større område enn selve stien (f.eks. hele kartutsnittet).
  const xs = analysis.waypoints.map((w) => w.x_m);
  const ys = analysis.waypoints.map((w) => w.y_m);
  const trailCenterX = (Math.min(...xs) + Math.max(...xs)) / 2;
  const trailCenterZ = (Math.min(...ys) + Math.max(...ys)) / 2;
  const trailSpan = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 10);
  // Kameraavstand/-høyde skalert direkte etter traséens utstrekning (ikke hele
  // terrenget), med en ganske bratt vinkel slik at traséen fyller bildet.
  const camDist = trailSpan * 0.6;
  const camHeight = trailSpan * 1.5;

  threeCamera = new THREE.PerspectiveCamera(50, width / height, 0.1, terrainSpan * 20);
  threeCamera.position.set(trailCenterX, camHeight, trailCenterZ + camDist);

  threeScene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const sun = new THREE.DirectionalLight(0xffffff, 0.8);
  sun.position.set(terrainCenterX + terrainSpan * 0.5, terrainSpan, terrainCenterZ - terrainSpan * 0.3);
  threeScene.add(sun);

  threeRenderer = new THREE.WebGLRenderer({ antialias: true });
  threeRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  threeRenderer.setSize(width, height);
  wrapper.innerHTML = "";
  wrapper.appendChild(threeRenderer.domElement);

  threeControls = new THREE.OrbitControls(threeCamera, threeRenderer.domElement);
  threeControls.target.set(trailCenterX, 0, trailCenterZ);
  threeControls.update();

  threeResizeHandler = () => {
    const w = wrapper.clientWidth || width;
    const h = wrapper.clientHeight || height;
    threeCamera.aspect = w / h;
    threeCamera.updateProjectionMatrix();
    threeRenderer.setSize(w, h);
  };
  window.addEventListener("resize", threeResizeHandler);

  function animate() {
    threeAnimationId = requestAnimationFrame(animate);
    threeControls.update();
    threeRenderer.render(threeScene, threeCamera);
  }
  animate();
}

document.getElementById("view-3d-btn").addEventListener("click", async () => {
  if (!lastResultForSave || !lastResultForSave.dem) return;
  const apiBase = getApiBase();
  const modal = document.getElementById("view3d-modal");
  modal.hidden = false;
  setView3DStatus("Bygger terreng …");

  try {
    const formData = new FormData();
    formData.append("dem", lastResultForSave.dem.blob, lastResultForSave.dem.filename);
    const res = await fetch(`${apiBase}/api/dem/terrain-grid`, { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Ukjent feil");
    }
    const grid = await res.json();
    lastTerrainData = { grid, analysis: lastResultForSave.analysis };
    const exaggeration = parseFloat(document.getElementById("view3d-exaggeration").value);
    renderThreeScene(grid, lastResultForSave.analysis, exaggeration);
    setView3DStatus("Dra for å rotere, scroll for å zoome.");
  } catch (err) {
    setView3DStatus(`Feil: ${err.message}`, true);
  }
});

document.getElementById("view3d-exaggeration").addEventListener("input", (e) => {
  if (!lastTerrainData) return;
  renderThreeScene(lastTerrainData.grid, lastTerrainData.analysis, parseFloat(e.target.value));
});

document.getElementById("view3d-close-btn").addEventListener("click", () => {
  document.getElementById("view3d-modal").hidden = true;
  disposeThreeScene();
});

// ---- Følg trasé i felt (live GPS-posisjon vs. foreslått/vurdert trasé) ----
let followGpsMap = null;
let followGpsWatchId = null;
let followGpsRouteLayer = null;
let followGpsPositionMarker = null;
let followGpsAccuracyCircle = null;
let followGpsConnectorLine = null;
let followGpsFirstFix = true;

function setFollowGpsStatus(message, isError = false) {
  const el = document.getElementById("follow-gps-status");
  el.textContent = message;
  el.style.color = isError ? "#ff8a80" : "";
}

/** Meter pr. breddegrad/lengdegrad ved en gitt breddegrad - grei nok
 * plan-tilnærming for feltavstander (noen hundre meter), ikke egnet for
 * store avstander/nær polene. */
function metersPerDegree(latDeg) {
  const latRad = (latDeg * Math.PI) / 180;
  return { mPerDegLat: 110574, mPerDegLon: 111320 * Math.cos(latRad) };
}

/** Finner nærmeste punkt på traséen (polyline av [lat, lon]-par) til en gitt
 * posisjon, i lokale meter-koordinater med posisjonen selv som origo. Bruker
 * cumDist (kumulativ avstand langs traséen, meter - fra analysens
 * waypoints[].distance_from_start_m) til å regne ut fremdrift langs traséen.
 * crossSign > 0 = posisjonen er til venstre for traséretningen (sett i
 * gangretning), < 0 = til høyre. */
function nearestPointOnRoute(lat, lon, routeLatLon, cumDist) {
  const { mPerDegLat, mPerDegLon } = metersPerDegree(lat);
  const toXY = (la, lo) => ({ x: (lo - lon) * mPerDegLon, y: (la - lat) * mPerDegLat });

  let best = null;
  for (let i = 0; i < routeLatLon.length - 1; i++) {
    const a = toXY(routeLatLon[i][0], routeLatLon[i][1]);
    const b = toXY(routeLatLon[i + 1][0], routeLatLon[i + 1][1]);
    const abx = b.x - a.x;
    const aby = b.y - a.y;
    const lenSq = abx * abx + aby * aby;
    let t = lenSq > 1e-9 ? -(a.x * abx + a.y * aby) / lenSq : 0;
    t = Math.max(0, Math.min(1, t));
    const cx = a.x + t * abx;
    const cy = a.y + t * aby;
    const dist = Math.hypot(cx, cy);
    if (!best || dist < best.dist) {
      const crossSign = abx * -a.y - aby * -a.x;
      const segStart = cumDist ? cumDist[i] : 0;
      const segEnd = cumDist ? cumDist[i + 1] : 0;
      const progress = cumDist ? segStart + t * (segEnd - segStart) : null;
      best = {
        dist,
        crossSign,
        progress,
        latlng: [lat + cy / mPerDegLat, lon + cx / mPerDegLon],
      };
    }
  }
  return best;
}

function formatDistance(m) {
  if (m < 10) return `${m.toFixed(1)} m`;
  return `${Math.round(m)} m`;
}

function updateFollowGpsUI(lat, lon, accuracy) {
  if (!lastResultForSave) return;
  const waypoints = lastResultForSave.analysis.waypoints;
  const routeLatLon = waypoints.map((w) => [w.lat, w.lon]);
  const cumDist = waypoints.map((w) => w.distance_from_start_m);
  const totalLength = cumDist[cumDist.length - 1];

  const nearest = nearestPointOnRoute(lat, lon, routeLatLon, cumDist);
  if (!nearest) return;

  document.getElementById("follow-gps-distance").textContent = formatDistance(nearest.dist);
  document.getElementById("follow-gps-direction").textContent =
    nearest.dist < 1 ? "På linja" : nearest.crossSign > 0 ? "Trasé til venstre" : "Trasé til høyre";
  document.getElementById("follow-gps-progress").textContent =
    nearest.progress !== null
      ? `${Math.round(nearest.progress)} m av ${Math.round(totalLength)} m (${Math.round((nearest.progress / totalLength) * 100)} %)`
      : "–";

  const latlng = [lat, lon];
  if (!followGpsPositionMarker) {
    followGpsPositionMarker = L.circleMarker(latlng, {
      radius: 8,
      color: "#1976d2",
      fillColor: "#1976d2",
      fillOpacity: 1,
      weight: 2,
    }).addTo(followGpsMap);
    followGpsAccuracyCircle = L.circle(latlng, { radius: accuracy, color: "#1976d2", weight: 1, fillOpacity: 0.08 }).addTo(followGpsMap);
    followGpsConnectorLine = L.polyline([latlng, nearest.latlng], { color: "#c62828", weight: 2, dashArray: "4,4" }).addTo(followGpsMap);
  } else {
    followGpsPositionMarker.setLatLng(latlng);
    followGpsAccuracyCircle.setLatLng(latlng).setRadius(accuracy);
    followGpsConnectorLine.setLatLngs([latlng, nearest.latlng]);
  }

  if (followGpsFirstFix) {
    followGpsMap.setView(latlng, 18);
    followGpsFirstFix = false;
  } else {
    followGpsMap.panTo(latlng, { animate: true });
  }
}

function onFollowGpsPosition(pos) {
  setFollowGpsStatus(`Nøyaktighet: ~${Math.round(pos.coords.accuracy)} m`);
  updateFollowGpsUI(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy);
}

function onFollowGpsError(err) {
  const messages = {
    1: "Posisjon ble avslått. Tillat posisjonstilgang for denne siden i nettleseren.",
    2: "Posisjon utilgjengelig - sjekk GPS/nettverk.",
    3: "Tidsavbrudd ved henting av posisjon.",
  };
  setFollowGpsStatus(messages[err.code] || `Feil: ${err.message}`, true);
}

document.getElementById("follow-gps-btn").addEventListener("click", () => {
  if (!lastResultForSave) return;
  if (!("geolocation" in navigator)) {
    setStatus("Denne nettleseren støtter ikke posisjonsdeling (geolocation).", true);
    return;
  }

  const modal = document.getElementById("follow-gps-modal");
  modal.hidden = false;
  followGpsFirstFix = true;
  setFollowGpsStatus("Henter posisjon …");

  const waypoints = lastResultForSave.analysis.waypoints;
  followGpsMap = L.map("follow-gps-map-wrapper").setView([waypoints[0].lat, waypoints[0].lon], 16);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap-bidragsytere",
    maxZoom: 19,
  }).addTo(followGpsMap);
  followGpsRouteLayer = L.polyline(
    waypoints.map((w) => [w.lat, w.lon]),
    { color: "#8a5a2b", weight: 5 }
  ).addTo(followGpsMap);
  followGpsMap.fitBounds(followGpsRouteLayer.getBounds(), { padding: [20, 20] });

  followGpsWatchId = navigator.geolocation.watchPosition(onFollowGpsPosition, onFollowGpsError, {
    enableHighAccuracy: true,
    maximumAge: 2000,
    timeout: 15000,
  });
});

function closeFollowGps() {
  if (followGpsWatchId !== null) {
    navigator.geolocation.clearWatch(followGpsWatchId);
    followGpsWatchId = null;
  }
  if (followGpsMap) {
    followGpsMap.remove();
    followGpsMap = null;
  }
  followGpsPositionMarker = null;
  followGpsAccuracyCircle = null;
  followGpsConnectorLine = null;
  followGpsRouteLayer = null;
  document.getElementById("follow-gps-modal").hidden = true;
}

document.getElementById("follow-gps-close-btn").addEventListener("click", closeFollowGps);
