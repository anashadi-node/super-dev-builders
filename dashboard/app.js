/* Command Deck SDB — v3.1
 * Sumber kebenaran: docs/WORKFLOW_SKENARIO.md (§1, §6, §7), docs/DIVISIONS.md,
 * dan /api/state (live). Perintah di UI diverifikasi terhadap scripts/*.py
 * (--help) — bukan dari ringkasan dokumen. Lihat tab "Kebijakan Rute".
 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

  /* ---------------------------------------------------------------- data */

  // 18 baris, urut dan bernama persis seperti `workflow_run.py --list-stages`.
  const STAGES = [
    { c: "01",  n: "User Objective",              d: "D0",  tool: "" },
    { c: "01A", n: "Authorization / Scope Gate",  d: "D1",  tool: "gate_check.py" },
    { c: "01B", n: "Recon / Evidence Package",    d: "D1",  tool: "evidence_lint.py" },
    { c: "02",  n: "Klarifikasi",                 d: "D0",  tool: "" },
    { c: "03",  n: "Research",                    d: "D2",  tool: "" },
    { c: "04",  n: "Architecture + ADR",          d: "D3",  tool: "" },
    { c: "05",  n: "Human Design Approval",       d: "D0",  tool: "manusia" },
    { c: "06",  n: "Implementation Plan",         d: "D5",  tool: "" },
    { c: "07",  n: "Implementasi (FE/BE)",        d: "D4",  tool: "" },
    { c: "08",  n: "Code Review",                 d: "D6",  tool: "" },
    { c: "09",  n: "QA / Integration / E2E",      d: "D7",  tool: "" },
    { c: "10",  n: "Security (SAST/Dep/Secret)",  d: "D8",  tool: "make secrets" },
    { c: "11",  n: "Code Audit & Assurance",      d: "D9",  tool: "" },
    { c: "12",  n: "Release Gate",                d: "D10", tool: "release_check.py" },
    { c: "13",  n: "Human Approval Produksi",     d: "D10", tool: "manusia" },
    { c: "14",  n: "DevOps Deploy",               d: "D10", tool: "" },
    { c: "15",  n: "Observability / Smoke / Rollback", d: "D10", tool: "" },
    { c: "16",  n: "Docs + Handover",             d: "D11", tool: "" },
  ];
  const STAGE_BY = Object.fromEntries(STAGES.map((s) => [s.c, s]));

  const DIVS = [
    { id: "D0",  name: "Master Orchestrator / Product & Planning", owner: "sdb-orchestrator" },
    { id: "D1",  name: "Reverse Engineering & Reconstruction",      owner: "sdb-recon" },
    { id: "D2",  name: "Research",                                 owner: "sdb-orchestrator · sdb-architect" },
    { id: "D3",  name: "Architecture",                             owner: "sdb-architect" },
    { id: "D4",  name: "Engineering — Frontend",                   owner: "sdb-builder" },
    { id: "D5",  name: "Engineering — Backend",                    owner: "sdb-builder" },
    { id: "D6",  name: "Code Review",                              owner: "sdb-reviewer" },
    { id: "D7",  name: "QA / Test",                                owner: "sdb-reviewer" },
    { id: "D8",  name: "Security",                                 owner: "sdb-security" },
    { id: "D9",  name: "Code Audit & Engineering Assurance",        owner: "sdb-security (independen)" },
    { id: "D10", name: "DevOps / Release / Reliability",           owner: "sdb-devops" },
    { id: "D11", name: "Documentation",                            owner: "sdb-devops" },
  ];
  const DIV_BY = Object.fromEntries(DIVS.map((d) => [d.id, d]));

  // §6 — tabel pemetaan apa adanya. `note` dipakai untuk pangkasan sebagian
  // (mis. "07 sebagian") yang tidak boleh disajikan sebagai coret penuh.
  const SCEN = [
    {
      key: "A", icon: "A", title: "Clone / Reverse Engineering", tag: "Rekonstruksi dari contoh",
      risk: "HIGH",
      when: "Anda punya contoh terkirim (screenshot, rekaman, app existing) dan ingin membangun ulang perilakunya — bukan menyalin asetnya.",
      entry: "01A + 01B berat",
      trim: { codes: ["07"], note: "07 hanya bila keluarannya analisis, bukan perangkat lunak." },
      keep: [
        { c: "01A", why: "tanpa Gate #0 PASS seluruh pekerjaan tidak sah" },
        { c: "01B", why: "bukti harus bersih (tanpa token/cookie)" },
        { c: "10",  why: "lisensi, secret, DRM" },
      ],
      keepText: "01A · 01B (bukti bersih) · 10",
      traps: [
        "Jangan melewati login, CAPTCHA, paywall, atau DRM target.",
        "Bukti mentah ≠ ternormalisasi: jalankan evidence_lint.py sebelum dipakai.",
        "Uji paritas perilaku, bukan kemiripan tampilan.",
      ],
      cmds: [
        "cd ~/super-dev-builders",
        "python3 scripts/init_target.py nama-target --mode A",
        "$EDITOR targets/nama-target/authorization.yaml   # isi izin tertulis + scope",
        "python3 scripts/gate_check.py nama-target        # wajib PASS sebelum capture",
        "python3 scripts/capture_web.py --target nama-target \\",
        "    --url https://contoh.tld/halaman-publik --out targets/nama-target/capture",
        "python3 scripts/normalize_capture.py --target nama-target",
        "python3 scripts/evidence_lint.py targets/nama-target",
        "make workflow TARGET=nama-target",
      ],
    },
    {
      key: "B", icon: "B", title: "PRD jadi produk", tag: "Spesifikasi tertulis",
      risk: "MED",
      when: "Anda punya PRD dengan metrik dan cakupan eksplisit. Ini jalur tercepat — selama non-goals ditulis.",
      entry: "01 (disalin dari PRD)",
      trim: { codes: ["03"], note: "03 dilewati hanya bila teknologi sudah dikenal tim." },
      keep: [
        { c: "02", why: "ambiguity dikonfirmasi, bukan ditebak" },
        { c: "05", why: "desain disetujui sebelum dikodekan" },
        { c: "09", why: "tes benar-benar dijalankan" },
        { c: "12", why: "release gate butuh artefak segar" },
      ],
      keepText: "02 · 05 · 09 · 12",
      traps: [
        "Scope creep: tulis non-goals di 01, bukan di kepala.",
        "Release gate menolak artefak kedaluwarsa (--max-age-hours).",
      ],
      cmds: [
        "cd ~/super-dev-builders",
        "python3 scripts/init_target.py nama-target --mode B",
        "python3 scripts/gate_check.py nama-target",
        "python3 scripts/workflow_run.py nama-target",
        "make release-check TARGET=nama-target",
      ],
    },
    {
      key: "C", icon: "C", title: "Ide dari chat", tag: "Belum tertulis",
      risk: "MED",
      when: "Ide masih kasar dan berubah-ubah. Tahap 02 (klarifikasi) dikerjakan berat sebelum apa pun dibangun.",
      entry: "01 + 02 berat",
      trim: { codes: ["01B"], note: "01B ringan bila tak ada target pihak ketiga." },
      keep: [
        { c: "02", why: "klarifikasi wajib — jangan menebak requirement" },
        { c: "05", why: "keputusan desain butuh persetujuan Anda" },
        { c: "09", why: "selesai = ada keluaran tes nyata" },
      ],
      keepText: "02 · 05 · 09",
      traps: [
        "Jangan biarkan agen mengisi kekosongan requirement dengan asumsi.",
        "Ide berubah di tengah jalan → kembali ke 01, bukan menambal di 07.",
      ],
      cmds: [
        "cd ~/super-dev-builders",
        "python3 scripts/init_target.py nama-target --mode B",
        "python3 scripts/gate_check.py nama-target",
        "python3 scripts/workflow_run.py nama-target --list-stages   # cek 18 baris",
        "python3 scripts/workflow_run.py nama-target",
      ],
    },
    {
      key: "GAME", icon: "G", title: "Game", tag: "GDD sebagai 01/01B",
      risk: "MED",
      when: "Game atau prototipe gameplay. Wajib: loop inti terdefinisi, build playable, dan uji performa di perangkat target.",
      entry: "GDD sebagai 01 + 01B",
      trim: { codes: ["03"], note: "03 dilewati bila engine sudah dipilih." },
      keep: [
        { c: "02", why: "loop inti & kontrol harus disepakati" },
        { c: "09", why: "harus playable, bukan hanya kompilasi" },
        { c: "10", why: "aset pihak ketiga & lisensi" },
      ],
      keepText: "02 (loop inti) · 09 (playable) · 10",
      traps: [
        "Pipeline build berbeda per platform — jangan asumsikan satu build untuk semua.",
        "Uji frame time di perangkat target, bukan di laptop dev.",
      ],
      cmds: [
        "cd ~/super-dev-builders",
        "python3 scripts/init_target.py nama-game --mode B",
        "python3 scripts/gate_check.py nama-game",
        "make workflow TARGET=nama-game",
      ],
    },
    {
      key: "MOB", icon: "M", title: "Aplikasi mobile", tag: "Android / iOS",
      risk: "MED",
      when: "Aplikasi mobile native atau lintas-platform. Izin OS dan data pribadi diperiksa di 02 dan 10.",
      entry: "01 + 01B",
      trim: { codes: ["03"], note: "03 dilewati bila stack sudah dikenal." },
      keep: [
        { c: "02", why: "izin OS & data pribadi disepakati lebih awal" },
        { c: "09", why: "uji di perangkat nyata" },
        { c: "10", why: "izin berlebih = temuan keamanan" },
      ],
      keepText: "02 (izin OS) · 09 (perangkat nyata) · 10",
      traps: [
        "Izin berlebih adalah temuan keamanan, bukan detail rilis.",
        "Store review memakan waktu — masukkan ke rencana, bukan kejutan.",
      ],
      cmds: [
        "cd ~/super-dev-builders",
        "python3 scripts/init_target.py nama-app --mode B",
        "python3 scripts/gate_check.py nama-app",
        "make workflow TARGET=nama-app",
      ],
    },
    {
      key: "CLI", icon: "›_", title: "CLI / otomasi internal", tag: "Tanpa UI",
      risk: "LOW",
      when: "Tool baris perintah, skrip operasional, atau layanan internal. Desain sering cukup di kepala — tapi keputusan tetap dicatat.",
      entry: "01",
      trim: { codes: ["04", "05", "06", "11", "13", "14", "15"], note: "ADR (04) dan approval desain (05) dilewati; deploy (14–15) manual." },
      keep: [
        { c: "01A", why: "gate tetap berlaku meski target internal" },
        { c: "09", why: "tes harus dijalankan, bukan diasumsikan" },
        { c: "10", why: "secret scan wajib" },
      ],
      keepText: "01A · 09 · 10",
      traps: [
        "Tanpa 04: keputusan desain tak terdokumentasi dan sulit diubah nanti.",
        "Deploy manual tetap butuh rencana rollback.",
      ],
      cmds: [
        "cd ~/super-dev-builders",
        "python3 scripts/init_target.py nama-tool --mode B",
        "python3 scripts/gate_check.py nama-tool",
        "python3 scripts/workflow_run.py nama-tool",
        "make secrets",
      ],
    },
    {
      key: "DATA", icon: "▦", title: "Data / laporan", tag: "ETL & analitik",
      risk: "MED",
      when: "Pipeline data, laporan berkala, atau analitik. Angka wajib diverifikasi terhadap sampel manual — bukan dipercaya dari pipeline.",
      entry: "01 + 01B",
      trim: { codes: ["05"], note: "07 sebagian: hanya transformasi, bukan aplikasi." },
      keep: [
        { c: "09", why: "verifikasi angka vs sampel manual" },
        { c: "10", why: "PII & secret disaring sebelum normalisasi" },
        { c: "12", why: "laporan keluar lewat release gate" },
      ],
      keepText: "09 (verifikasi angka) · 10",
      traps: [
        "Angka tanpa verifikasi sampel = klaim tanpa bukti.",
        "PII wajib [REDACTED] sebelum bukti disimpan.",
      ],
      cmds: [
        "cd ~/super-dev-builders",
        "python3 scripts/init_target.py nama-data --mode B",
        "python3 scripts/gate_check.py nama-data",
        "python3 scripts/workflow_run.py nama-data",
        "make release-check TARGET=nama-data",
      ],
    },
    {
      key: "REF", icon: "⟳", title: "Refactor / legacy", tag: "Perbaiki yang berjalan",
      risk: "HIGH",
      when: "Mengubah kode lama yang sudah dipakai. Baseline perilaku direkam sebelum satu baris pun diubah.",
      entry: "01B (baseline)",
      trim: { codes: ["03"], note: "04 sebagian: ADR hanya bila arsitektur berubah." },
      keep: [
        { c: "01B", why: "baseline sebelum perubahan" },
        { c: "09", why: "bandingkan perilaku sebelum vs sesudah" },
        { c: "12", why: "release gate sebelum rilis ulang" },
      ],
      keepText: "01B · 09 (bandingkan) · 12",
      traps: [
        "Refactor tanpa baseline = tak bisa dibuktikan tidak ada regresi.",
        "Jangan campur refactor dan fitur baru dalam satu langkah.",
      ],
      cmds: [
        "cd ~/super-dev-builders",
        "make test 2>&1 | tee targets/nama-target/evidence/baseline-test.txt",
        "python3 scripts/init_target.py nama-target --mode B",
        "python3 scripts/gate_check.py nama-target",
        "make workflow TARGET=nama-target",
      ],
    },
    {
      key: "AUD", icon: "◎", title: "Audit sistem berjalan", tag: "Tanpa membangun",
      risk: "LOW",
      when: "Memeriksa sistem atau kode yang sudah ada. Masuk dari 01B, keluar di 11 — tidak ada implementasi.",
      entry: "01B",
      trim: { codes: ["06", "07", "08", "09"], note: "Semua tahap bangun dilewati." },
      keep: [
        { c: "01B", why: "bukti & cakupan akses" },
        { c: "10", why: "temuan keamanan" },
        { c: "11", why: "audit & assurance independen" },
      ],
      keepText: "01B · 10 · 11",
      traps: [
        "Temuan wajib punya bukti dan tingkat keyakinan.",
        "Tanpa akses baca → out of scope, bukan bahan spekulasi.",
      ],
      cmds: [
        "cd ~/super-dev-builders",
        "python3 scripts/init_target.py nama-audit --mode B",
        "python3 scripts/gate_check.py nama-audit",
        "make secrets",
        "python3 scripts/workflow_run.py nama-audit    # berhenti di 11",
      ],
    },
    {
      key: "OPS", icon: "⚙", title: "Operasional / rilis", tag: "Insiden & rilis rutin",
      risk: "LOW",
      when: "Tidak ada pembangunan: rilis rutin, insiden, atau pemeliharaan. Fokus pada smoke test dan rollback.",
      entry: "—",
      trim: { codes: ["01", "01A", "01B", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "16"], note: "Semua tahap bangun; 16 dijalankan bila perilaku berubah." },
      keep: [{ c: "15", why: "smoke test + rollback yang sudah diuji" }],
      keepText: "15 (smoke/rollback)",
      traps: [
        "Rollback harus diuji, bukan diasumsikan bisa.",
        "Satu perubahan per insiden; postmortem tanpa menyalahkan orang.",
      ],
      cmds: [
        "cd ~/super-dev-builders",
        "make doctor          # capability check",
        "make check           # lint + test + drift + hygiene",
        "make release-check TARGET=nama-target",
      ],
    },
  ];
  const SCEN_BY = Object.fromEntries(SCEN.map((s) => [s.key, s]));

  const FATAL = [
    ["Melewati Gate #0 “karena buru-buru”", "Pekerjaan tidak sah, tak bisa diaudit", "gate_check.py sebelum capture apa pun"],
    ["Evidence berisi token / cookie", "Kebocoran kredensial permanen", "evidence_lint.py wajib, [REDACTED]"],
    ["“Selesai” tanpa tes dijalankan", "Klaim palsu", "Tahap 09 hanya hijau bila ada keluaran nyata"],
    ["Deploy semua layanan sekaligus", "Rollback tidak terarah", "Satu layanan per deploy"],
    ["Menilai dari daftar fitur", "Produk terlihat lengkap, tak terpakai", "Nilai dari alur ujung-ke-ujung"],
    ["Desain tidak disetujui lalu dikodekan", "Revisi termahal", "Tahap 05 selalu dijalankan"],
  ];

  const CORE_RULES = [
    "Satu mesin 18 baris untuk semua skenario; yang berubah hanya titik masuk dan tahap yang dipangkas.",
    "Gate #0 tidak pernah dipangkas — ia yang membuat pekerjaan sah.",
    "Klaim “selesai” = artefak + tes dijalankan + persetujuan Anda.",
    "Tahap 05 dan 13 adalah persetujuan manusia, bukan checklist agen.",
    "Runner memeriksa keberadaan artefak, bukan kualitas. MISSING = belum dikerjakan.",
    "Bila perilaku sistem berbeda dari dokumen, yang benar adalah kode dan tesnya — laporkan selisihnya.",
  ];

  const DRIFT = [
    ["sdb workflow --list-stages", "command not found", "python3 scripts/workflow_run.py --list-stages"],
    ["make init TARGET=", "target tidak ada di Makefile", "python3 scripts/init_target.py &lt;slug&gt;"],
    ["sdb gate / sdb-health", "CLI sdb tidak terpasang", "python3 scripts/gate_check.py &lt;slug&gt; · make doctor"],
  ];

  /* --------------------------------------------------------------- state */

  const S = { view: "skenario", q: "", state: null, err: null, opened: null, focusBack: null };

  const fresh = () => {
    if (!S.state || !S.state.generated) return null;
    const t = Date.parse(S.state.generated);
    return Number.isFinite(t) ? Math.round((Date.now() - t) / 1000) : null;
  };
  const ago = (s) => (s == null ? "—" : s < 60 ? `${s} dtk` : s < 3600 ? `${Math.round(s / 60)} mnt` : `${(s / 3600).toFixed(1)} jam`);

  async function load() {
    try {
      const r = await fetch("/api/state", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      S.state = await r.json();
      S.err = null;
    } catch (e) {
      S.state = null;
      S.err = e.message || "gagal";
    }
    paintLive();
    render();
  }

  function paintLive() {
    const el = $("live"), txt = $("liveTxt");
    const age = fresh();
    el.classList.remove("ok", "warn", "bad");
    if (S.err) { el.classList.add("bad"); txt.textContent = "state offline"; }
    else if (age != null && age > 300) { el.classList.add("warn"); txt.textContent = `state ${ago(age)} lalu`; }
    else { el.classList.add("ok"); txt.textContent = "state segar"; }
    $("footTxt").innerHTML = S.state
      ? `Sumber: <b>/api/state</b> (dibuat ${esc(S.state.generated)}) · docs/WORKFLOW_SKENARIO.md · docs/DIVISIONS.md`
      : `Sumber statis: docs/WORKFLOW_SKENARIO.md · docs/DIVISIONS.md — <b>live state tidak tersedia</b> (${esc(S.err || "")})`;
  }

  /* --------------------------------------------------------------- util */

  // /api/state mengirim `agents` sebagai objek ber-id, bukan array — normalisasi dulu.
  const agentList = () => {
    const a = S.state && S.state.agents;
    if (!a) return [];
    if (Array.isArray(a)) return a;
    return Object.entries(a).map(([id, v]) => Object.assign({ id }, v));
  };
  const agentOf = (d) => agentList().filter((a) => (a.divisions || []).includes(d));
  // Pemilik = divisi dari semua tahap yang TIDAK dipangkas (bukan hanya yang wajib).
  const scenOwners = (sc) => {
    const set = new Set();
    STAGES.forEach((s) => { if (!sc.trim.codes.includes(s.c)) set.add(s.d); });
    return [...set].sort();
  };
  const trimmedBy = (code) => SCEN.filter((s) => s.trim.codes.includes(code));

  function kpis() {
    const agents = agentList();
    const items = [
      ["Skenario", SCEN.length, "titik masuk terverifikasi §6"],
      ["Tahap mesin", STAGES.length, "01 → 16 · runner sama"],
      ["Divisi", DIVS.length, "D0–D11"],
      ["Agen live", S.err ? "—" : agents.length, S.err ? "state offline" : "dari /api/state"],
      ["Gate deterministik", 2, "gate_check · release_check"],
      ["Head", S.state && S.state.head ? String(S.state.head).slice(0, 7) : "—", "commit terakhir", "mono"],
    ];
    $("kpis").innerHTML = items.map(([k, v, s, cls]) =>
      `<div class="kpi"><span class="k">${esc(k)}</span><b class="v${cls ? " " + cls : ""}">${esc(v)}</b><span class="s">${esc(s)}</span></div>`).join("");
    $("nScen").textContent = SCEN.length;
    $("nDiv").textContent = DIVS.length;
    $("nAgent").textContent = agents.length || "";
    $("nStage").textContent = STAGES.length;
  }

  /* -------------------------------------------------------------- views */

  const match = (o, q) => !q || JSON.stringify(o).toLowerCase().includes(q.toLowerCase());

  function shel(title, sub, extra = "") {
    return `<div class="shead"><div><h1>${esc(title)}</h1><p>${esc(sub)}</p></div>${extra}</div>`;
  }

  function viewScen() {
    const rows = SCEN.filter((s) => match(s, S.q));
    if (!rows.length) return shel("Tidak ada hasil", `Tidak ada skenario yang cocok dengan “${S.q}”.`) + `<div class="empty">Coba kata lain: clone, PRD, mobile, audit, rilis.</div>`;
    return shel(
      "Mulai dari titik masuk",
      "Sepuluh jalur resmi di atas satu mesin 18 tahap. Klik kartu untuk melihat tahap yang dipangkas, perintah nyatanya, dan jebakannya.",
      `<div class="quick" role="group" aria-label="Pintu masuk cepat">
         <button type="button" class="quick-btn" data-scen="A">Punya contoh</button>
         <button type="button" class="quick-btn" data-scen="B">Punya PRD</button>
         <button type="button" class="quick-btn" data-scen="C">Baru ide chat</button>
       </div>`
    ) + `<div class="grid scen">${rows.map((s) => `
      <button class="scard" type="button" data-scen="${esc(s.key)}" aria-label="Buka skenario ${esc(s.title)}">
        <span class="top"><span class="ico" aria-hidden="true">${esc(s.icon)}</span><span class="risk ${esc(s.risk)}">${esc(s.risk)}</span></span>
        <h3>${esc(s.title)}</h3>
        <p class="when">${esc(s.when)}</p>
        <span class="foot">
          <span class="chip">masuk: ${esc(s.entry)}</span>
          <span class="chip warn">${s.trim.codes.length ? `pangkas ${s.trim.codes.length} tahap` : "pangkas 0"}</span>
          <span class="chip d">wajib ${esc(s.keepText)}</span>
        </span>
      </button>`).join("")}</div>`;
  }

  function viewDiv() {
    const rows = DIVS.filter((d) => match(d, S.q) || agentOf(d.id).some((a) => match(a, S.q)));
    if (!rows.length) return shel("Tidak ada divisi cocok", `“${S.q}”` ) + `<div class="empty">Kosong.</div>`;
    return shel("Dua belas divisi, satu alur", "Pemilik tahap dan agen yang terpasang. Nama divisi dari docs/DIVISIONS.md; status agen dari /api/state.") +
      `<div class="grid cards">${rows.map((d) => {
        const ag = agentOf(d.id);
        const st = STAGES.filter((s) => s.d === d.id).map((s) => s.c);
        const sc = SCEN.filter((s) => scenOwners(s).includes(d.id)).length;
        return `<article class="card">
          <div class="hd"><span class="avatar${d.id === "D9" ? " alt" : ""}">${esc(d.id)}</span>
            <span class="who"><b>${esc(d.name)}</b><span>${esc(d.owner)}</span></span></div>
          <dl class="kv">
            <dt>Tahap</dt><dd>${esc(st.join(" · ") || "—")}</dd>
            <dt>Agen</dt><dd>${esc(ag.map((a) => a.model || a.profile).join(" · ") || "tak ada di state")}</dd>
            <dt>Skenario</dt><dd>${sc} / ${SCEN.length}</dd>
          </dl>
        </article>`;
      }).join("")}</div>`;
  }

  function viewAgen() {
    const agents = agentList();
    if (S.err) return shel("Agen tidak terbaca", "State live gagal dimuat — tabel agen tidak dikarang.") +
      `<div class="empty">${esc(S.err)}. Tekan ↻ untuk mencoba lagi.</div>`;
    const rows = agents.filter((a) => match(a, S.q));
    return shel("Agen yang terpasang", "Delapan peran agen dari /api/state. “Health unknown” berarti monitoring belum mengisi — bukan berarti sehat.") +
      `<div class="grid cards">${rows.map((a) => `
        <article class="card">
          <div class="hd"><span class="avatar">${esc((a.id || "?").slice(0, 2).toUpperCase())}</span>
            <span class="who"><b>${esc(a.profile)}</b><span>${esc(a.id)}</span></span></div>
          <p class="mission">${esc(a.mission || "")}</p>
          <dl class="kv">
            <dt>Divisi</dt><dd>${esc((a.divisions || []).join(" ") || "—")}</dd>
            <dt>Model</dt><dd>${esc(a.primary || a.model || "—")}</dd>
            <dt>Eskalasi</dt><dd>${esc(Array.isArray(a.escalation) ? a.escalation.join(" → ") : (a.escalation || "—"))}</dd>
            <dt>Tahap</dt><dd>${esc((a.stages || []).join(" ") || "—")}</dd>
            <dt>Izin</dt><dd>${esc((a.permissions || []).join(" · ") || "—")}</dd>
          </dl>
          ${a.notes ? `<p class="src">${esc(a.notes)}</p>` : ""}
        </article>`).join("")}</div>`;
  }

  function viewAlur() {
    const rows = STAGES.filter((s) => match(s, S.q));
    return shel("Satu mesin, delapan belas baris", "Urutan ini yang dijalankan workflow_run.py. Runner memeriksa keberadaan artefak — bukan menilai kualitas.") +
      `<div class="pipe">${rows.map((s) => {
        const tr = trimmedBy(s.c);
        return `<div class="stage" data-stage="${esc(s.c)}">
          <span class="num">${esc(s.c)}</span>
          <span class="nm">${esc(s.n)}</span>
          <span class="own">
            <span class="chip">${esc(s.d)}</span>
            ${s.tool ? `<span class="chip d">${esc(s.tool)}</span>` : ""}
            ${tr.length ? `<span class="chip warn">dipangkas ${tr.length}/10</span>` : `<span class="chip">wajib di semua</span>`}
          </span>
        </div>`;
      }).join("")}</div>`;
  }

  function viewPolicy() {
    const sc = new Set(SCEN.map((s) => s.key));
    return shel("Kebijakan rute", "Aturan yang tidak boleh dilanggar, kesalahan yang sudah merusak proyek nyata, dan selisih dokumen vs kode yang saya temukan.") +
      `<div class="grid cards">
        <article class="card" style="grid-column:1/-1">
          <div class="hd"><span class="avatar">§1</span><span class="who"><b>Aturan inti</b><span>WORKFLOW_SKENARIO §8</span></span></div>
          <ul class="clean">${CORE_RULES.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
        </article>
        <article class="card" style="grid-column:1/-1">
          <div class="hd"><span class="avatar alt">§7</span><span class="who"><b>Kesalahan lintas-skenario</b><span>semua ini pernah merusak proyek</span></span></div>
          <table class="tbl"><thead><tr><th>Kesalahan</th><th>Kenapa fatal</th><th>Pencegahan</th></tr></thead><tbody>
            ${FATAL.map(([a, b, c]) => `<tr><td>${esc(a)}</td><td>${esc(b)}</td><td><code>${esc(c)}</code></td></tr>`).join("")}
          </tbody></table>
        </article>
        <article class="card" style="grid-column:1/-1">
          <div class="hd"><span class="avatar alt">!</span><span class="who"><b>Drift dokumen → kode</b><span>diverifikasi di checkout ini</span></span></div>
          <p class="mission">Dokumen menulis perintah singkat yang tidak ada di checkout ini. Deck memakai perintah yang sudah saya jalankan.</p>
          <table class="tbl"><thead><tr><th>Di dokumen</th><th>Hasil uji</th><th>Gunakan</th></tr></thead><tbody>
            ${DRIFT.map(([a, b, c]) => `<tr><td><code>${a}</code></td><td>${esc(b)}</td><td><code>${c}</code></td></tr>`).join("")}
          </tbody></table>
          <p class="src">${sc.size} skenario · 18 tahap · diverifikasi 2026-11-01</p>
        </article>
      </div>`;
  }

  /* ------------------------------------------------------------- drawer */

  function rail(sc) {
    return `<div class="rail">${STAGES.map((s) => {
      const off = sc.trim.codes.includes(s.c);
      const keep = sc.keep.some((k) => k.c === s.c);
      const cls = off ? "chip off" : keep ? "chip keep" : "chip";
      return `<span class="${cls}" title="${esc(s.c + " " + s.n)}">${esc(s.c)}</span>`;
    }).join("")}</div>
    <p class="legend"><span class="chip keep">wajib</span><span class="chip off">dipangkas</span><span class="chip">normal</span></p>`;
  }

  function openScen(key) {
    const sc = SCEN_BY[key];
    if (!sc) return;
    $("dEyebrow").textContent = `Skenario ${sc.key} · risiko ${sc.risk} (penilaian deck)`;
    $("dTitle").textContent = sc.title;
    const owners = scenOwners(sc);
    $("dBody").innerHTML = `
      <h4>Kapan dipakai</h4>
      <p>${esc(sc.when)}</p>

      <h4>Titik masuk</h4>
      <p class="chips"><span class="chip d">${esc(sc.entry)}</span></p>

      <h4>Alur 18 tahap</h4>
      ${rail(sc)}

      <h4>Dipangkas</h4>
      ${sc.trim.codes.length ? `<ul class="clean">${sc.trim.codes.map((c) => `<li><b>${esc(c)}</b> ${esc(STAGE_BY[c] ? STAGE_BY[c].n : "")} — ${esc(sc.trim.note)}</li>`).join("")}</ul>`
        : `<p class="mission">Tidak ada tahap yang dipangkas.</p>`}

      <h4>Tidak boleh dipangkas</h4>
      <ul class="clean">${sc.keep.map((k) => `<li><b>${esc(k.c)}</b> ${esc(STAGE_BY[k.c] ? STAGE_BY[k.c].n : "")} — ${esc(k.why)}</li>`).join("")}</ul>

      <h4>Perintah nyata</h4>
      <div class="promptbox">
        <div class="cmdhead"><span>bash · dari ~/super-dev-builders</span><button class="copy" type="button" data-copy>Salin</button></div>
        <pre><code>${esc(sc.cmds.join("\n"))}</code></pre>
      </div>
      <p class="src">Semua perintah diuji dengan <code>--help</code> pada checkout ini. Ganti <code>nama-target</code> sesuai slug Anda.</p>

      <h4>Jebakan</h4>
      <ul>${sc.traps.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>

      <h4>Pemilik</h4>
      <div class="owners">${owners.map((d) => {
        const a = agentOf(d)[0];
        return `<span class="owner"><span class="avatar">${esc(d)}</span><b>${esc(DIV_BY[d] ? DIV_BY[d].name : d)}</b>
          <span>${esc(a ? a.profile : DIV_BY[d] ? DIV_BY[d].owner : "—")}</span></span>`;
      }).join("")}</div>

      <p class="src">Sumber: docs/WORKFLOW_SKENARIO.md §5 (${esc(sc.key)}), §6, §7.</p>`;
    show(sc.key);
  }

  function openStage(code) {
    const s = STAGE_BY[code];
    if (!s) return;
    const tr = trimmedBy(code);
    $("dEyebrow").textContent = `Tahap ${s.c}`;
    $("dTitle").textContent = s.n;
    $("dBody").innerHTML = `
      <h4>Pemilik</h4>
      <p class="chips"><span class="chip">${esc(s.d)}</span> ${esc(DIV_BY[s.d] ? DIV_BY[s.d].name : "")}</p>
      <h4>Alat</h4>
      <p>${s.tool ? `<code>${esc(s.tool)}</code>` : "Tidak ada alat otomatis — diperiksa lewat artefak."}</p>
      <h4>Skenario yang memangkas tahap ini</h4>
      ${tr.length ? `<ul class="clean">${tr.map((x) => `<li><b>${esc(x.key)}</b> ${esc(x.title)} — ${esc(x.trim.note)}</li>`).join("")}</ul>`
        : `<p class="mission">Tidak ada skenario resmi yang memangkas tahap ini.</p>`}
      <h4>Skenario yang mewajibkannya</h4>
      <p class="chips">${SCEN.filter((x) => x.keep.some((k) => k.c === code)).map((x) => `<span class="chip keep">${esc(x.key)}</span>`).join("") || "—"}</p>
      <p class="src">Sumber: docs/WORKFLOW_SKENARIO.md §1, §6.</p>`;
    show(`stage:${code}`);
  }

  function show(tag) {
    S.opened = tag;
    S.focusBack = document.activeElement;
    const hash = tag.startsWith("stage:") ? `#alur/${tag.slice(6)}` : `#skenario/${tag}`;
    if (location.hash !== hash) history.replaceState(null, "", hash);
    const d = $("drawer");
    d.hidden = false;
    requestAnimationFrame(() => d.classList.add("on"));
    $("dBody").scrollTop = 0;
    const btn = d.querySelector("[data-close]");
    if (btn) btn.focus({ preventScroll: true });
  }

  function close() {
    const d = $("drawer");
    d.classList.remove("on");
    S.opened = null;
    history.replaceState(null, "", `#${S.view}`);
    setTimeout(() => { d.hidden = true; }, 160);
    if (S.focusBack && S.focusBack.isConnected) S.focusBack.focus({ preventScroll: true });
  }

  /* -------------------------------------------------------------- toast */

  let toastT = 0;
  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("on");
    clearTimeout(toastT);
    toastT = setTimeout(() => t.classList.remove("on"), 2200);
  }

  async function copyText(txt) {
    try {
      await navigator.clipboard.writeText(txt);
      toast("Perintah disalin");
    } catch {
      const ta = document.createElement("textarea");
      ta.value = txt;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand && document.execCommand("copy");
      ta.remove();
      toast(ok ? "Perintah disalin" : "Gagal menyalin — pilih manual");
    }
  }

  /* --------------------------------------------------------------- render */

  const VIEWS = { skenario: viewScen, divisi: viewDiv, agen: viewAgen, alur: viewAlur, kebijakan: viewPolicy };

  function render() {
    kpis();
    $("view").innerHTML = (VIEWS[S.view] || viewScen)();
    document.querySelectorAll(".tab").forEach((t) =>
      t.setAttribute("aria-selected", String(t.dataset.view === S.view)));
  }

  function setView(v, push = true) {
    if (!VIEWS[v]) v = "skenario";
    S.view = v;
    if (push && location.hash !== `#${v}`) history.replaceState(null, "", `#${v}`);
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  /* ---------------------------------------------------------------- wire */

  document.querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => setView(t.dataset.view)));

  $("q").addEventListener("input", (e) => { S.q = e.target.value.trim(); render(); });

  $("refresh").addEventListener("click", async () => {
    $("refresh").disabled = true;
    await load();
    $("refresh").disabled = false;
    toast("Data dimuat ulang");
  });

  $("view").addEventListener("click", (e) => {
    const card = e.target.closest("[data-scen]");
    if (card) return openScen(card.dataset.scen);
    const stage = e.target.closest("[data-stage]");
    if (stage) return openStage(stage.dataset.stage);
  });

  $("dBody").addEventListener("click", (e) => {
    if (!e.target.closest("[data-copy]")) return;
    const pre = $("dBody").querySelector("pre code");
    if (pre) copyText(pre.textContent);
  });

  $("drawer").addEventListener("click", (e) => { if (e.target.closest("[data-close]")) close(); });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && S.opened) { e.preventDefault(); close(); return; }
    if (e.key === "/" && document.activeElement !== $("q")) { e.preventDefault(); $("q").focus(); }
    if (e.key === "Tab" && S.opened) {
      const f = $("drawer").querySelectorAll("button, [href], pre");
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  const tick = () => {
    const now = new Date();
    $("clock").textContent = now.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Jakarta" }) + " WIB";
    paintLive();
  };
  tick();
  setInterval(tick, 1000);

  const q0 = new URLSearchParams(location.search).get("q");
  if (q0) { S.q = q0; $("q").value = q0; }

  const [hView, hKey] = (location.hash || "").replace(/^#/, "").split("/");
  S.view = VIEWS[hView] ? hView : "skenario";
  render();
  if (hKey) {
    if (hView === "alur") openStage(hKey);
    else if (SCEN_BY[hKey]) openScen(hKey);
  }
  load();
  setInterval(load, 60000);
})();
