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

const trailLayer = L.layerGroup().addTo(map);
const markerLayer = L.layerGroup().addTo(map);

function segmentSeverity(flags) {
  if (flags.some((f) => BAD_FLAGS.has(f))) return "bad";
  if (flags.some((f) => WARN_FLAGS.has(f))) return "warn";
  return "ok";
}

function severityColor(sev) {
  return { ok: "#2e7d32", warn: "#f9a825", bad: "#c62828" }[sev];
}

function renderMap(segments) {
  trailLayer.clearLayers();
  const bounds = [];
  for (const seg of segments) {
    const sev = segmentSeverity(seg.flags);
    const latlngs = [seg.start, seg.end];
    L.polyline(latlngs, { color: severityColor(sev), weight: 5 }).addTo(trailLayer)
      .bindPopup(
        `Segment ${seg.index}: ${seg.length_m} m, helning ${seg.grade_pct}%` +
          (seg.flags.length ? `<br>${seg.flags.map((f) => FLAG_LABELS[f] || f).join("<br>")}` : "<br>Ingen funn")
      );
    bounds.push(latlngs[0], latlngs[1]);
  }
  if (bounds.length) map.fitBounds(bounds, { padding: [20, 20] });
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
  `;
}

function setStatus(message, isError = false) {
  const el = document.getElementById("status");
  el.textContent = message;
  el.className = isError ? "error" : "";
}

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
    trailLayer.clearLayers();
    markerLayer.clearLayers();
  });
});

// ---- Vurder eksisterende trasé ----
analyzeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const trailFile = document.getElementById("trail-file").files[0];
  const demFile = document.getElementById("dem-file").files[0];
  const apiBase = document.getElementById("api-base").value.replace(/\/$/, "");

  if (!trailFile || !demFile) {
    setStatus("Velg både en trasé-fil og en DEM-fil.", true);
    return;
  }

  const formData = new FormData();
  formData.append("trail", trailFile);
  formData.append("dem", demFile);

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
    document.getElementById("download-buttons").hidden = true;
    renderMap(result.segments);
    renderReport(result);
  } catch (err) {
    setStatus(`Feil: ${err.message}`, true);
  }
});

// ---- Foreslå trasé ----
let pickedStart = null;
let pickedEnd = null;
let lastSuggestedRoute = null;

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
    <name>Foreslått trasé</name>
    <trkseg>
${trkpts}
    </trkseg>
  </trk>
</gpx>
`;
}

document.getElementById("download-gpx").addEventListener("click", () => {
  if (!lastSuggestedRoute) return;
  triggerDownload("foreslatt-trase.gpx", buildGpx(lastSuggestedRoute.points), "application/gpx+xml");
});

document.getElementById("download-geojson").addEventListener("click", () => {
  if (!lastSuggestedRoute) return;
  const geojson = {
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: {}, geometry: lastSuggestedRoute.route }],
  };
  triggerDownload("foreslatt-trase.geojson", JSON.stringify(geojson, null, 2), "application/geo+json");
});

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
  const demFile = document.getElementById("suggest-dem-file").files[0];
  const apiBase = document.getElementById("suggest-api-base").value.replace(/\/$/, "");
  const trailType = document.getElementById("trail-type").value;
  const targetGrade = document.getElementById("target-grade").value;

  if (!demFile) {
    setStatus("Velg en DEM-fil.", true);
    return;
  }
  if (!pickedStart || !pickedEnd) {
    setStatus("Klikk et start- og et sluttpunkt i kartet først.", true);
    return;
  }

  const formData = new FormData();
  formData.append("dem", demFile);
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
    lastSuggestedRoute = result;
    document.getElementById("download-buttons").hidden = false;
  } catch (err) {
    setStatus(`Feil: ${err.message}`, true);
  }
});
