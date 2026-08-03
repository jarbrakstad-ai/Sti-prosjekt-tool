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
    lastResultForSave = { mode: "Vurdert trasé", analysis: result };
    document.getElementById("save-alternative").hidden = false;
  } catch (err) {
    setStatus(`Feil: ${err.message}`, true);
  }
});

// ---- Foreslå trasé ----
let pickedStart = null;
let pickedEnd = null;
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

function updatePickedPointsLabel() {
  const fmt = (p) => (p ? `${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}` : "–");
  document.getElementById("picked-points").textContent =
    `Start: ${fmt(pickedStart)}   Slutt: ${fmt(pickedEnd)}`;
}

map.on("click", (e) => {
  const isSuggestMode = document.querySelector('input[name="mode"]:checked').value === "suggest";
  if (!isSuggestMode) return;

  markerLayer.clearLayers();
  if (!pickedStart || (pickedStart && pickedEnd)) {
    pickedStart = e.latlng;
    pickedEnd = null;
  } else {
    pickedEnd = e.latlng;
  }
  if (pickedStart) L.marker(pickedStart, { title: "Start" }).addTo(markerLayer).bindPopup("Start");
  if (pickedEnd) L.marker(pickedEnd, { title: "Slutt" }).addTo(markerLayer).bindPopup("Slutt");
  updatePickedPointsLabel();
});

document.getElementById("reset-points").addEventListener("click", () => {
  pickedStart = null;
  pickedEnd = null;
  markerLayer.clearLayers();
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
  if (!pickedStart || !pickedEnd) {
    setStatus("Klikk et start- og et sluttpunkt i kartet først.", true);
    return;
  }

  const formData = new FormData();
  formData.append("dem", dem.blob, dem.filename);
  formData.append("start_lat", pickedStart.lat);
  formData.append("start_lon", pickedStart.lng);
  formData.append("end_lat", pickedEnd.lat);
  formData.append("end_lon", pickedEnd.lng);
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
    setStatus(
      `Ferdig. ${stats.final_points} punkter${stats.smoothed ? " (glattet)" : " (uglattet – se hint under)"}.`
    );
    renderMap(result.analysis.segments);
    renderReport(result.analysis, { suggested: true });
    lastExportData = { points: result.points, route: result.route };
    document.getElementById("download-buttons").hidden = false;
    lastResultForSave = { mode: "Foreslått trasé", analysis: result.analysis };
    document.getElementById("save-alternative").hidden = false;
  } catch (err) {
    setStatus(`Feil: ${err.message}`, true);
  }
});
