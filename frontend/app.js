const BAD_FLAGS = new Set(["half_rule_violation", "fall_line_high_risk", "steep_grade"]);
const WARN_FLAGS = new Set([
  "fall_line_moderate_risk",
  "missing_grade_reversal",
  "abrupt_grade_transition",
  "elevation_mismatch",
]);

const FLAG_LABELS = {
  half_rule_violation: "Half rule brutt",
  steep_grade: "For bratt",
  fall_line_high_risk: "Følger fallinjen (høy risiko)",
  fall_line_moderate_risk: "Følger fallinjen (moderat risiko)",
  missing_grade_reversal: "Mangler drenering (grade reversal)",
  abrupt_grade_transition: "Brå endring i helning",
  elevation_mismatch: "Avvik GPX- vs DEM-høyde",
};

const map = L.map("map").setView([61.0, 9.0], 6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap-bidragsytere",
  maxZoom: 19,
}).addTo(map);

window.addEventListener("resize", () => map.invalidateSize());
window.addEventListener("orientationchange", () => setTimeout(() => map.invalidateSize(), 200));

// Egne lag per informasjonstype, slik at de kan skrus av/på uavhengig
// (se "Vis i kart"-panelet) i stedet for å presse alt oppå hverandre.
const trailLineLayer = L.layerGroup().addTo(map);
const trailLabelLayer = L.layerGroup(); // av som standard - kan bli tett ved mange segmenter
const markerLayer = L.layerGroup().addTo(map);
const waypointLayer = L.layerGroup(); // av som standard
const jumpLayer = L.layerGroup().addTo(map);
const cornerLayer = L.layerGroup().addTo(map);
const compareLayer = L.layerGroup().addTo(map);

const LAYER_BY_CHECKBOX = {
  "layer-trail-lines": trailLineLayer,
  "layer-segment-labels": trailLabelLayer,
  "layer-waypoints": waypointLayer,
  "layer-jumps": jumpLayer,
  "layer-corners": cornerLayer,
  "layer-compare": compareLayer,
};

for (const [checkboxId, layer] of Object.entries(LAYER_BY_CHECKBOX)) {
  const checkbox = document.getElementById(checkboxId);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) map.addLayer(layer);
    else map.removeLayer(layer);
  });
}

function segmentSeverity(flags) {
  if (flags.some((f) => BAD_FLAGS.has(f))) return "bad";
  if (flags.some((f) => WARN_FLAGS.has(f))) return "warn";
  return "ok";
}

function severityColor(sev) {
  return { ok: "#2e7d32", warn: "#f9a825", bad: "#c62828" }[sev];
}

function segmentMidpoint(seg) {
  return [(seg.start[0] + seg.end[0]) / 2, (seg.start[1] + seg.end[1]) / 2];
}

