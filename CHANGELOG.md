# Changelog

Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/) dan [SemVer](https://semver.org/lang/id/).

## [Belum dirilis]

### Ditambahkan
- **Gerbang dokumen `scripts/docs_lint.py` (`make docs-lint`, ikut `make check`).** Aturan
  `docs/INDEX.md` dulu hanya prosa; audit 2026-11-04 menemukan 10 dokumen tanpa entri indeks,
  3 PDF hasil generate masih terlacak, dan README mengklaim 39 skill padahal registry berisi 40.
  Gerbang kini memeriksa: setiap `docs/**/*.md` terindeks (ADR lewat nomor `ADR-000N`), setiap
  rujukan indeks menunjuk berkas yang ada, tidak ada `.pdf` terlacak, `.html` di `docs/`/`reports/`
  wajib berdaftar di `platform/docs-html-allowlist.json` beserta alasan, klaim jumlah skill README
  sama dengan `registry/skills.yaml`, dan tautan repo resmi ada. 10 uji negatif di
  `tests/test_docs_lint.py` — tiap aturan diuji karena harus MENOLAK, bukan sekadar ada.
- `docs/adr/0008-html-dokumen-dilacak-dan-gerbang-docs-lint.md` — dasar keputusan HTML berdaftar
  boleh dilacak, PDF tidak pernah.

### Diperbaiki
- **Jalur biner tidak memeriksa `deep_analysis_allowed`.** `recon --kind native` pada target
  mode A lolos Gate #0 lalu memanggil provider decompiler: gate berkata PASS, izin dilanggar.
  `_recon_native` kini menolak (exit 2, pesan jelas) bila manifest tidak menyatakan
  `deep_analysis_allowed: true`, dan menolak bila manifest hilang (fail-closed).
- **Verdict `doctor` saling bertentangan.** REA melaporkan `healthy=false` karena registrasi
  klien/skill opsional, sementara `native_ready=True`. `doctor` sekarang mencetak `sehat=`
  (kebutuhan SDB, tanpa penghambat) dan memisahkan `healthy-lengkap` + daftar celah opsional.
  Uji: `tests/test_recon_forge.py` (+2), `tests/test_docs_lint.py` (+10).
- `tools/recon-forge.py`: `deep_allowed()` membaca manifest target sekali, dipakai jalur biner.

### Dicatat
- Target contoh `elf-demo` (`targets/elf-demo`, biner kompilasi sendiri 16 KB) + manifest
  mode B, sebagai bukti jalur biner bisa dijalankan dan sebagai uji negatif mode A.

### Diubah
- `README.md`: klaim jumlah custom skill 39 → 40 (sesuai registry) dan tautan repo resmi
  `github.com/anashadi-node/super-dev-builders` ditambahkan di bagian atas.
- `docs/INDEX.md`: 10 dokumen masuk indeks (Seksi Tutorial baru, `DECK_INTAKE`, `TELEGRAM_SDB`,
  `WORKFLOW_SKENARIO`, `SECURITY_GATE_10`, 4 laporan), ADR-0008 terdaftar, aturan menambah
  dokumen kini menunjuk gerbang nyata.

### Dihapus
- 3 PDF hasil generate (`docs/REA_VS_CRAFT_ANYTHING_20261104.pdf`,
  `docs/archive/INTEGRASI_GITHUB_VERCEL_SUPABASE.pdf`, `reports/RESEARCH_REPLACEMENT_2026-10-04.pdf`)
  dan 1 HTML arsip hasil generate dilepas dari pelacakan (tetap ada di disk, bisa dibangun ulang
  dari `.md`; riwayat git tidak ditulis ulang). `.gitignore` menolak PDF baru.

- **`tools/recon-forge.py` — jalur recon native + gerbang bukti.** `recon --kind native
  --path <berkas>` membungkus `rea inspect` (dan `decompile-all` dengan `--decompile`),
  sehingga biner/ELF masuk alur yang sama dengan target web.
  - Akar izin: `targets/<target>` plus `repos`/`apps`/`apk_ipa_binaries` dari
    `evidence/<target>/authorization.yaml`. Path di luar akar ditolak (exit 2) sebelum
    REA dipanggil; `resolve()` menutup jalan keluar lewat symlink.
  - Provider gagal → exit 5 dengan penyebab + "Bukti tidak dikarang". Tidak ada
    manifest `verified: true` untuk hasil yang tidak ada.
- `jdk_ok()` / `jdk_home(roots=None)` — JDK hanya dianggap sehat bila `bin/java` dan
  `release` berisi (bukan 0 byte) dan `release` memuat `JAVA_VERSION=`. Sebelumnya
  instalasi terpotong lolos hanya karena `exists()`.
- `cmd_doctor` kini menyimpan `rea.checks` dan `rea.blockers`; `recon-biner` baru
  `True` bila ada provider ok **dan** tidak ada blocker (`ghidra`, `ghidra-java`,
  `ghidra-headless`, `java`, `node`). Output manusia menampilkan baris "Penghambat".
- `sha256_tree()` / `tree_bytes()` / `stamp_artifact()` — artefak berupa direktori
  (hasil `decompile-all`) dicatat sebagai **digest pohon**: SHA-256 dari `relpath` +
  isi tiap berkas dalam urutan nama.

### Diperbaiki
- **Manifest mencatat artefak direktori sebagai `sha256: null`, `bytes: 0`** — `sha256_file()`
  hanya menerima berkas, dan `p.is_file()` selalu `False` untuk direktori. Kini jalur web
  dan native sama-sama memakai `stamp_artifact()`; `decompile-all` tercatat 46191 byte
  dengan digest `3a5fb8ad…` yang cocok saat dihitung ulang lewat shell.
- Lint: 17 temuan `ruff` di `sdb_platform scripts tests skills dashboard` (RUF100, I001,
  F841, BLE001 ×3, RUF005 ×2, E741 ×2, RUF059) dibersihkan tanpa melonggarkan config.

### Diubah
- `targets/*/native/` masuk `.gitignore`. Subjek uji jalur native ternyata identik dengan
  `/usr/bin/true` host (GNU coreutils, GPLv3), jadi **tidak** di-commit ke repo BUSL-1.1;
  cara reproduksi ditulis di `docs/RECON_FORGE.md` (sha256 `8a63c983…`).
- `docs/INDEX.md` — entri `RECON_FORGE.md` dan `INTEGRASI_REPLICA.md` ditambahkan
  (sebelumnya kedua dokumen tidak terindeks, melanggar aturan indeks di `docs/INDEX.md`).
- `docs/RECON_FORGE.md` diselaraskan dengan kode: 21 uji, perintah native, akar izin,
  artefak `<stamp>-inspect.json` / `<stamp>-decompiled/`, invarian keamanan 8–10,
  tabel bukti biner `forge-demo`, dan catatan `healthy=false` yang akurat (sisa kegagalan
  hanya komponen opsional/registrasi, bukan Node/Ghidra/Java).

## [0.7.6] — 2026-10-29

### Diperbaiki
- **Ikon Desktop tidak pernah membuat kantor 3D tampil**: dua sebab ditemukan saat uji
  jalur nyata (klik ikon, bukan CLI).
  1. Flag `--enable-unsafe-swiftshader` hanya berlaku untuk **proses Chrome baru**.
     Saat Chrome sudah berjalan, klik ikon menumpang sesi lama ("Opening in existing
     browser session") sehingga flag diabaikan dan WebGL tetap mati.
  2. `--user-data-dir=%h/...` ditolak `desktop-file-validate` (`%h` bukan field code
     Exec), dan `$HOME` tidak di-expand di dalam heredoc berkutip — Chrome sempat
     membuat direktori literal bernama `$HOME`.
  - Launcher kini memakai profil khusus `~/.local/share/sdb-deck/profile` dengan path
    absolut yang disubstitusi setelah heredoc, sehingga flag benar-benar berlaku.
  - `sdb-fix-launcher.sh` ikut memulihkan `--user-data-dir` (dan memperbaiki `%h`
    warisan versi lama) pada `.desktop` yang sudah terpasang.

### Ditambahkan
- `tests/test_deck_boot.py::test_launcher_pakai_profil_khusus` — mengunci profil khusus,
  menolak `%h`, dan memvalidasi `.desktop` terpasang dengan `desktop-file-validate`.

## [0.7.5] — 2026-10-29

### Diperbaiki
- **Command Deck menggantung di "Menyiapkan Super Dev Builders Workspace…"**: akar masalah
  bukan izin launcher, melainkan `new THREE.WebGLRenderer()` melempar
  `Error creating WebGL context` di PC tanpa driver EGL (`No suitable EGL configs found`).
  Karena dilempar di top-level modul, overlay loader tidak pernah ditutup.
  - `dashboard/ws/world.js`: renderer dibuat dengan dua percobaan, lalu melempar
    `WEBGL_UNAVAILABLE` berkode agar bisa ditangani.
  - `dashboard/ws/app.js`: boot aman — bila WebGL gagal, deck tetap terbuka dalam **mode 2D**
    (chat, proyek, tim, panel hidup; hanya kantor 3D dimatikan) plus pemberitahuan penyebab.
  - Watchdog 8 detik: overlay loader **selalu** ditutup walau `ready` tak pernah datang.
  - `data-mode` / `data-mode-why` diekspos untuk diagnosis.

### Diubah
- Launcher deck (`install_shortcuts.sh`, `sdb-deck`, `sdb-fix-launcher.sh`) memakai
  `--enable-unsafe-swiftshader` supaya Chrome memakai renderer perangkat lunak ketika
  GPU/EGL tidak bisa membuat konteks WebGL — kantor 3D tetap tampil.
- Self-heal mengembalikan flag tersebut bila hilang dari `.desktop` terpasang.

### Ditambahkan
- `tests/test_deck_boot.py` (4 tes): GL rusak -> mode 2D tanpa loader; GL normal -> mode 3D
  dengan scene terbangun; launcher wajib mengizinkan Swiftshader; jalur gagal + watchdog ada.

## [0.7.4] — 2026-10-29

### Perbaikan

- **Command Deck tidak bisa dibuka dari ikon Desktop** (dialog *"Invalid Permissions on Desktop
  File"*, ikon X merah). Akar masalah: `~/Desktop/sdb-command-deck.desktop` pernah dibuat manual
  dengan mode `664` (tanpa bit executable) dan tanpa metadata GNOME `trusted` — tidak pernah
  dipasang oleh skrip repo mana pun. Server deck sendiri sehat (`HTTP 200` di `:8484`).
- `scripts/install_shortcuts.sh` kini **memasang sendiri** peluncur Command Deck ke
  `~/.local/share/applications/` + menyalinnya ke `~/Desktop`, menetapkan `chmod 755` dan
  `metadata::trusted true`, lalu **memverifikasi** (`desktop-file-validate`, bit `x`, keberadaan
  salinan Desktop) dan **gagal keras** (`exit 1`) bila ada yang menyimpang — bukan sekadar
  peringatan.
- `scripts/sdb-fix-launcher.sh` (baru) — self-heal: memulihkan izin, salinan Desktop, dan
  metadata trusted secara otomatis. Dipanggil harian oleh `sdb-deck-health.service` dan setiap
  kali `sdb-deck` dijalankan, sehingga kelas bug ini tidak bisa bertahan lebih dari satu siklus.

### Ditambahkan

- `docs/WORKFLOW_SKENARIO.{md,html,pdf}` — alur kerja untuk semua skenario: clone/reverse
  engineering (Gate #0 + evidence bersih), PRD jadi, chat ide, game, mobile, CLI/otomasi,
  data/laporan, refactor (baseline), audit, dan operasional — termasuk tabel tahap yang boleh
  dipangkas per skenario.
- `tests/test_install_shortcuts.py` — 7 tes regresi guard launcher (sintaks skrip, `chmod 755`,
  `metadata::trusted`, verifikasi fail-loud, tanpa `sudo`) + cakupan dokumen skenario.

### Verifikasi

- 7 tes baru PASS; seluruh suite (415 tes) PASS; `make check` RC=0.
- Uji nyata di PC: `chmod 644` pada launcher → self-heal memulihkan `755` + `trusted=true`;
  `gio launch ~/Desktop/sdb-command-deck.desktop` membuka deck (RC=0).

## [0.7.3] — 2026-10-29

### Ditambahkan

- `docs/TUTORIAL_PRIBADI.{md,html}` — panduan pemakaian pribadi di PC ini dan lewat Telegram
  (10 bagian: peta sistem, persiapan, rutinitas harian, contekan, bot read-only, shortcut, bahaya,
  FAQ), termasuk langkah membuat bot di BotFather dan tabel diagnosis bot diam.
- `scripts/sdb_tg_bot.py` — bot Telegram **read-only** (stdlib): `/status`, `/health`, `/revenue`,
  `/help`; SQLite `mode=ro` (tolak tulis di tingkat driver), hanya chat ID pemilik, long polling
  tanpa membuka port.
- `scripts/install_shortcuts.sh` — peluncur `SDB Tutorial`, `SDB Tutorial Pribadi`, `SDB Health`,
  handler `sdb://deck`, plus helper `sdb-deck`, `sdb-health`, `sdb-open` (mode 700, tanpa root).
- Unit `systemd --user`: `sdb-control-plane.service`, `sdb-tg-bot.service` (EnvironmentFile 600).

### Perbaikan

- `make docs-tutorial` kini membangun dua dokumen (produk & pribadi).

### Verifikasi

- 408 tes (401 → 408; 7 tes baru untuk bot, termasuk bukti `mode=ro` menolak INSERT).
- Smoke end-to-end bot terhadap DB hasil control plane nyata: 1 tenant, buku besar 75.000.000 μUSD.
- `make check` RC=0; hygiene PASS (334 berkas, 0 FAIL).

## [0.7.2] — 2026-10-29

### Perbaikan

- PDF tutorial dikeluarkan dari git: 609 KB melanggar gerbang berkas besar R1 (batas 512 KB).
  Ditangkap oleh uji kloning segar, bukan oleh `make check` lokal (berkas masih untracked saat itu).
  HTML (54 KB) dan Markdown tetap dilacak; PDF dibuat ulang lokal.
- `scripts/build_tutorial.py` + `make docs-tutorial` untuk membangun ulang HTML/PDF dari Markdown.


## [0.7.1] — 2026-10-29

### Ditambahkan

- `POST /v1/admin/tenants/<id>/status` — admin dapat menonaktifkan/mengaktifkan tenant lewat HTTP
  (sebelumnya `Store.set_status` hanya bisa dipanggil dari Python, tidak layak untuk operasi 24/7).
  Kunci tenant tidak bisa mengubah status sendiri; status tak sah → `400 invalid_status`.
- `docs/TUTORIAL_PENGGUNAAN.md` — panduan pemakaian lengkap (21 bagian, semua skenario dan kode galat).

Data pendukung: 401 tes (sebelumnya 396), 5 tes baru untuk rute status; make check RC=0.

## [0.7.0] — 2026-10-29

Fase 2c: pembatas laju per tenant, metrik Prometheus, dan pembatasan percobaan PIN dashboard.
Keputusan desain: ADR-0008. 396 tes (sebelumnya 384).

### Ditambahkan

- `429 rate_limited` + `Retry-After` saat tenant melewati jatah permintaan (token bucket di memori,
  default 600/menit, `SDB_RATE_PER_MIN`). Jatah per tenant lewat `limits.rate_per_min` (kolom baru
  `tenants.rate_per_min`, dimigrasi otomatis). Admin/worker tidak dibatasi.
- `GET /metrics` (admin) dalam format teks Prometheus: permintaan per rute/status, job dibuat/selesai,
  token terpakai, penolakan laju, uptime.
- Dashboard: >30 kegagalan token per IP dalam 60 detik → `429`.

### Catatan

- Penghitung metrik disimpan di proses: hilang saat restart, tidak dijumlah antar instance.

## [0.6.0] — 2026-10-29

Rilis audit fundamental. 30 cacat direproduksi dulu, baru diperbaiki (control plane 26 dari 27 hipotesis
terkonfirmasi, dashboard 3, skrip 1); tiap cacat punya tes regresi. 37 dari 39 tes regresi baru
**gagal di v0.5.0** — bukti tesnya membedakan; 2 sisanya pagar perilaku yang sudah benar. Laporan lengkap:
`reports/SDB_AUDIT_FUNDAMENTAL_20261029.md`. Keputusan desain: ADR-0007.

### Breaking

- `POST /v1/jobs/{id}/finish` → `410 endpoint_removed`. Tenant membatalkan lewat `/cancel`; job
  ditutup worker lewat `/v1/jobs/{id}/complete`.
- `POST /v1/invoices` (tenant) dihapus → `POST /v1/admin/invoices` (admin, body `tenant_id`).
  Tenant tetap bisa `GET /v1/invoices`.
- Worker CLI wajib `--executor`; `echo` butuh `SDB_ALLOW_ECHO_EXECUTOR=1`.
- URI artefak wajib `s3://<bucket>/<tenant_id>/…` atau `artifact://<tenant_id>/…`;
  `retention_until` wajib tanggal ISO masa depan.

### Fixed — uang

- Tenant bisa menutup job yang sedang dikerjakan worker → tagihan hilang (H1).
- `finish_job` menerima status `queued`/`running` → job ditagih 0 lalu dikerjakan ulang gratis (H2).
- Batal + worker mati → job macet `queued` selamanya, kredit tertahan (H3).
- Batal di detik terakhir → seluruh token terpakai gratis; kini ditagih pemakaian (H4).
- Worker lambat bisa menutup job yang sudah diambil worker lain (H5); cek & tulis kini satu transaksi.
- Invoice tumpang-tindih menagih charge sama dua kali; periode sampah/masa depan diterima (H9).
- Cek kuota job/storage dan idempotensi di luar transaksi → kuota jebol / 500 saat balapan (H25).

### Fixed — integritas & isolasi

- Job tenant `suspended` tetap dikerjakan; tenant `deleted` tidak menutup antrean (H6).
- Kunci idempotensi sama + isi beda diam-diam mengembalikan job lain → kini `409` (H7).
- `INSERT OR REPLACE` memindahkan API key antar tenant → kini `409 key_exists` (H8).
- URI artefak bisa menunjuk ruang tenant lain (H11); retensi bukan tanggal diterima (H10).
- `entry_id` di respons ≠ di DB (H12); memo ledger tidak terlindung hash (H13) → hash v2 + cek saldo
  per baris; baris v1 tetap terverifikasi. Refund tanpa transaksi (H14).
- Echo executor (token fiktif yang ditagih) jadi default CLI worker (H15).
- Lease 120 s tanpa heartbeat otomatis untuk job s/d 4 jam → diklaim ganda (H16).

### Changed — upgrade (bukan cacat terbukti)

- Klaim fair-share antar tenant (H17: probe kelaparan di v0.5.0 **REFUTED**; tetap ditambahkan karena
  FIFO murni membiarkan satu tenant yang mengantre ribuan job menunda semua tenant lain). FIFO dalam
  satu tenant kini deterministik (`rowid`), bukan acak dalam milidetik yang sama.

### Fixed — HTTP

- Body JSON non-objek, `pack`/`budget` non-objek, `lease_seconds` non-int, `Content-Length` cacat →
  500; kini 400 (H18–H21). `lease_seconds` tanpa batas (H22) → 10..3600.
- Tanpa socket timeout (slowloris) di control plane dan dashboard (H23, D3) → 30 s.
- Error 500 tidak tercatat di mana pun (H24) → traceback ke stderr, tanpa header/body.
- Header kunci non-ASCII → 500 (H26) → 401.
- Dashboard: body JSON non-objek → 500 yang membocorkan pesan internal Python (D1/D2) → 400.
- Respons API: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.
- `scripts/md_to_pdf.py --help` keluar kode 2 → 0; nama berkas di-escape di HTML.

### Catatan

- Purge riwayat (di bawah) menyebut "96 commit / 2,7 MB": itu angka **saat purge** dijalankan.
  `RESULT.md` (97 / 2,8 MB) dan laporan (98 / 2,9 MB) diambil setelah commit dokumentasi berikutnya —
  bukan kontradiksi, melainkan potret pada waktu berbeda.
- Tes: 384 (341 → 384). Migrasi DB v0.5.0 otomatis (kolom `ledger.hv`, 2 indeks).

## [0.5.0] — 2026-10-29

Fase 2b: produk bisa menagih dan pekerjaan benar-benar dijalankan. Masih **belum** ada gateway
pembayaran, RBAC/SSO, sandbox eksekusi, dan antrean terdistribusi.

### Added — billing (`sdb_platform/control_plane/billing.py`)

- Uang integer **micro-USD** (1e-6 USD); harga per 1 juta token: starter $2,00 · pro $1,60 ·
  team $1,20 · enterprise $1,00; pembulatan ke atas (tidak ada token gratis).
- Prabayar: hold sebesar harga budget saat job dibuat; kredit kurang → `402 insufficient_credit`,
  job tidak tercipta. Sukses → `charge` pemakaian nyata + sisa pesanan kembali; gagal/batal → `release`.
- **Ledger append-only ber-rantai hash**; kredit uji dicatat entri `adjust` sehingga
  `sum(amount) == saldo` dapat diuji; `verify_chain()` mendeteksi suntingan langsung di DB.
- `settle` idempoten (`job_charges` PK `job_id`): retry tidak menagih dua kali.
- Invoice periode: snapshot JSON kanonik + hash ber-rantai, idempoten per (tenant, periode),
  `verify_invoice()` mendeteksi perubahan total di luar aplikasi.

### Added — worker (`sdb_platform/runtime/worker.py`)

- Klaim atomik (`BEGIN IMMEDIATE` + `UPDATE … WHERE status='queued'` + cek `rowcount`) — dua worker
  paralel diuji: tepat satu yang menang.
- Lease + heartbeat; lease kedaluwarsa → antre ulang; setelah `max_attempts` → `failed` + kredit dilepas.
- Budget dua arah: token dipotong ke budget (`budget_exceeded`) dan wall-clock (`time.monotonic`).
- Executor berupa fungsi murni `job -> ExecutionResult`; `echo_executor` untuk uji alur penuh.

### Added — API

`/v1/worker/claim` · `/v1/jobs/{id}/heartbeat` · `/v1/jobs/{id}/complete` (X-Worker-Key) ·
`/v1/jobs/{id}/cancel` · `/v1/billing` · `/v1/ledger` · `/v1/invoices` · `/v1/credits/topup` (admin) ·
`/v1/admin/revenue`.

### Changed

- `Store` memakai autocommit + transaksi eksplisit; pembuatan job kini satu transaksi bersama hold kredit.
- Paket `runtime/` tanpa impor di `__init__` agar `python -m …worker` tidak memuat modul dua kali.

### Catatan

- Smoke end-to-end: hold 6.400 μUSD → 1.814 token → charge 2.903 μUSD → saldo 24.997.097/25.000.000
  → invoice 2.903 μUSD (1 job).
- Belum ada: pembayaran (kartu/VA), pajak, proration upgrade, dunning, prioritas antrean,
  dead-letter queue, sandbox eksekusi, metrik Prometheus.
- **Riwayat git dibersihkan** (`git filter-repo`): `runs/`, `evidence/`, `verification/`, `normalized/`,
  `reconstruction/` dihapus dari 96 commit. `.git` 38 MB → 2,7 MB; 0 objek artefak tersisa; isi HEAD
  di luar artefak identik; tag `v0.4.0`/`v0.5.0` dipertahankan (SHA ditulis ulang). Backup:
  `~/sdb-archive/pre-purge-20261029/` (mirror + bundle). Remote `origin` dilepas filter-repo —
  **belum** di-push ulang; push paksa ke remote bersama butuh keputusan terpisah.

## [0.4.0] — 2026-10-29

Rilis pertama yang **layak ditawarkan**: lisensi jelas, batas tenant ditegakkan mesin, artefak tidak lagi
membengkakkan git. Belum ada billing, worker, atau SSO — lihat `docs/ARSITEKTUR_SAAS.md` untuk sisa fase.

### Added — legal

- `LICENSE` Business Source License 1.1: penggunaan non-produksi bebas; produksi untuk klien atau sebagai
  bagian layanan berbayar butuh perjanjian komersial; produksi internal badan hukum sendiri ≤250 job/bulan;
  Change Date 2030-10-26 → Apache-2.0.
- `NOTICE` dan `THIRD_PARTY_NOTICES.md`: kewajiban MIT (`rea-agents`) dan **CC-BY-SA-4.0**
  (`trailofbits/skills`) dipisahkan; paket berbayar tidak boleh menyerap skill share-alike sebagai milik SDB.
- 39 `SKILL.md` diselaraskan dari MIT ke BUSL-1.1.

### Added — skala & distribusi

- `platform/schemas/` (tenant, job, artifact) + contoh valid; `scripts/pack_build.py` dan
  `platform/packs/*.json` untuk 8 divisi (77 entri skill, sha256 per SKILL.md).
  Verifier menolak hash drift, lisensi share-alike di paket BUSL, dan pack >25 skill.
- `sdb_platform/control_plane/` (Fase 2a): tenant, isolasi baca 404 lintas tenant, kuota job/token/storage,
  job idempoten, artefak wajib status redaksi, API key per tenant. HTTP stdlib + SQLite.
- `scripts/archive_artifacts.py`: 299 berkas / 33,5 MB artefak (`runs/`, `evidence/`, `verification/`,
  `normalized/`) diarsipkan ke luar git dengan manifest sha256 (0 mismatch); berkas kerja tidak dihapus.

### Changed

- `make check` kini juga menjalankan `hygiene` dan `packs`; `ruff` mencakup `sdb_platform/`.
- 4 skrip pilot dipindah dari `runs/rt-rw-portal/tools/` ke `scripts/privasi/portal-rt-rw/` (kode tidak
  boleh tinggal di direktori artefak).
- Repo terlacak: 483 → 327 berkas; `.gitignore` memakai pola `/dir/*` + `!/dir/INDEX.md` agar indeks tetap
  terlacak.

### Fixed

- `repo_hygiene.py` false positive pada email paket SBOM (`click@8.6.0.dev`) dan pada angka panjang di SBOM;
  regex PII sekarang butuh penanda field.
- `tests/test_platform_contracts.py` bug presedensi `and/or` yang meloloskan validasi tipe.

### Catatan

- Riwayat git masih memuat blob lama (±37 MB). Pembersihan dengan `git filter-repo` **belum** dijalankan —
  tidak bisa dibatalkan, menunggu approval Owner.
- Nama paket Python `sdb_platform` dipilih karena `platform` (stdlib) dan `sdb` (ditutupi `scripts/sdb.py`)
  tidak bisa dipakai. Lihat `docs/adr/0004`.

## [0.3.0] — sebelum 2026-10-26

Integrasi REA (`rea-agents@6.8.0`, MIT, commit terpin, MCP tidak aktif), audit ganda SDB, fondasi kontrak
Fase 0, gerbang higiene, dan indeks dokumen. Tidak pernah ditandai sebagai tag.
