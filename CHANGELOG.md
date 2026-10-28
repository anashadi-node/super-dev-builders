# Changelog

Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/) dan [SemVer](https://semver.org/lang/id/).

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
