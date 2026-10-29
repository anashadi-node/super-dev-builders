# Changelog

Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/) dan [SemVer](https://semver.org/lang/id/).

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
