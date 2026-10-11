// SDB Workspace — UI fungsional: chat Kapten -> draft Gate #0 -> approve -> tahap proyek; kartu karakter; musik lo-fi.
import { createWorld, ROOMS } from './world.js';
import { CAST } from './chars.js';

const $ = (s, r = document) => r.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h !== undefined) e.innerHTML = h; return e; };
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const API = '/api/ws';
let TOKEN = localStorage.getItem('sdb_token') || '';
let state = { profiles: [], agents: {} }, projects = [], STAGEDEF = [];

function toast(t, ms = 2600) { const e = $('#toast'); e.textContent = t; e.classList.add('on'); clearTimeout(toast.t); toast.t = setTimeout(() => e.classList.remove('on'), ms); }

async function api(path, body) {
  const r = await fetch(API + path, { method: body ? 'POST' : 'GET', headers: { 'X-SDB-Token': TOKEN, ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined, cache: 'no-store' });
  const d = await r.json().catch(() => ({}));
  if (r.status === 401) { showGate(); throw new Error('PIN diperlukan'); }
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
  return d;
}
function showGate() { $('#gate').classList.add('on'); }
$('#pinok').onclick = () => { TOKEN = $('#pinin').value.trim(); localStorage.setItem('sdb_token', TOKEN); $('#gate').classList.remove('on'); boot2(); };

// ------------------------------------------------------------------ dunia
const world = createWorld($('#stage'));
window.__world = world;
if (new URLSearchParams(location.search).get('den') === '1') { world.setDen(true); world.snap(); }
world.on('ready', () => { document.documentElement.setAttribute('data-stats', JSON.stringify(world.stats())); });
world.on('ready', () => setTimeout(() => $('#load').classList.add('off'), 350));
world.on('select', (s) => showCard(s));
world.on('den', (on) => $('#bDen').classList.toggle('on', on));
world.on('inside', (on) => { $('#bIn').classList.toggle('on', on); $('#dpad').classList.toggle('on', on); const h = $('#hint'); h.style.display = on ? 'block' : 'none'; h.textContent = 'WASD / panah untuk berjalan · seret mouse/jari untuk menoleh · tekan “Masuk” lagi untuk keluar'; });

// ------------------------------------------------------------------ warna avatar & util
const COLORS = { owner: '#e8483f', orch: '#26324f', arch: '#f08a35', front: '#f2b640', build: '#1f9fa8', qa: '#4fae4f', sec: '#7a4aa8', aud: '#2b4a8a', ops: '#f5c542', rec: '#4a5a9a', grd: '#c4412f' };
const initials = (n) => n.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();
const profState = (pid) => state.profiles.find((p) => p.id === pid);
function healthBadge(pid) {
  if (!pid) return '<span class="pill deco">Owner · manusia</span>';
  const p = profState(pid);
  if (!p) return '<span class="pill">belum ada data probe</span>';
  const age = state.health_age_h != null ? ` · probe ${state.health_age_h < 1 ? '<1' : Math.round(state.health_age_h)} jam lalu` : '';
  return p.health === 'ok' ? `<span class="pill ok">✔ PONG ${esc(p.ms ?? '?')} ms</span><span style="color:var(--mute);font-size:12px">${age}</span>` : `<span class="pill bad">✖ probe gagal</span><span style="color:var(--mute);font-size:12px">${age}</span>`;
}

// ------------------------------------------------------------------ kartu info
function showCard(sel) {
  const c = $('#card'); c.classList.add('on');
  if (sel.kind === 'actor') {
    const sp = CAST.find((x) => x.id === sel.id) || { name: 'Mimi', title: 'Barista (dekoratif)', persona: 'Pegawai kafe. Hanya hiasan.', routine: [] };
    const p = profState(sp.profile);
    const act = world.A[sel.id];
    c.innerHTML = `<button class="x" id="cx">×</button><h3>${esc(sp.name)}</h3><div class="sub">${esc(sp.title)}</div>
      <div>${healthBadge(sp.profile)} ${p ? `<span class="pill">${esc(p.model || '')}</span>` : ''}</div>
      ${sp.profile ? `<div class="sec"><h5>Profil Hermes</h5><div class="kv"><span>profil</span><b>${esc(sp.profile)}</b></div></div>` : ''}
      <div class="sec"><h5>Peran &amp; kepribadian <span class="pill deco">karakter fiksi</span></h5>${esc(sp.persona)}</div>
      <div class="sec"><h5>Rutinitas <span class="pill deco">dekoratif</span></h5><ul>${(sp.routine || []).map((r) => `<li>${esc(r)}</li>`).join('')}</ul>
      <div style="color:var(--mute);font-size:12px;margin-top:4px">Gerakan di layar hanyalah animasi — bukan tanda agent sedang bekerja.</div></div>
      <div class="sec"><h5>Tugas terverifikasi</h5>${taskFor(sp)}</div>`;
  } else if (sel.kind === 'room') {
    if (sel.id === 'den') {
      c.innerHTML = `<button class="x" id="cx">×</button><h3>Ruang Koordinasi</h3><div class="sub">basement · Kapten Orka (Orchestrator)</div>
        <div class="sec"><h5>Papan 16 tahap</h5>Tabel bercahaya di meja = 16 tahap pipeline SDB. Cahaya berdenyut adalah dekorasi; status tahap proyek nyata ada di tab <b>Proyek</b>.</div>
        <div class="sec"><button class="btn pri" id="goChat">Diskusi dengan Kapten</button></div>`;
    } else {
      const r = ROOMS.find((x) => x.id === sel.id), pr = r.project ? projects.find((p) => p.id === r.project) : null;
      let body = '';
      if (r.ghost) body = `<div class="sec"><span class="pill sample">CONTOH</span> Ruang ini sengaja kosong untuk menunjukkan bentuk ruang proyek baru. Ruang proyek sungguhan dibuat otomatis saat kamu meng-approve draft ide baru.</div>`;
      else if (pr) {
        const f = pr.facts || {};
        body = `<div class="sec"><h5>Proyek nyata (dibaca dari disk)</h5><div class="kv"><span>folder</span><b>${esc(pr.path)}</b><span>ada</span><b>${f.exists ? 'ya' : 'TIDAK'}</b>${f.head ? `<span>commit</span><b>${esc(f.head)}</b>` : ''}${f.dirty != null ? `<span>perubahan lokal</span><b>${f.dirty ? 'ada' : 'bersih'}</b>` : ''}</div></div>
        <div class="sec"><h5>Tahap pipeline</h5>${pr.done}/16 selesai (file dokumen nyata). <button class="btn sm" id="goProj" data-p="${esc(pr.id)}">Buka tab Proyek</button></div>`;
      } else body = `<div class="sec"><div style="color:var(--mute)">${esc(r.name)} — ruang pendukung.</div></div>`;
      c.innerHTML = `<button class="x" id="cx">×</button><h3>${esc(r.name)}</h3><div class="sub">${r.project ? 'ruang proyek' : (r.ghost ? 'contoh' : 'ruang tim')}</div>${body}`;
    }
  }
  $('#cx').onclick = () => { c.classList.remove('on'); };
  const gc = $('#goChat'); if (gc) gc.onclick = () => { panelOpen(true); tab('chat'); $('#msg').focus(); };
  const gp = $('#goProj'); if (gp) gp.onclick = () => { panelOpen(true); tab('proj'); };
}
function taskFor(sp) {
  if (!sp.profile) return 'Memutuskan arah & menyetujui Gate #0 di panel Diskusi.';
  const mine = [];
  projects.forEach((p) => p.stages.forEach((s) => { if (s.profile === sp.profile && s.state !== 'todo') mine.push(`${p.name} · tahap ${s.n} ${s.name} (${s.state === 'done' ? 'dokumen ada' : 'brief ada'})`); }));
  return mine.length ? `<ul>${mine.slice(0, 6).map((m) => `<li>${esc(m)}</li>`).join('')}</ul>` : '<span style="color:var(--mute)">Belum ada tahap yang dikerjakan agent ini di proyek mana pun.</span>';
}

// ------------------------------------------------------------------ panel & tab
function panelOpen(on) { $('#panel').classList.toggle('hide', !on); world.setPanelShift(on && innerWidth > 820 ? 215 : 0); }
function tab(t) { document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('on', b.dataset.t === t)); document.querySelectorAll('.pane').forEach((p) => p.classList.toggle('on', p.id === 'p-' + t)); if (t === 'proj') renderProj(); if (t === 'team') renderTeam(); }
document.querySelectorAll('.tabs button').forEach((b) => (b.onclick = () => tab(b.dataset.t)));
$('#bPanel').onclick = () => panelOpen($('#panel').classList.contains('hide'));
if (innerWidth < 820) panelOpen(false); else world.setPanelShift(215);

