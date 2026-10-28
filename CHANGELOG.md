# Changelog

Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/) dan [SemVer](https://semver.org/lang/id/).

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
