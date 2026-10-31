/* SDB Command Deck — client logic (v2 premium) */
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

let STATE = null, FILTER = "all", lastFetchOk = null, lastFetchAt = null;
const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const canHover = () => matchMedia("(hover: hover)").matches;

function fmtClock() {
  const d = new Date();
  document.getElementById("clock").textContent =
    d.toLocaleTimeString("id-ID", {hour12: false});
}
setInterval(fmtClock, 1000); fmtClock();

// Pil "live": status nyata dari fetch terakhir, bukan dekorasi statis.
function tickLive() {
  const el = document.getElementById("live");
  if (!el || lastFetchAt === null) return;
  el.classList.toggle("ok", lastFetchOk === true);
  el.classList.toggle("err", lastFetchOk === false);
  const dtk = Math.max(0, Math.round((Date.now() - lastFetchAt) / 1000));
  const rel = dtk < 2 ? "baru saja" : dtk < 60 ? `${dtk} dtk lalu` : `${Math.round(dtk / 60)} mnt lalu`;
  el.querySelector(".lbl").textContent = lastFetchOk === false ? "API tidak terjangkau" : `diperbarui ${rel}`;
}
setInterval(tickLive, 1000);

// Angka yang murni numerik dianimasikan naik dari nilai lama -> baru (nilai itu sendiri TETAP
// apa adanya dari /api/state; ini hanya transisi visual, bukan mengubah/mengarang angka).
function animateNumber(el, to) {
  const toNum = Number(to);
  const fromNum = Number(el.dataset.v || 0);
  if (!Number.isFinite(toNum) || String(to).includes("/") || reduceMotion()) {
    el.textContent = to; el.dataset.v = toNum || 0; return;
  }
  el.dataset.v = toNum;
  const t0 = performance.now(), dur = 650;
  function step(t) {
    const p = Math.min(1, (t - t0) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(fromNum + (toNum - fromNum) * eased);
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

async function load() {
  try {
    const r = await fetch("/api/state", {cache: "no-store"});
    STATE = await r.json();
    lastFetchOk = true;
  } catch (e) {
    lastFetchOk = false;
    if (!STATE) {
      document.getElementById("kpis").innerHTML =
        `<div class="kpi"><b>—</b><span>API tidak terjangkau</span></div>`;
    }
    lastFetchAt = Date.now(); tickLive();
    return;
  }
  lastFetchAt = Date.now(); tickLive();
  render();
}

function render() {
  const P = STATE.profiles || [];
  const okN = P.filter(p => p.health === "ok").length;
  const healthKnown = P.some(p => p.health !== "unknown");
  const pongPct = healthKnown && P.length ? Math.round((okN / P.length) * 100) : 0;
  const kpis = [
    {id: "k-profil", b: P.length, s: "Profil Terhubung", c: "var(--acc)", pct: 100},
    {id: "k-pong", b: healthKnown ? `${okN}/${P.length}` : "—", s: "PONG 24 Jam", c: "var(--good)", pct: pongPct},
    {id: "k-model", b: new Set(P.map(p => p.model_id)).size, s: "Model Aktif", c: "var(--acc2)", pct: 100},
    {id: "k-tahap", b: 16, s: "Alur Tahapan", c: "var(--glm)", pct: 100},
    {id: "k-divisi", b: 12, s: "Divisi D0–D11", c: "var(--warn)", pct: 100}
  ];
  const kpisEl = document.getElementById("kpis");
  const prevVals = {};
  kpis.forEach(k => {
    const old = document.getElementById(k.id);
    if (old && old.dataset.v !== undefined) prevVals[k.id] = old.dataset.v;
  });
  kpisEl.innerHTML = kpis.map(k =>
    `<div class="kpi" style="--kc:${k.c}"><b id="${k.id}" data-v="${prevVals[k.id] ?? 0}">${prevVals[k.id] ?? 0}</b><span>${k.s}</span>
      <div class="bar"><i id="${k.id}-bar" style="width:0%"></i></div></div>`).join("");
  kpis.forEach(k => {
    animateNumber(document.getElementById(k.id), k.b);
    requestAnimationFrame(() => { document.getElementById(k.id + "-bar").style.width = k.pct + "%"; });
  });

  document.getElementById("head").textContent = STATE.head || "—";
  document.getElementById("gen").textContent = "update " + (STATE.generated || "—");
  document.getElementById("lan").innerHTML =
    STATE.lan ? `LAN: <b>${esc(STATE.lan)}</b> — buka di HP (WiFi sama)` : "";

  // cards — latensi dihitung RELATIF terhadap ms terlambat pada daftar yang tampil saat ini
  // (bukan ambang absolut yang dikarang): transparan di label "lat.".
  const list = P.filter(p => FILTER === "all" || famOf(p.model_id) === FILTER);
  const msList = list.map(p => Number(p.ms)).filter(Number.isFinite);
  const maxMs = msList.length ? Math.max(...msList) : 0;
  document.getElementById("grid").innerHTML = list.map(p => {
    const fam = famOf(p.model_id);
    const chain = (p.chain || []).map((c, i) =>
      `<span class="fstep${i === 0 ? " on" : ""}"><b>${esc(c.provider)}</b>${c.model ? " · " + esc(c.model) : ""}</span>`
    ).join(`<span class="arrow">→</span>`) || `<span class="fstep">tanpa fallback</span>`;
    const msNum = Number(p.ms);
    const latPct = maxMs && Number.isFinite(msNum) ? Math.max(6, Math.round((msNum / maxMs) * 100)) : null;
    return `<article class="card ${p.health === "fail" ? "fail" : ""}" style="--fc:${FAM[fam].color}">
      <div class="chip-row">
        <div class="div-chips">${(p.divisions || "").split(" ").map(d =>
          `<span class="chip">${esc(d)}</span>`).join("")}</div>
        <span class="dot ${esc(p.health)}" title="health: ${esc(p.health)}"></span>
      </div>
      <h3>${esc(p.label)}</h3>
      <div class="role">${esc(p.role)} · <code>${esc(p.id)}</code></div>
      <div class="model-line">
        <span class="fam" style="background:${FAM[fam].color};color:${FAM[fam].color}"></span>
        <b>${esc(p.model)}</b>
        <span class="prov">${esc(p.provider)}${p.provider_url ? ` · ${esc(p.provider_url)}` : ""}</span>
      </div>
      <div class="chain"><div class="lbl">Fallback chain</div>
        <div class="flowline">${chain}</div></div>
      <div class="meta">${p.checked ? `PONG ${esc(String(p.checked).slice(11, 16))} · ${esc(p.ms)} ms` :
        "health: belum diukur"}${latPct !== null ? `<span class="lat" title="latensi relatif thd. profil terlambat saat ini"><i style="width:${latPct}%"></i></span>` : ""}</div>
    </article>`;
  }).join("");
  if (canHover() && !reduceMotion()) attachTilt();

  // 16-stage flow — referensi pipa statis (bukan klaim tahap aktif; backend tak melaporkannya)
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

// tilt 3D ringan — murni dekoratif, dimatikan di sentuh/prefers-reduced-motion
function attachTilt() {
  document.querySelectorAll(".grid .card").forEach(card => {
    card.onmousemove = (e) => {
      const r = card.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5, py = (e.clientY - r.top) / r.height - 0.5;
      card.style.transform = `rotateX(${(-py * 5).toFixed(2)}deg) rotateY(${(px * 5).toFixed(2)}deg) translateZ(0)`;
    };
    card.onmouseleave = () => { card.style.transform = ""; };
  });
}

// tabs — indikator geser diukur dari posisi tab aktif sungguhan (bukan animasi dikarang)
function positionIndicator(btn) {
  const tabs = document.getElementById("tabs");
  let ind = document.getElementById("tab-ind");
  if (!ind) {
    ind = document.createElement("div"); ind.id = "tab-ind"; ind.className = "tab-ind";
    tabs.insertBefore(ind, tabs.firstChild);
  }
  ind.style.width = btn.offsetWidth + "px";
  ind.style.height = btn.offsetHeight + "px";
  ind.style.top = btn.offsetTop + "px";
  ind.style.transform = `translateX(${btn.offsetLeft}px)`;
}
document.getElementById("tabs").addEventListener("click", e => {
  const b = e.target.closest(".tab");
  if (!b) return;
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("on"));
  b.classList.add("on");
  positionIndicator(b);
  FILTER = b.dataset.f;
  render();
});
window.addEventListener("resize", () => {
  const on = document.querySelector(".tab.on");
  if (on) positionIndicator(on);
});
window.addEventListener("load", () => {
  const on = document.querySelector(".tab.on");
  if (on) positionIndicator(on);
});

// HP mode
document.getElementById("lanmode").addEventListener("change", e => {
  document.body.classList.toggle("compact", e.target.checked);
});

load();
setInterval(load, 60000); // auto-refresh 60s