// ------------------------------------------------------------------ tim
function renderTeam() {
  const p = $('#p-team'); p.innerHTML = '';
  const pinBox = el('div', 'proj', `<b>PIN perangkat lain</b><span id="pinshow" style="color:var(--mute);font-size:13px">…</span>`); p.appendChild(pinBox);
  fetch(API + '/whoami').then((r) => r.json()).then((d) => { $('#pinshow').innerHTML = d.local ? `Buka <b>http://${esc(state.lan || location.host)}</b> di HP, lalu masukkan PIN: <b style="font-size:18px;letter-spacing:2px">${esc(d.token)}</b>` : 'PIN hanya terlihat dari PC server.'; });
  CAST.forEach((c) => {
    const m = el('div', 'mem', `<div class="av" style="background:${COLORS[c.id]}">${esc(initials(c.name))}</div><div style="flex:1;min-width:0"><b>${esc(c.name)}</b><div style="color:var(--mute);font-size:12.5px">${esc(c.title)}</div></div><div style="text-align:right;font-size:12px">${c.profile ? (profState(c.profile)?.health === 'ok' ? '<span class="dot ok"></span>PONG' : '<span class="dot"></span>—') : 'manusia'}</div>`);
    m.onclick = () => world.select('actor', c.id); p.appendChild(m);
  });
}