function renderMap(segments) {
  trailLineLayer.clearLayers();
  trailLabelLayer.clearLayers();
  const bounds = [];
  for (const seg of segments) {
    const sev = segmentSeverity(seg.flags);
    const latlngs = [seg.start, seg.end];
    const color = severityColor(sev);
    const popupHtml =
      `Segment ${seg.index}: ${seg.length_m} m, helning ${seg.grade_pct}%` +
      (seg.flags.length ? `<br>${seg.flags.map((f) => FLAG_LABELS[f] || f).join("<br>")}` : "<br>Ingen funn");

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

function renderJumpOpportunities(jumpOpportunities) {
  jumpLayer.clearLayers();
  for (const opp of jumpOpportunities || []) {
    L.polyline([opp.start, opp.end], {
      color: "#8e24aa",
      weight: 7,
      opacity: 0.85,
      dashArray: "2,10",
      lineCap: "round",
    })
      .addTo(jumpLayer)
      .bindPopup(
        `<strong>Mulig hopplinje</strong><br>${opp.length_m} m, snitt-helning ~${Math.abs(opp.avg_grade_pct)}%` +
          `<br>${opp.note}`
      );
  }
}

function renderJumpOpportunitiesSection(jumpOpportunities) {
  if (!jumpOpportunities || jumpOpportunities.length === 0) {
    return `
      <h2>Hopplinje-muligheter</h2>
      <p class="hint">Ingen jevne nedoverbakke-partier funnet som naturlig egner seg til hopp/tabletop uten videre tilpasning.</p>
    `;
  }
  const items = jumpOpportunities
    .map(
      (opp) =>
        `<li>${opp.length_m} m, snitt-helning ~${Math.abs(opp.avg_grade_pct)} % (variasjon ${opp.grade_variation_pct} pp) – ${opp.note}</li>`
    )
    .join("");
  return `
    <h2>Hopplinje-muligheter (${jumpOpportunities.length})</h2>
    <p class="hint">Grov heuristikk basert på jevn nedoverbakke – markert med lilla stiplet linje i kartet. Må detaljprosjekteres og kontrolleres i felt (fart inn, sprangvidde, sikt) før bygging.</p>
    <ul>${items}</ul>
  `;
}

function renderCornerRecommendations(cornerRecommendations) {
  cornerLayer.clearLayers();
  for (const rec of cornerRecommendations || []) {
    const color = rec.flags.includes("bank_angle_high") ? "#c62828" : "#00838f";
    L.circleMarker(rec.location, {
      radius: 7,
      color,
      fillColor: color,
      fillOpacity: 0.9,
      weight: 2,
    })
      .addTo(cornerLayer)
      .bindTooltip(`${rec.recommended_bank_deg}°`, { permanent: true, direction: "top", offset: [0, -8] })
      .bindPopup(
        `<strong>Sving – dosering</strong><br>Svingvinkel ~${rec.turn_angle_deg}°, anslått radius ${rec.estimated_radius_m} m` +
          `<br>Antatt fart ~${rec.assumed_speed_kmh} km/t<br>Anbefalt dosering: <strong>${rec.recommended_bank_deg}°</strong>` +
          `<br>${rec.note}`
      );
  }
}

function renderCornerRecommendationsSection(cornerRecommendations) {
  if (!cornerRecommendations || cornerRecommendations.length === 0) {
    return `
      <h2>Svinger – dosering</h2>
      <p class="hint">Ingen svinger skarpere enn terskelen ble funnet.</p>
    `;
  }
  const items = cornerRecommendations
    .map(
      (rec) =>
        `<li>Svingvinkel ~${rec.turn_angle_deg}°, radius ${rec.estimated_radius_m} m – anbefalt dosering ` +
        `<strong>${rec.recommended_bank_deg}°</strong> (antatt fart ~${rec.assumed_speed_kmh} km/t)` +
        `${rec.flags.includes("bank_angle_high") ? " ⚠️ vurder større svingradius" : ""}</li>`
    )
    .join("");
  return `
    <h2>Svinger – dosering (${cornerRecommendations.length})</h2>
    <p class="hint">Grov heuristikk basert på svingradius og antatt fart – markert som fargede punkter i kartet
    (turkis = normal, rød = vurder større radius). Faktisk komfortabel dosering avhenger av underlag og
    syklistens erfaring – bruk som utgangspunkt, ikke fasit.</p>
    <ul>${items}</ul>
  `;
}

function renderReport(result, { suggested } = {}) {
  const s = result.summary;
  const report = document.getElementById("report");
  report.innerHTML = `
    ${suggested ? "<h2>Foreslått trasé</h2><p class=\"hint\">Heuristisk forslag – kontroller i felt før bygging.</p>" : ""}
    <h2>Sammendrag</h2>
    <table>
      <tr><td>Total lengde</td><td>${s.total_length_m} m</td></tr>
      <tr><td>Stigning / fall</td><td>${s.elevation_gain_m} m / ${s.elevation_loss_m} m</td></tr>
      <tr><td>Snitt helning</td><td>${s.avg_grade_pct} %</td></tr>
      <tr><td>Maks helning</td><td>${s.max_grade_pct} %</td></tr>
      <tr><td>Segmenter med funn</td><td>${s.flagged_segments} / ${s.num_segments}</td></tr>
      <tr><td><strong>Bærekraft-score</strong></td><td><strong>${s.sustainability_score} / 100</strong></td></tr>
    </table>
    <h2>Anbefalinger</h2>
    <ul>${result.recommendations.map((r) => `<li>${r}</li>`).join("")}</ul>
    ${renderJumpOpportunitiesSection(result.jump_opportunities)}
    ${renderCornerRecommendationsSection(result.corner_recommendations)}
    ${renderWaypointsTable(result.waypoints)}
  `;
  renderWaypointMarkers(result.waypoints);
  renderJumpOpportunities(result.jump_opportunities);
  renderCornerRecommendations(result.corner_recommendations);
}

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

document.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener("change", (e) => {
    const isSuggest = e.target.value === "suggest";
    analyzeForm.hidden = isSuggest;
    suggestForm.hidden = !isSuggest;
    setStatus("");
    document.getElementById("report").innerHTML = "";
    document.getElementById("download-buttons").hidden = true;
    document.getElementById("save-alternative").hidden = true;
    document.getElementById("view3d-buttons").hidden = true;
    lastResultForSave = null;
    trailLineLayer.clearLayers();
    trailLabelLayer.clearLayers();
    markerLayer.clearLayers();
    waypointLayer.clearLayers();
    jumpLayer.clearLayers();
    cornerLayer.clearLayers();
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
<gpx version="1.1" creator="Sti-prosjekt-tool" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Trasé (Sti-prosjekt-tool)</name>
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
const ALT_STORAGE_KEY = "sti-prosjekt-tool-alternatives-v1";
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
          <td>${alt.summary.sustainability_score}</td>
          <td>${alt.jumpCount}</td>
          <td>${alt.cornerCount}</td>
          <td><input type="checkbox" data-alt-id="${alt.id}" class="alt-visible-toggle" ${alt.visible ? "checked" : ""} /></td>
          <td><button type="button" class="remove-alt-btn" data-alt-id="${alt.id}" title="Slett">✕</button></td>
        </tr>`
    )
    .join("");
  wrapper.innerHTML = `
    <table>
      <thead>
        <tr>
          <th></th><th>Navn</th><th>Type</th><th>Lengde</th><th>Snitt helning</th>
          <th>Maks helning</th><th>Score</th><th>Hopp</th><th>Svinger</th><th>Vis</th><th></th>
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
    jumpCount: (analysis.jump_opportunities || []).length,
    cornerCount: (analysis.corner_recommendations || []).length,
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

suggestForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const dem = getDemForRequest("suggest-dem-file");
  const apiBase = getApiBase();
  const trailType = document.getElementById("trail-type").value;
  const targetGrade = document.getElementById("target-grade").value;

  if (!dem) {
    setStatus("Velg en DEM-fil, eller hent høydedata automatisk for kartutsnittet over.", true);
    return;
  }
  if (routeWaypoints.length < 2) {
    setStatus("Klikk minst et start- og et sluttpunkt i kartet først (og ev. mellompunkt mellom dem).", true);
    return;
  }

  const formData = new FormData();
  formData.append("dem", dem.blob, dem.filename);
  formData.append("waypoints_json", JSON.stringify(routeWaypoints.map((p) => [p.lat, p.lng])));
  formData.append("trail_type", trailType);
  formData.append("target_grade_pct", targetGrade);

  setStatus("Foreslår trasé …");
  try {
    const res = await fetch(`${apiBase}/api/suggest`, { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Ukjent feil");
    }
    const result = await res.json();
    const stats = result.search_stats;
    let statusMsg = `Ferdig. ${stats.final_points} punkter${stats.smoothed ? " (glattet)" : " (uglattet – se hint under)"}.`;
    if (stats.self_intersects) {
      statusMsg +=
        " OBS: traséen krysser/overlapper seg selv et sted - terrenget tvinger " +
        "trolig ruten gjennom samme korridor to ganger nær et mellompunkt. " +
        "Prøv å flytte mellompunktet litt, eller sjekk kartet nøye.";
    }
    setStatus(statusMsg, stats.self_intersects);
    renderMap(result.analysis.segments);
    renderReport(result.analysis, { suggested: true });
    lastExportData = { points: result.points, route: result.route };
    document.getElementById("download-buttons").hidden = false;
    lastResultForSave = { mode: "Foreslått trasé", analysis: result.analysis, dem };
    document.getElementById("save-alternative").hidden = false;
    document.getElementById("view3d-buttons").hidden = false;
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

const TRAIL_HALF_WIDTH_M = 0.6; // ~1,2 m stibredde (typisk singletrack)
const MAX_VISUAL_BANK_DEG = 35; // tak for hvor bratt vi faktisk tegner dosering (rent visuelt)
const JUMP_LIP_HEIGHT_M = 1.0; // høyde på hopp-kicker over terrenget, før eksaggerasjon

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

/** Doseringsvinkel (grader, signert) per trasépunkt, ut fra corner_recommendations,
 * bløtt utjevnet mot naboene slik at dosering ramper inn/ut av svingen. */
function computeBankDegrees(analysis, n, tangents) {
  const bankDeg = new Array(n).fill(0);
  for (const rec of analysis.corner_recommendations || []) {
    const idx = rec.point_index;
    if (idx <= 0 || idx >= n - 1) continue;
    const tin = tangents[idx - 1];
    const tout = tangents[Math.min(idx + 1, n - 1)];
    const cross = tin.x * tout.z - tin.z * tout.x;
    const sign = cross >= 0 ? 1 : -1;
    const magnitude = Math.min(Math.abs(rec.recommended_bank_deg), MAX_VISUAL_BANK_DEG);
    for (let off = -2; off <= 2; off++) {
      const j = idx + off;
      if (j < 0 || j >= n) continue;
      const weight = Math.max(0, 1 - Math.abs(off) / 3);
      const val = sign * magnitude * weight;
      if (Math.abs(val) > Math.abs(bankDeg[j])) bankDeg[j] = val;
    }
  }
  return bankDeg;
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

/** Bygger stien som et bånd med reell bredde: fysisk dosert i svinger, og med
 * stiliserte hopp-ramper (opptak -> gap -> landing) ved hopplinje-mulighetene. */
function buildTrailRibbon(grid, analysis, minElev, exaggeration) {
  const DIRT_COLOR = new THREE.Color(0x8d6e4a);
  const JUMP_COLOR = new THREE.Color(0x8e24aa);
  const waypoints = analysis.waypoints;
  const n = waypoints.length;

  const positions = waypoints.map((w) => ({
    x: w.x_m,
    y: (sampleGridElevation(grid, w.x_m, w.y_m) - minElev) * exaggeration,
    z: w.y_m,
  }));
  const tangents = computeTangents(positions);
  const bankDeg = computeBankDegrees(analysis, n, tangents);

  function makeNode(pos, tangent, bankDegVal, color) {
    const nx = -tangent.z;
    const nz = tangent.x;
    const yOff = TRAIL_HALF_WIDTH_M * Math.tan((bankDegVal * Math.PI) / 180);
    return {
      left: new THREE.Vector3(
        pos.x + nx * TRAIL_HALF_WIDTH_M,
        pos.y - yOff,
        pos.z + nz * TRAIL_HALF_WIDTH_M
      ),
      right: new THREE.Vector3(
        pos.x - nx * TRAIL_HALF_WIDTH_M,
        pos.y + yOff,
        pos.z - nz * TRAIL_HALF_WIDTH_M
      ),
      color,
    };
  }

  const jumpZoneByStart = new Map();
  for (const jump of analysis.jump_opportunities || []) {
    jumpZoneByStart.set(jump.start_index, jump);
  }

  const lipHeight = JUMP_LIP_HEIGHT_M * exaggeration;
  const nodes = []; // null = "gap" (ingen flate - syklisten er i luften her)
  let i = 0;
  while (i < n) {
    const jump = jumpZoneByStart.get(i);
    if (jump && jump.end_index > i) {
      const endIdx = Math.min(jump.end_index, n - 1);
      const startPos = positions[i];
      const endPos = positions[endIdx];
      const tangent = tangents[i];
      const SUBDIVISIONS = 24;
      for (let s = 0; s <= SUBDIVISIONS; s++) {
        const t = s / SUBDIVISIONS;
        if (t >= 0.2 && t < 0.35) {
          nodes.push(null);
          continue;
        }
        const interp = {
          x: startPos.x + (endPos.x - startPos.x) * t,
          y: startPos.y + (endPos.y - startPos.y) * t,
          z: startPos.z + (endPos.z - startPos.z) * t,
        };
        if (t < 0.2) interp.y += lipHeight * (t / 0.2);
        nodes.push(makeNode(interp, tangent, 0, JUMP_COLOR));
      }
      i = endIdx + 1;
    } else {
      const seg = analysis.segments[i];
      const color =
        seg && seg.flags.length ? new THREE.Color(severityColor(segmentSeverity(seg.flags))) : DIRT_COLOR;
      nodes.push(makeNode(positions[i], tangents[i], bankDeg[i], color));
      i++;
    }
  }

  const positionsArr = [];
  const colorsArr = [];
  for (let k = 0; k < nodes.length - 1; k++) {
    const a = nodes[k];
    const b = nodes[k + 1];
    if (!a || !b) continue; // hopp over "gap"-partier i hopplinjene

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
