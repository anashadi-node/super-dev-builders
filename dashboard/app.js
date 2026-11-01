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

  /* ------------------------------------------------------------- intake */
  /* Kanal input per skenario. Satu panel = teks bebas + link + lampiran.
   * Penyimpanan nyata: ~/sdb-workspace/intake/<id>/{meta.json,brief.md,files/}
   * Tidak ada klaim "menjalankan agen" — ini hanya menulis masukan ke disk. */

  const IK = { token: null, local: false, scope: null, ctx: null, files: [], links: [],
               busy: false, list: null, listErr: null };

  const ikBytes = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(2)} MB`);
  const ikExt = (n) => (String(n).split(".").pop() || "").toLowerCase();
  const IK_KIND = {
    png: "img", jpg: "img", jpeg: "img", gif: "img", webp: "img", svg: "img", bmp: "img",
    pdf: "pdf", doc: "doc", docx: "doc", odt: "doc", rtf: "doc",
    md: "text", txt: "text", csv: "text", json: "text", yaml: "text", yml: "text", log: "text",
    html: "web", htm: "web", css: "web", js: "web", ts: "web", tsx: "web", jsx: "web", vue: "web",
    zip: "zip", gz: "zip", tar: "zip", "7z": "zip", rar: "zip",
  };
  const ikGlyph = (n) => ({ img: "▣", pdf: "▤", doc: "▤", text: "≡", web: "❮❯", zip: "▩" }[IK_KIND[ikExt(n)] || ""] || "▢");

  function ikDraft(scope) {
    try {
      const d = JSON.parse(localStorage.getItem("sdb.ik." + scope) || "null");
      return { text: d && typeof d.text === "string" ? d.text : "",
               links: d && Array.isArray(d.links) ? d.links.slice(0, 20) : [] };
    } catch { return { text: "", links: [] }; }
  }
  function ikStore(scope, d) {
    try { localStorage.setItem("sdb.ik." + scope, JSON.stringify(d)); } catch { /* kuota penuh: draf tetap di layar */ }
  }

  async function ikAuth() {
    try {
      const r = await fetch("/api/ws/whoami", { cache: "no-store" });
      if (!r.ok) return;
      const j = await r.json();
      IK.local = !!j.local;
      if (j.token) IK.token = j.token;
    } catch { /* offline: PIN manual tetap bisa diisi */ }
  }

  /* Token lokal baru diketahui setelah fetch; buang kolom PIN bila sudah ada. */
  function ikSyncAuth() {
    if (!IK.token) return;
    const body = $("dBody");
    if (!body) return;
    const pin = body.querySelector("[data-ik-pin]");
    if (!pin) return;
    const lab = pin.previousElementSibling;
    pin.remove();
    if (lab && lab.classList.contains("ik-lab")) lab.remove();
  }

  function ikPanel(ctx) {
    return `<section class="ik" data-ik="${esc(ctx.scope)}">
      <div class="ik-hd">
        <span class="ik-ic" aria-hidden="true">＋</span>
        <span class="ik-tt"><b>Brief &amp; lampiran</b><span>${esc(ctx.hint)}</span></span>
        <span class="ik-tag">input</span>
      </div>

      <label class="ik-lab" for="ikText">Apa yang ingin dibuat / diubah</label>
      <textarea id="ikText" class="ik-ta" data-ik-text rows="4"
        placeholder="Contoh: Buat ulang landing page ini dengan Next.js + Tailwind, tanpa menyalin aset. Ganti logo &amp; copy dengan milik sendiri."></textarea>
      <div class="ik-meta"><span data-ik-count>0</span> karakter · draf tersimpan otomatis di browser ini</div>

      <label class="ik-lab" for="ikLink">Contoh / referensi — tempel link, tekan Enter</label>
      <div class="ik-linkrow">
        <input id="ikLink" class="ik-in" data-ik-link type="url" inputmode="url" autocomplete="off" spellcheck="false"
          placeholder="https://contoh.com/halaman-yang-ingin-ditiru">
        <button class="ik-add" type="button" data-ik-add>Tambah</button>
      </div>
      <div class="ik-chips" data-ik-links></div>

      <label class="ik-lab">Lampiran</label>
      <div class="ik-drop" data-ik-drop tabindex="0" role="button" aria-label="Tambah lampiran file">
        <span class="ik-dg" aria-hidden="true">⬆</span>
        <b>Tarik file ke sini, atau klik untuk memilih</b>
        <span>gambar · html · md · doc/docx · pdf · zip · apa pun</span>
        <em>Maks 25 MB per file · 40 file per kiriman</em>
        <input type="file" data-ik-file multiple hidden>
      </div>
      <div class="ik-files" data-ik-files></div>

      <div class="ik-prog" data-ik-prog hidden><i></i><span></span></div>

      ${IK.token ? "" : `<label class="ik-lab" for="ikPin">PIN akses</label>
      <input id="ikPin" class="ik-in ik-pinfield" data-ik-pin type="password" autocomplete="off"
        placeholder="PIN 12 karakter">`}

      <div class="ik-foot">
        <button class="ik-send" type="button" data-ik-send>Simpan ke Intake</button>
        <span class="ik-note" data-ik-note>Ditulis ke ~/sdb-workspace/intake/ — bukan menjalankan agen.</span>
      </div>
      <div class="ik-out" data-ik-out></div>
    </section>`;
  }

  function ikMount(ctx) {
    IK.ctx = ctx;
    const body = $("dBody");
    const host = body.querySelector(".ik");
    if (!host) return;
    const same = IK.scope === ctx.scope;
    const d = ikDraft(ctx.scope);
    if (!same) { IK.scope = ctx.scope; IK.files = []; IK.links = d.links; }
    host.querySelector("[data-ik-text]").value = d.text;
    ikSyncAuth();
    ikPaint();
  }

  function ikPaint() {
    const body = $("dBody");
    const ta = body.querySelector("[data-ik-text]");
    if (!ta) return;
    const cnt = body.querySelector("[data-ik-count]");
    if (cnt) cnt.textContent = ta.value.trim().length;

    const lk = body.querySelector("[data-ik-links]");
    if (lk) {
      lk.innerHTML = IK.links.length
        ? IK.links.map((u, i) => `<span class="ik-chip"><a href="${esc(u)}" target="_blank" rel="noopener noreferrer nofollow">${esc(u.replace(/^https?:\/\//i, "").slice(0, 46))}</a><button type="button" data-ik-rmlink="${i}" aria-label="Hapus link">✕</button></span>`).join("")
        : `<span class="ik-chips-empty">Belum ada link.</span>`;
    }

    const fl = body.querySelector("[data-ik-files]");
    if (fl) {
      fl.innerHTML = IK.files.map((f, i) => `<div class="ik-file">
        <span class="ik-fg k-${IK_KIND[ikExt(f.name)] || "other"}">${ikGlyph(f.name)}</span>
        <span class="ik-fn"><b title="${esc(f.name)}">${esc(f.name)}</b><span>${ikBytes(f.size)}${f.type ? " · " + esc(String(f.type).split("/")[0]) : ""}</span></span>
        <button type="button" data-ik-rmfile="${i}" aria-label="Hapus ${esc(f.name)}">✕</button>
      </div>`).join("");
    }

    const btn = body.querySelector("[data-ik-send]");
    if (btn) { btn.disabled = IK.busy; btn.textContent = IK.busy ? "Mengirim…" : "Simpan ke Intake"; }

    const note = body.querySelector("[data-ik-note]");
    if (note && !IK.busy) {
      const total = IK.files.reduce((a, f) => a + f.size, 0);
      note.textContent = IK.files.length
        ? `${IK.files.length} file · ${ikBytes(total)} — ditulis ke ~/sdb-workspace/intake/`
        : "Ditulis ke ~/sdb-workspace/intake/ — bukan menjalankan agen.";
    }
  }

  function ikAddFiles(list) {
    if (!list || !list.length) return;
    const errs = [];
    for (const f of list) {
      if (f.size > 25 * 1024 * 1024) { errs.push(`${f.name}: lebih dari 25 MB`); continue; }
      if (IK.files.length >= 40) { errs.push("maksimum 40 file per kiriman"); break; }
      if (IK.files.some((x) => x.name === f.name && x.size === f.size)) continue;
      IK.files.push(f);
    }
    if (errs.length) toast(errs[0]);
    ikPaint();
  }

  function ikAddLink() {
    const inp = $("dBody").querySelector("[data-ik-link]");
    if (!inp) return;
    let v = inp.value.trim();
    if (!v) return;
    if (!/^https?:\/\//i.test(v) && /^[\w.-]+\.[a-z]{2,}(\/|$)/i.test(v)) v = "https://" + v;
    if (!/^https?:\/\/\S+$/i.test(v)) return toast("Link harus http:// atau https://");
    if (IK.links.includes(v)) { inp.value = ""; return toast("Link sudah ada"); }
    if (IK.links.length >= 20) return toast("Maksimum 20 link");
    IK.links.push(v);
    inp.value = "";
    const ta = $("dBody").querySelector("[data-ik-text]");
    ikStore(IK.scope, { text: ta ? ta.value : "", links: IK.links });
    ikPaint();
  }

  function ikUpload(id, file, onp) {
    return new Promise((res, rej) => {
      const x = new XMLHttpRequest();
      x.open("POST", `/api/inbox/file?id=${encodeURIComponent(id)}&name=${encodeURIComponent(file.name)}`);
      x.setRequestHeader("X-SDB-Token", IK.token);
      x.setRequestHeader("Content-Type", file.type || "application/octet-stream");
      x.upload.onprogress = (e) => { if (e.lengthComputable && onp) onp(e.loaded / e.total); };
      x.onload = () => {
        let j = {};
        try { j = JSON.parse(x.responseText); } catch { /* balasan bukan JSON */ }
        if (x.status >= 200 && x.status < 300) res(j);
        else rej(new Error(j.error || `HTTP ${x.status}`));
      };
      x.onerror = () => rej(new Error("jaringan gagal"));
      x.send(file);
    });
  }

  async function ikSend() {
    if (IK.busy) return;
    const body = $("dBody");
    const ta = body.querySelector("[data-ik-text]");
    const pin = body.querySelector("[data-ik-pin]");
    if (!IK.token && pin && pin.value.trim()) IK.token = pin.value.trim();
    const text = (ta ? ta.value : "").trim();
    if (!text && !IK.links.length && !IK.files.length) return toast("Isi brief, link, atau lampiran dulu");
    if (!IK.token) return toast("PIN akses belum diisi");

    const ctx = IK.ctx || {};
    IK.busy = true;
    ikPaint();
    const prog = body.querySelector("[data-ik-prog]");
    const bar = prog && prog.querySelector("i");
    const lab = prog && prog.querySelector("span");
    const setP = (p, t) => { if (!prog) return; prog.hidden = false; bar.style.width = `${Math.round(p * 100)}%`; lab.textContent = t; };

    try {
      setP(0.03, "membuat intake…");
      const r = await fetch("/api/inbox/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-SDB-Token": IK.token },
        body: JSON.stringify({
          scen: ctx.scen || "", scen_title: ctx.scenTitle || "", stage: ctx.stage || "",
          text, links: IK.links, expect_files: IK.files.length,
        }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);

      const n = IK.files.length;
      let done = 0;
      for (const f of IK.files) {
        await ikUpload(j.id, f, (p) => setP((done + p) / Math.max(1, n), `mengunggah ${f.name}`));
        done += 1;
      }
      setP(1, "selesai");

      ikStore(IK.scope, { text: "", links: [] });
      if (ta) ta.value = "";
      IK.links = []; IK.files = [];
      ikOut(j.id, j.title);
      IK.list = null;
      toast("Brief tersimpan di Intake");
    } catch (e) {
      toast(String(e.message || e).slice(0, 90));
      const note = body.querySelector("[data-ik-note]");
      if (note) note.textContent = `Gagal: ${e.message}`;
    } finally {
      IK.busy = false;
      ikPaint();
      setTimeout(() => { if (prog) prog.hidden = true; }, 900);
    }
  }

  function ikOut(id, title) {
    const o = $("dBody").querySelector("[data-ik-out]");
    if (!o) return;
    o.innerHTML = `<div class="ik-ok">
      <div class="ik-ok-hd"><span aria-hidden="true">✓</span><b>Tersimpan</b><code>${esc(id)}</code></div>
      <p>${esc(String(title || "").slice(0, 120))}</p>
      <dl>
        <dt>Folder</dt><dd>~/sdb-workspace/intake/${esc(id)}/</dd>
        <dt>Isi</dt><dd>brief.md · meta.json · files/</dd>
      </dl>
      <div class="ik-ok-act">
        <button type="button" data-ik-copy="${esc(id)}">Salin path</button>
        <button type="button" data-ik-show="${esc(id)}">Lihat brief.md</button>
      </div>
      <pre class="ik-brief" hidden></pre>
    </div>`;
  }

  async function ikShowBrief(id) {
    const pre = $("dBody").querySelector(".ik-brief");
    if (!pre) return;
    if (!pre.hidden) { pre.hidden = true; return; }
    pre.hidden = false;
    pre.textContent = "memuat…";
    try {
      const r = await fetch(`/api/inbox/get?id=${encodeURIComponent(id)}`, { cache: "no-store", headers: { "X-SDB-Token": IK.token } });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
      pre.textContent = j.brief || "(brief kosong)";
    } catch (e) { pre.textContent = `Gagal: ${e.message}`; }
  }

  async function ikLoadList() {
    IK.listErr = null;
    if (!IK.token) await ikAuth();
    try {
      const r = await fetch("/api/inbox/list", { cache: "no-store", headers: IK.token ? { "X-SDB-Token": IK.token } : {} });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
      IK.list = Array.isArray(j.items) ? j.items : [];
    } catch (e) {
      IK.listErr = `Tidak bisa memuat Intake: ${e.message}`;
      IK.list = null;
    }
    const n = $("nIntake");
    if (n) n.textContent = IK.list ? String(IK.list.length) : "";
  }

  async function openIntakeCard(id) {
    if (!/^\d{8}-\d{6}-[a-z0-9]{6}$/.test(id)) return;
    $("dEyebrow").textContent = "Intake";
    $("dTitle").textContent = "memuat…";
    $("dBody").innerHTML = `<div class="skel" style="height:120px"></div>`;
    show(`intake:${id}`);
    try {
      const r = await fetch(`/api/inbox/get?id=${encodeURIComponent(id)}`, { cache: "no-store", headers: { "X-SDB-Token": IK.token } });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
      $("dTitle").textContent = j.title || id;
      const files = Array.isArray(j.files) ? j.files : [];
      const links = Array.isArray(j.links) ? j.links : [];
      $("dBody").innerHTML = `
        <h4>Ringkasan</h4>
        <dl class="kv">
          <dt>Intake</dt><dd>${esc(j.id || id)}</dd>
          <dt>Dibuat</dt><dd>${esc(String(j.created || "").replace("T", " "))}</dd>
          <dt>Skenario</dt><dd>${esc(j.scen || "—")} ${esc(j.scen_title || "")}</dd>
          <dt>Tahap</dt><dd>${esc(j.stage || "—")}</dd>
          <dt>Target</dt><dd>${esc(j.target || "—")}</dd>
        </dl>

        <h4>Brief</h4>
        <pre class="ik-brief on">${esc(j.brief || "(kosong)")}</pre>

        <h4>Link (${links.length})</h4>
        ${links.length ? `<div class="ik-chips">${links.map((u) => `<span class="ik-chip"><a href="${esc(u)}" target="_blank" rel="noopener noreferrer nofollow">${esc(u.replace(/^https?:\/\//i, "").slice(0, 46))}</a></span>`).join("")}</div>` : `<p class="mission">Tidak ada link.</p>`}

        <h4>Lampiran (${files.length})</h4>
        ${files.length ? `<div class="ik-files on">${files.map((f) => `<div class="ik-file">
          <span class="ik-fg k-${IK_KIND[ikExt(f.name)] || "other"}">${ikGlyph(f.name)}</span>
          <span class="ik-fn"><b>${esc(f.name)}</b><span>${ikBytes(Number(f.size) || 0)} · sha256 ${esc(String(f.sha256 || "").slice(0, 12))}</span></span>
          <button type="button" data-ik-dl="${esc(f.stored)}" aria-label="Unduh ${esc(f.name)}">⇩</button>
        </div>`).join("")}</div>` : `<p class="mission">Tidak ada lampiran.</p>`}

        <h4>Folder</h4>
        <p class="src">~/sdb-workspace/intake/${esc(j.id || id)}/</p>
        <div class="ik-ok-act">
          <button type="button" data-ik-copy="${esc(j.id || id)}">Salin path</button>
          <button type="button" class="danger" data-ik-del="${esc(j.id || id)}">Hapus kiriman ini</button>
        </div>`;
    } catch (e) {
      $("dTitle").textContent = "Gagal memuat intake";
      $("dBody").innerHTML = `<div class="empty">${esc(String(e.message || e))}</div>`;
    }
  }

  async function ikDownload(id, name) {
    try {
      const r = await fetch(`/api/inbox/download?id=${encodeURIComponent(id)}&name=${encodeURIComponent(name)}`,
        { headers: { "X-SDB-Token": IK.token } });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const b = await r.blob();
      const u = URL.createObjectURL(b);
      const a = document.createElement("a");
      a.href = u;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(u), 4000);
    } catch (e) { toast(`Gagal mengunduh: ${e.message}`); }
  }

  async function ikDelete(id) {
    if (!window.confirm(`Hapus kiriman ${id} beserta semua lampirannya? Tindakan ini permanen.`)) return;
    try {
      const r = await fetch("/api/inbox/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-SDB-Token": IK.token },
        body: JSON.stringify({ id }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
      close();
      IK.list = null;
      if (S.view === "intake") ikLoadList().then(() => { if (S.view === "intake") render(); });
      toast("Kiriman dihapus");
    } catch (e) { toast(`Gagal menghapus: ${e.message}`); }
  }

  function viewIntake() {
    const root = `<span class="chip">~/sdb-workspace/intake</span>`;
    if (IK.listErr) return shel("Intake", "gagal memuat", root) + `<div class="empty">${esc(IK.listErr)}</div>`;
    if (!IK.list) return shel("Intake", "memuat…", root) + `<div class="skel"></div>`;
    if (!IK.list.length) {
      return shel("Intake", "belum ada kiriman", root) +
        `<div class="empty">Belum ada brief. Buka kartu skenario mana pun → panel “Brief &amp; lampiran” di paling atas, atau tekan tombol di bawah.<br><br>
         <button class="quick-btn" type="button" data-scen="A">Buka skenario A</button></div>`;
    }
    return shel("Intake", `${IK.list.length} kiriman terakhir`, root) +
      `<div class="grid cards">${IK.list.map((it) => `<article class="card ikcard">
        <div class="hd">
          <span class="avatar alt">${esc((it.scen || "·").slice(0, 3))}</span>
          <span class="who"><b>${esc(it.title || it.id)}</b><span>${esc(String(it.created || "").replace("T", " "))}</span></span>
        </div>
        <p class="mission">${esc(it.text || "(hanya lampiran/link)")}</p>
        <div class="chips">
          <span class="chip">${it.n_files} file</span>
          <span class="chip">${ikBytes(it.bytes)}</span>
          ${it.stage ? `<span class="chip d">tahap ${esc(it.stage)}</span>` : ""}
          ${it.links.length ? `<span class="chip">${it.links.length} link</span>` : ""}
        </div>
        <p class="src">${esc(it.id)}</p>
        <div class="ik-ok-act"><button type="button" data-ik-show="${esc(it.id)}">Lihat brief.md</button></div>
      </article>`).join("")}</div>`;
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
    const ctx = { scope: `scen:${sc.key}`, scen: sc.key, scenTitle: sc.title, stage: "",
                  hint: "Tulis maksud Anda di sini — jadi konteks tahap 01." };
    $("dEyebrow").textContent = `Skenario ${sc.key} · risiko ${sc.risk} (penilaian deck)`;
    $("dTitle").textContent = sc.title;
    const owners = scenOwners(sc);
    $("dBody").innerHTML = `
      ${ikPanel(ctx)}

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
    ikMount(ctx);
  }

  function openStage(code) {
    const s = STAGE_BY[code];
    if (!s) return;
    const ctx = { scope: `stage:${s.c}`, scen: "", scenTitle: "", stage: s.c,
                  hint: `Catatan untuk tahap ${s.c} — ${s.n}.` };
    const tr = trimmedBy(code);
    $("dEyebrow").textContent = `Tahap ${s.c}`;
    $("dTitle").textContent = s.n;
    $("dBody").innerHTML = `
      ${ikPanel(ctx)}
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
    ikMount(ctx);
  }

  function show(tag) {
    S.opened = tag;
    S.focusBack = document.activeElement;
    const hash = tag.startsWith("stage:") ? `#alur/${tag.slice(6)}`
      : tag.startsWith("intake:") ? `#intake/${tag.slice(7)}`
        : `#skenario/${tag}`;
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

  const VIEWS = { skenario: viewScen, divisi: viewDiv, agen: viewAgen, alur: viewAlur, intake: viewIntake, kebijakan: viewPolicy };

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
    if (v === "intake") {
      if (!IK.token) ikAuth().then(() => ikLoadList().then(() => { if (S.view === "intake") render(); }));
      else ikLoadList().then(() => { if (S.view === "intake") render(); });
    }
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

  /* ── intake: satu handler untuk ketik, link, dan file ─────────────── */

  $("dBody").addEventListener("input", (e) => {
    const ta = e.target.closest("[data-ik-text]");
    if (!ta) return;
    ikStore(IK.scope, { text: ta.value, links: IK.links });
    ikPaint();
  });

  $("dBody").addEventListener("keydown", (e) => {
    if (e.target.matches("[data-ik-link]") && e.key === "Enter") { e.preventDefault(); ikAddLink(); }
  });

  $("dBody").addEventListener("click", (e) => {
    const t = e.target;
    if (t.closest("[data-ik-add]")) return ikAddLink();
    const rl = t.closest("[data-ik-rmlink]");
    if (rl) {
      IK.links.splice(Number(rl.dataset.ikRmlink), 1);
      const ta = $("dBody").querySelector("[data-ik-text]");
      ikStore(IK.scope, { text: ta ? ta.value : "", links: IK.links });
      return ikPaint();
    }
    const rf = t.closest("[data-ik-rmfile]");
    if (rf) { IK.files.splice(Number(rf.dataset.ikRmfile), 1); return ikPaint(); }
    if (t.closest("[data-ik-drop]")) {
      const inp = $("dBody").querySelector("[data-ik-file]");
      if (inp && t.tagName !== "INPUT") inp.click();
      return;
    }
    if (t.closest("[data-ik-send]")) return ikSend();
    const cp = t.closest("[data-ik-copy]");
    if (cp) return copyText(`~/sdb-workspace/intake/${cp.dataset.ikCopy}`);
    const sh = t.closest("[data-ik-show]");
    if (sh) {
      if (S.view === "intake") { openIntakeCard(sh.dataset.ikShow); return; }
      return ikShowBrief(sh.dataset.ikShow);
    }
    const dl = t.closest("[data-ik-dl]");
    if (dl) {
      const m = /^(\d{8}-\d{6}-[a-z0-9]{6})$/.exec((S.opened || "").replace(/^intake:/, ""));
      if (m) ikDownload(m[1], dl.dataset.ikDl);
      return;
    }
    const del = t.closest("[data-ik-del]");
    if (del) return ikDelete(del.dataset.ikDel);
  });

  $("dBody").addEventListener("change", (e) => {
    if (!e.target.matches("[data-ik-file]")) return;
    ikAddFiles(e.target.files);
    e.target.value = "";
  });

  ["dragenter", "dragover"].forEach((ev) =>
    $("dBody").addEventListener(ev, (e) => {
      const d = e.target.closest("[data-ik-drop]");
      if (!d) return;
      e.preventDefault();
      d.classList.add("over");
    }));

  $("dBody").addEventListener("dragleave", (e) => {
    const d = e.target.closest("[data-ik-drop]");
    if (d) d.classList.remove("over");
  });

  $("dBody").addEventListener("drop", (e) => {
    const d = e.target.closest("[data-ik-drop]");
    if (!d) return;
    e.preventDefault();
    d.classList.remove("over");
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) ikAddFiles(e.dataTransfer.files);
  });

  $("dBody").addEventListener("paste", (e) => {
    if (!e.target.matches("[data-ik-text]")) return;
    const f = e.clipboardData && e.clipboardData.files;
    if (f && f.length) ikAddFiles(f);   // tempel gambar langsung jadi lampiran
  });

  /* Kartu di tab Intake hidup di #view, bukan di drawer. */
  $("view").addEventListener("click", (e) => {
    const sh = e.target.closest("[data-ik-show]");
    if (!sh) return;
    e.preventDefault();
    const go = () => openIntakeCard(sh.dataset.ikShow);
    if (IK.token) go(); else ikAuth().then(go);
  });

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

  /* Deep link yang diketik/diubah di address bar: hash saja tidak me-reload. */
  window.addEventListener("hashchange", () => {
    const [hv, hk] = (location.hash || "").replace(/^#/, "").split("/");
    if (!VIEWS[hv]) return;
    if (S.view !== hv) { S.view = hv; render(); window.scrollTo({ top: 0 }); }
    if (hk) {
      if (hv === "alur") openStage(hk);
      else if (hv === "intake") ikAuth().then(() => openIntakeCard(hk));
      else if (SCEN_BY[hk]) openScen(hk);
    } else if (S.opened) close();
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

  ikAuth().then(ikSyncAuth);

  const [hView, hKey] = (location.hash || "").replace(/^#/, "").split("/");
  S.view = VIEWS[hView] ? hView : "skenario";
  render();
  if (S.view === "intake") ikAuth().then(() => ikLoadList()).then(() => { if (S.view === "intake") render(); });
  if (hKey) {
    if (hView === "alur") openStage(hKey);
    else if (hView === "intake") { ikAuth().then(() => openIntakeCard(hKey)); }
    else if (SCEN_BY[hKey]) openScen(hKey);
  }
  load();
  setInterval(load, 60000);
})();