// ------------------------------------------------------------------ proyek
let jobsPoll = null;
function stageChip(pr, s, nextN) {
  const b = el('button', 'st ' + s.state + (s.n === nextN ? ' next' : ''), s.n);
  b.title = `${s.n} ${s.name} · ${s.profile} · ${s.kind === 'doc' ? 'dokumen (bisa dari web)' : 'eksekusi (brief serah-terima)'} · ${s.state}`;
  b.onclick = async () => {
    if (s.file) { try { const d = await api(`/artifact?project=${encodeURIComponent(pr.id)}&file=${encodeURIComponent(s.file)}`); modal(`${pr.name} · ${s.n} ${s.name}`, d.text); } catch (e) { toast(e.message); } }
    else toast(`Tahap ${s.n} ${s.name} belum dikerjakan (${s.profile})`);
  };
  return b;
}
async function renderProj() {
  const p = $('#p-proj');
  try { const d = await api('/projects'); projects = d.projects; STAGEDEF = d.stages; } catch (e) { p.innerHTML = `<div class="msg sys">${esc(e.message)}</div>`; return; }
  world.setProjects(projects);
  p.innerHTML = '';
  if (!projects.length) p.appendChild(el('div', 'msg sys', 'Belum ada proyek.'));
  projects.forEach((pr) => {
    const nextI = pr.stages.findIndex((s) => s.state !== 'done'), nextN = nextI < 0 ? null : pr.stages[nextI].n, nextS = nextI < 0 ? null : pr.stages[nextI];
    const card = el('div', 'proj');
    const f = pr.facts || {};
    card.innerHTML = `<h4>${esc(pr.name)} <span class="pill ${pr.kind === 'real' ? 'ok' : ''}">${pr.kind === 'real' ? 'repo nyata' : 'ide baru'}</span> <span class="pill">${pr.done}/16</span></h4>
      ${pr.path ? `<div class="kv"><span>folder</span><b>${esc(pr.path)}</b>${f.head ? `<span>commit</span><b>${esc(f.head)}</b>` : ''}</div>` : '<div style="color:var(--mute);font-size:13px">Belum punya repo — dibuat saat tahap Build.</div>'}`;
    const g = el('div', 'stages'); pr.stages.forEach((s) => g.appendChild(stageChip(pr, s, nextN))); card.appendChild(g);
    const row = el('div', 'row');
    row.style.cssText = 'display:flex;gap:8px;align-items:center;flex-wrap:wrap';
    if (nextS && pr.stages[0].state === 'done') {
      const btn = el('button', 'btn pri sm', nextS.kind === 'doc' ? `▶ Jalankan tahap ${nextS.n} ${esc(nextS.name)}` : `📝 Buat brief tahap ${nextS.n} ${esc(nextS.name)}`);
      btn.onclick = () => runStage(pr, nextS, btn); row.appendChild(btn);
      row.appendChild(el('span', '', `<span style="color:var(--mute);font-size:12px">${esc(nextS.profile)}${nextS.kind === 'exec' ? ' · tidak dieksekusi dari web' : ''}</span>`));
    } else if (!nextS) row.appendChild(el('span', 'pill ok', 'semua tahap selesai'));
    else row.appendChild(el('span', 'pill', 'menunggu approve intake (Gate #0)'));
    card.appendChild(row); p.appendChild(card);
  });
  p.appendChild(el('div', 'msg sys', 'Hijau = dokumen ada di disk · Kuning = brief serah-terima ada, eksekusi belum · Abu = belum. Status dibaca dari file, bukan klaim.'));
}
async function runStage(pr, st, btn) {
  btn.disabled = true;
  try {
    const d = await api('/stage/run', { project: pr.id, stage: st.n });
    if (!d.job) { toast('Brief dibuat'); return renderProj(); }
    toast(`Tahap ${st.n} berjalan (${st.profile})…`); btn.textContent = '⏳ berjalan…';
    await waitJob(d.job, 480);
    toast(`Tahap ${st.n} selesai`);
  } catch (e) { toast(e.message, 5000); }
  renderProj();
}
async function waitJob(id, maxS) {
  const t0 = Date.now();
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000));
    const j = await api('/job/' + id);
    if (j.status === 'done') return j;
    if (j.status === 'error') throw new Error(j.error || 'job gagal');
    if ((Date.now() - t0) / 1000 > maxS) throw new Error('timeout menunggu job');
  }
}
function modal(title, text) { $('#mt').textContent = title; $('#mb').textContent = text; $('#modal').classList.add('on'); }
$('#mx').onclick = () => $('#modal').classList.remove('on');
$('#modal').onclick = (e) => { if (e.target.id === 'modal') $('#modal').classList.remove('on'); };

