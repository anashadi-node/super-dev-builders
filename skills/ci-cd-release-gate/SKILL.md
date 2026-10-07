---
name: ci-cd-release-gate
description: "Use to wire build-test-scan-staging-approval-production with exit criteria."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [ci, cd, pipeline, release, gate, docker]
    divisions: [D10, D8]
    related_skills: [engineering-release-audit, rollback-and-recovery, release-handover-docs]
---


# CI/CD Release Gate

Pipeline deterministik: build -> test -> scan -> artefak -> staging -> **approval manusia** -> produksi.
Semua gate punya exit criteria; tidak ada gate "kira-kira lulus".

## Tahap & exit criteria
1. **Lint/format** — nol error; peringatan baru harus dibenarkan.
2. **Build** — sukses bersih dari commit yang sama dengan artefak; hash artefak dicatat.
3. **Test** — unit/integration/contract/E2E sesuai kelas risiko; tidak ada kegagalan tak terjelaskan.
4. **Security scan** — SAST (Semgrep cepat; CodeQL pada milestone), dependency/secret/misconfig (Trivy);
   triase temuan dengan aturan stop: critical/high terbuka => berhenti.
5. **Audit/assurance** — `release_check.py` PASS (artefak segar).
6. **Staging** — deploy + smoke test + observasi; rollback sudah siap & teruji.
7. **Approval manusia** — tercatat (nama, waktu, keputusan) di `reports/human-approval-required.md`.
8. **Produksi** — deploy bertahap, satu layanan sekaligus, verifikasi health setelah tiap langkah.
9. **Post-deploy** — smoke test, pantau log/metrik periode awal, siap rollback.

## Aturan
- Docker untuk build reproducible; **jangan** memberikan socket Docker host ke pekerjaan tak-terpercaya.
- Tidak ada `--force`, `--no-verify`, atau bypass gate. Tidak ada auto-approve untuk aksi destruktif/
  publikasi/produksi.
- Credential hanya lewat secret store; tanpa secret di log/artefak.
- **Suite uji WAJIB hermetik**: jangan pernah meng-assert state host (`~/.hermes/**`, skill terpasang,
  isi `$HOME`). Pisahkan — bagian spec/repo selalu diperiksa; bagian khusus host `pytest.skip(...)`
  dengan alasan eksplisit. Uji yang membaca state mesin pengembang lulus lokal tapi merah di runner
  bersih dan menyamarkan bug nyata.
- **Interpreter jangan hardcode** (`/usr/bin/python3`): di runner setup-python berada di path lain.
  Resolusi sadar-kapabilitas (`.venv` repo -> `python3` yang bisa `import pytest` -> `/usr/bin/python3`),
  mis. `PY_SYS ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; elif python3 -c "import pytest" 2>/dev/null; then echo python3; else echo /usr/bin/python3; fi)`.
- **Gerbang yang butuh Host** (drift skill) harus SKIP eksplisit di runner, bukan gagal dan bukan lulus
  diam-diam: `if [ -d "$HOME/.hermes/skills" ]; then ...; else echo "SKIP ..."; fi`.
- **Action pihak ketiga dipin ke commit SHA**, bukan tag bergerak; dependensi uji dibaca dari satu
  sumber (`pyproject.toml`), jangan diduplikasi di YAML.

- **Skill yang dicerminkan ke profil**: mengubah berkas repo saja membuat salinan
  terpasang (main + tiap profil di `~/.hermes/profiles/<p>/skills/...`) menyimpang →
  `make drift` MERAH. Urutan benar: patch repo -> sinkronkan SEMUA salinan terpasang
  -> `make check` hijau -> baru commit/push. Jangan pernah push sebelum gerbang lokal
  hijau walau CI lolos: CI tidak boleh jadi penemu cacat yang bisa dicegah lokal.

## Verifikasi SEBELUM push (jangan menyerahkan ke CI untuk menemukan cacat mendasar)
1. Reproduksi lingkungan runner secara lokal: salinan bersih (`git archive HEAD | tar -x -C /tmp/sim`),
   venv terpisah berisi hanya dependensi pyproject, `HOME` kosong, `PATH` hanya venv:
   `env -i PATH=<venv>/bin:/usr/bin:/bin HOME=/tmp/fakehome bash -c 'cd /tmp/sim && make check'`.
2. Jalankan juga di host nyata — keduanya harus hijau (atau SKIP dengan alasan).
3. Baru push; setelah push tonton run dan baca `--log-failed` bila merah.
4. **Output gerbang dari proses latar WAJIB dicek identitas/waktunya dulu.** Output `make check`/
   test yang datang lewat notifikasi proses bisa milik revisi KODE LAMA (stale) dan melaporkan
   kegagalan yang sudah diperbaiki — atau sebaliknya. Hanya output yang dijalankan pada revisi
   kerja saat ini yang sahih; kalau ragu, jalankan ulang. (Nyata: notifikasi EXIT=2 dari
   `proc_8b9b42feac50` pra-perbaikan `SLUG_RE` nyaris memicu "perbaikan" bug yang sudah hilang.)
5. **Triase temuan scanner tidak boleh melemahkan kontrol positifnya.** Menambahkan `nosemgrep`
   hanya sah bila (a) jalur berisiko sudah dijaga fail-closed DI TITIK PAKAI (bukan bergantung
   pemanggil) — pindahkan gerbang ke dalam fungsi, bukan cukup di `main()`; (b) ada kontrol
   positif yang membuktikan penolakan (mis. `file:///etc/passwd` DITOLAK); (c) kontrol positif
   tes keamanan tetap LULUS setelah anotasi — jangan pernah mengubah fixture jadi placeholder
   lemah agar scanner diam, itu mematikan tes yang menguji keamanan itu sendiri.
- Tidak ada `--force`, `--no-verify`, atau bypass gate. Tidak ada auto-approve untuk aksi destruktif/
  publikasi/produksi.
- Credential hanya lewat secret store; tanpa secret di log/artefak.

## Output
- Konfigurasi pipeline + `reports/deploy-<versi>.md` (build, test, scan, approval, smoke, rollback ref).
