/* SDB Command Deck — client logic */
const FAM = {
  glm: {name: "GLM 5.3 Flash", color: "var(--glm)"},
  ds: {name: "DeepSeek V4.1 Flash", color: "var(--ds)"},
  ant: {name: "Sonnet 5.5", color: "var(--ant)"},
  opu: {name: "Opus 5.5", color: "var(--opu)"},
  gpt: {name: "GPT-5.6 Sol", color: "var(--gpt)"},
  x: {name: "?", color: "var(--dim)"}
};
// Semua data /api/state berasal dari config.yaml/health.json profil -> perlakukan sebagai tak tepercaya.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
function famOf(id) {
  if (/glm/i.test(id)) return "glm";
  if (/deepseek|ds-flash/i.test(id)) return "ds";
  if (/opus/i.test(id)) return "opu";
  if (/sonnet/i.test(id)) return "ant";
  if (/gpt|sol/i.test(id)) return "gpt";
  return "x";
}
const STAGES = [
  ["01","Intake","ds"],["02","Clarify","ds"],["03","Scope","ds"],["04","ADR/Design","ant"],
  ["05","Recon","glm"],["06","Impl Plan","ds"],["07","Build","ds"],["08","Review","ant"],
  ["09","QA/E2E","ant"],["10","Security","opu"],["11","Audit","opu"],["12","Verdict","opu"],
  ["13","Dashboard","ant"],["14","Release","ds"],["15","Deploy","ds"],["16","Handover","ds"]
];

let STATE = null, FILTER = "all";

function fmtClock() {
  const d = new Date();
  document.getElementById("clock").textContent =
    d.toLocaleTimeString("id-ID", {hour12: false});
}
setInterval(fmtClock, 1000); fmtClock();

async function load() {
  try {
    const r = await fetch("/api/state", {cache: "no-store"});
    STATE = await r.json();
  } catch (e) {
    document.getElementById("kpis").innerHTML =
      `<div class="kpi"><b>—</b><span>API tidak terjangkau</span></div>`;
    return;
  }
  render();
}

function render() {
  const P = STATE.profiles || [];
  const okN = P.filter(p => p.health === "ok").length;
  const healthKnown = P.some(p => p.health !== "unknown");
  const kpis = [
    {b: P.length, s: "Profil Terhubung", c: "var(--acc)"},
    {b: healthKnown ? `${okN}/${P.length}` : "—", s: "PONG 24 Jam", c: "var(--good)"},
    {b: new Set(P.map(p => p.model_id)).size, s: "Model Aktif", c: "var(--acc2)"},
    {b: "16", s: "Alur Tahapan", c: "var(--glm)"},
    {b: "12", s: "Divisi D0–D11", c: "var(--warn)"}
  ];
  document.getElementById("kpis").innerHTML = kpis.map(k =>
    `<div class="kpi" style="--kc:${k.c}"><b>${k.b}</b><span>${k.s}</span></div>`).join("");

  document.getElementById("head").textContent = STATE.head || "—";
  document.getElementById("gen").textContent = "update " + (STATE.generated || "—");
  document.getElementById("lan").innerHTML =
    STATE.lan ? `LAN: <b>${esc(STATE.lan)}</b> — buka di HP (WiFi sama)` : "";

  // cards
  const list = P.filter(p => FILTER === "all" || famOf(p.model_id) === FILTER);
  document.getElementById("grid").innerHTML = list.map(p => {
    const fam = famOf(p.model_id);
    const chain = (p.chain || []).map((c, i) =>
      `<span class="fstep${i === 0 ? " on" : ""}"><b>${esc(c.provider)}</b>${c.model ? " · " + esc(c.model) : ""}</span>`
    ).join(`<span class="arrow">→</span>`) || `<span class="fstep">tanpa fallback</span>`;
    return `<article class="card ${p.health === "fail" ? "fail" : ""}" style="--fc:${FAM[fam].color}">
      <div class="chip-row">
        <div class="div-chips">${(p.divisions || "").split(" ").map(d =>
          `<span class="chip">${esc(d)}</span>`).join("")}</div>
        <span class="dot ${esc(p.health)}" title="health: ${esc(p.health)}"></span>
      </div>
      <h3>${esc(p.label)}</h3>
      <div class="role">${esc(p.role)} · <code>${esc(p.id)}</code></div>
      <div class="model-line">
        <span class="fam" style="background:${FAM[fam].color}"></span>
        <b>${esc(p.model)}</b>
        <span class="prov">${esc(p.provider)}${p.provider_url ? ` · ${esc(p.provider_url)}` : ""}</span>
      </div>
      <div class="chain"><div class="lbl">Fallback chain</div>
        <div class="flowline">${chain}</div></div>
      <div class="meta">${p.checked ? `PONG ${esc(String(p.checked).slice(11, 16))} · ${esc(p.ms)} ms` :
        "health: belum diukur"}</div>
    </article>`;
  }).join("");

  // 16-stage flow
  document.getElementById("flow").innerHTML = STAGES.map(([n, t, f]) =>
    `<div class="st ${f}" title="${FAM[f].name}"><b>${n} ${t}</b>${FAM[f].name}</div>`
  ).join(`<span class="arrow">→</span>`);

  // divisions
  const DIVS = [
    ["D0","Intake"],["D1","Recon"],["D2","Plan"],["D3","Arch"],
    ["D4","FE Build"],["D5","BE Build"],["D6","Review"],["D7","QA"],
    ["D8","Security"],["D9","Audit"],["D10","Release"],["D11","Docs"]
  ];
  document.getElementById("divs").innerHTML = DIVS.map(([d, n]) =>
    `<div class="dv"><b>${d}</b><span>${n}</span></div>`).join("");
}

// tabs
document.getElementById("tabs").addEventListener("click", e => {
  const b = e.target.closest(".tab");
  if (!b) return;
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("on"));
  b.classList.add("on");
  FILTER = b.dataset.f;
  render();
});

// HP mode
document.getElementById("lanmode").addEventListener("change", e => {
  document.body.classList.toggle("compact", e.target.checked);
});

load();
setInterval(load, 60000); // auto-refresh 60s