// ------------------------------------------------------------------ chat
let CID = localStorage.getItem('sdb_cid') || ('c' + Math.random().toString(36).slice(2, 10));
localStorage.setItem('sdb_cid', CID);
function fillScope() {
  const s = $('#scope'); const cur = s.value; s.innerHTML = '<option value="baru">💡 Ide proyek BARU</option>';
  projects.forEach((p) => s.insertAdjacentHTML('beforeend', `<option value="${esc(p.id)}">📁 ${esc(p.name)}</option>`)); if (cur) s.value = cur;
}
function addMsg(cls, text) { const m = el('div', 'msg ' + cls); m.textContent = text; $('#log').appendChild(m); $('#log').scrollTop = 1e9; return m; }
function addDraft(d) {
  const x = el('div', 'draft');
  x.innerHTML = `<div><span class="pill sample">DRAFT · belum disetujui</span> <span class="pill">${esc(d.type || '')}</span></div><h4>${esc(d.title)}</h4><div>${esc(d.summary || '')}</div>
    <div><b>Pengguna:</b> ${esc(d.users || '-')}</div><div><b>Platform:</b> ${esc(d.platform || '-')}</div>
    <div><b>Fitur inti</b><ul>${(d.features || []).map((f) => `<li>${esc(f)}</li>`).join('')}</ul></div>
    ${(d.risks || []).length ? `<div><b>Risiko</b><ul>${d.risks.map((f) => `<li>${esc(f)}</li>`).join('')}</ul></div>` : ''}
    ${(d.open_questions || []).length ? `<div><b>Masih terbuka</b><ul>${d.open_questions.map((f) => `<li>${esc(f)}</li>`).join('')}</ul></div>` : ''}
    <div class="row"><button class="btn ok sm">✔ Approve (Gate #0)</button><button class="btn sm">✎ Revisi lewat chat</button></div>`;
  const [ok, rev] = x.querySelectorAll('button');
  ok.onclick = async () => { ok.disabled = true; try { const r = await api('/draft/approve', { cid: CID, draft_id: d.id }); x.querySelector('.pill').className = 'pill ok'; x.querySelector('.pill').textContent = 'DISETUJUI · intake tersimpan'; toast('Disetujui → proyek ' + r.project); ok.remove(); rev.remove(); await renderProj(); fillScope(); tab('proj'); } catch (e) { ok.disabled = false; toast(e.message, 5000); } };
  rev.onclick = () => { $('#msg').focus(); $('#msg').placeholder = 'Tulis revisi untuk draft…'; };
  $('#log').appendChild(x); $('#log').scrollTop = 1e9;
}
$('#send').onclick = async () => {
  const ta = $('#msg'), text = ta.value.trim(); if (!text) return;
  ta.value = ''; addMsg('u', text); const wait = addMsg('k typing', 'Kapten berpikir'); $('#send').disabled = true; $('#chatst').textContent = 'menunggu model…';
  try {
    const r = await api('/chat', { cid: CID, scope: $('#scope').value, message: text });
    const j = await waitJob(r.job, 240); wait.remove();
    addMsg('k', j.result.reply || '(kosong)'); if (j.result.draft) addDraft(j.result.draft);
    $('#chatst').textContent = `dijawab ${j.secs}s`;
  } catch (e) { wait.remove(); addMsg('sys', '⚠ ' + e.message + ' — coba lagi.'); $('#chatst').textContent = ''; }
  $('#send').disabled = false;
};
$('#msg').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) $('#send').click(); });
async function loadHistory() {
  try {
    const h = await api('/chat/history?cid=' + CID);
    (h.messages || []).forEach((m) => addMsg(m.role === 'user' ? 'u' : 'k', m.text));
    (h.drafts || []).filter((d) => d.status === 'pending').forEach(addDraft);
  } catch { /* abaikan */ }
}

