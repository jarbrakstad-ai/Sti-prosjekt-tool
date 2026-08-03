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

let trailLayer = L.layerGroup().addTo(map);

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

function renderReport(result) {
  const s = result.summary;
  const report = document.getElementById("report");
  report.innerHTML = `
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

document.getElementById("analyze-form").addEventListener("submit", async (e) => {
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
    renderMap(result.segments);
    renderReport(result);
  } catch (err) {
    setStatus(`Feil: ${err.message}`, true);
  }
});