// ------------------------------------------------------------------ tombol dunia
$('#bIn').onclick = () => world.setInside(!world.inside);
$('#bDen').onclick = () => { const on = world.toggleDen(); if (on) world.select('room', 'den'); else $('#card').classList.remove('on'); };
$('#bReset').onclick = () => { world.reset(); $('#card').classList.remove('on'); };
document.querySelectorAll('#dpad button').forEach((b) => {
  const set = (v) => { const d = b.dataset.d; world.setJoy(d === 'l' ? -v : d === 'r' ? v : 0, d === 'f' ? v : d === 'b' ? -v : 0); };
  b.addEventListener('pointerdown', (e) => { e.preventDefault(); set(1); }); ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) => b.addEventListener(ev, () => set(0)));
});

// ------------------------------------------------------------------ audio (dibuat di browser, tanpa file)
let AC = null, master = null, musicOn = false, muted = false, seq = null, sfxT = null;
function ensureAudio() {
  if (AC) return; AC = new (window.AudioContext || window.webkitAudioContext)(); master = AC.createGain(); master.gain.value = 0.5;
  const lp = AC.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 2200; master.connect(lp); lp.connect(AC.destination);
}
const N = (m) => 440 * Math.pow(2, (m - 69) / 12);
function tone(freq, t, dur, type, vol, dest) { const o = AC.createOscillator(), g = AC.createGain(); o.type = type; o.frequency.value = freq; g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vol, t + 0.03); g.gain.exponentialRampToValueAtTime(0.0001, t + dur); o.connect(g); g.connect(dest || master); o.start(t); o.stop(t + dur + 0.05); }
const CH = [[45, 52, 57, 60], [43, 50, 55, 59], [48, 55, 60, 64], [41, 48, 53, 57]]; // A-F-C-G major
const RIFF = [57, 57, 64, 57, 62, 60, 57, 55], MEL = [69, 72, 76, 72, 74, 72, 69, 67];
function startMusic() {
  ensureAudio(); document.documentElement.dataset.music = '1'; if (AC.state === 'suspended') AC.resume(); let step = 0, next = AC.currentTime + 0.1;
  seq = setInterval(() => {
    while (next < AC.currentTime + 0.6) {
      const bar = Math.floor(step / 16) % 4, beat = Math.floor(step / 2) % 8;
      if (step % 2 === 0) tone(N(CH[bar][0] - 12), next, 0.16, 'sawtooth', 0.10); // driving bass
      if (beat === 0) CH[bar].forEach((m, i) => tone(N(m), next + i * 0.012, 1.6, 'square', 0.03)); // stab
      if (beat % 2 === 1) tone(80 + Math.random() * 30, next, 0.05, 'square', 0.05); // snare-ish
      if (beat % 4 === 2) { const n = RIFF[beat % 8] + (bar % 2 ? 2 : 0); tone(N(n), next, 0.14, 'sawtooth', 0.05); tone(N(n + 12), next + 0.08, 0.12, 'sawtooth', 0.04); } // riff gitar
      if (beat % 4 === 0 && Math.random() < 0.8) tone(N(MEL[(step / 2 + bar * 3) % 8 | 0]), next, 0.3, 'triangle', 0.045); // melodi
      step++; next += 0.1875; // 160 BPM
    }
  }, 120);
}
function stopMusic() { clearInterval(seq); seq = null; delete document.documentElement.dataset.music; }
function sfx() { if (!AC || muted) return; const t = AC.currentTime, k = Math.random(); if (k < 0.4) { tone(1318, t, 0.25, 'sine', 0.05); tone(1760, t + 0.12, 0.3, 'sine', 0.04); } else if (k < 0.7) { for (let i = 0; i < 3; i++) tone(180 + Math.random() * 60, t + i * 0.09, 0.05, 'square', 0.025); } else { tone(660, t, 0.18, 'triangle', 0.05); } }
$('#bMusic').onclick = () => { musicOn = !musicOn; $('#bMusic').classList.toggle('on', musicOn); if (musicOn) { startMusic(); clearInterval(sfxT); sfxT = setInterval(sfx, 9000 + Math.random() * 6000); } else { stopMusic(); clearInterval(sfxT); } if (musicOn && muted) $('#bMute').click(); };
$('#bMute').onclick = () => { muted = !muted; $('#bMute').classList.toggle('on', muted); $('#bMute').firstChild.textContent = muted ? '🔇' : '🔊'; if (master) master.gain.value = muted ? 0 : 0.5; };

// parameter QA/tautan: ?focus=<id karakter>&z=<zoom>&panel=0
(() => { const q = new URLSearchParams(location.search), f = q.get('focus'); if (q.get('panel') === '0') panelOpen(false);
  if (f) setTimeout(() => { const a = Object.hasOwn(world.A, f) ? world.A[f] : null; const z = Number(q.get('z') || 3.2); if (a) { world.focusOn(a.g.position.x, a.g.position.y + 1.2, a.g.position.z, Number.isFinite(z) && z > 0.5 && z < 60 ? z : 3.2); world.select('actor', f); if (q.get('snap')) setTimeout(() => world.snap(), 150); } }, 800); })();

// ------------------------------------------------------------------ boot
async function refreshState() { try { const r = await fetch('/api/state', { cache: 'no-store' }); state = await r.json(); world.setState(state); } catch { /* offline */ } }
async function boot2() {
  await refreshState(); try { await renderProj(); } catch { /* butuh PIN */ }
  fillScope(); await loadHistory(); renderTeam();
}
(async () => {
  try {
    const who = await (await fetch(API + '/whoami')).json();
    if (who.local && who.token) { TOKEN = who.token; localStorage.setItem('sdb_token', TOKEN); }
    if (!TOKEN) showGate();
  } catch { showGate(); }
  boot2(); setInterval(refreshState, 60000);
})();
