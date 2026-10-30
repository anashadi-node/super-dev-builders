---
name: ci-cd-release-gate
description: "Pipeline build, test, scan, staging, prod, approval"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
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
6. **Artefak bukti buatan skrip WAJIB memenuhi kontrak Evidence Schema.** Keluaran mentah alat
   pihak ketiga (semgrep/trivy/syft/...) yang ditulis APA ADANYA ke `reports/` menutupi blok
   metadata level-atas (`provenance`, `captured_at`, `redaction_status`, `status`) → `evidence_lint`
   FAIL ("metadata wajib hilang") dan gerbang bukti pecah. Satu jalan benar: helper yang menaruh
   kontrak di level-atas dan **menitipkan keluaran mentah di kunci `raw`** (data utuh, nol
   kehilangan bukti). Verifikasi sebelum tulis: `scan_for_secrets(raw)` = 0 hit; sesudah tulis:
   `out["raw"] == raw` True. **Tutup dengan tes**, bukan disiplin manual — gate manual terbukti
   terlewat saat commit: `assert evidence_lint.main(<dir bukti terlacak>) == 0` + kontrol negatif
   (`evidence_lint.main(<bentuk mentah apa adanya>) == 1`). Gate yang hanya "diingat" bukan gate.
7. **Re-run artefak bukti: bandingkan ANGKA, bukan byte.** Skrip bukti yang menstempel
   `captured_at`/ID alat (`ReportID`, `CreatedAt`) dan urutan temuan menghasilkan byte BERBEDA
   di tiap jalan walau angkanya sama — jangan mengklaim "idempoten byte" tanpa membuktikannya.
   Sebelum commit: bandingkan angka substantif (findings/severity/secret/misconfig); bila sama,
   `git restore` berkas bukti dan JANGAN commit timestamp baru. **Warning nyata:** scanner bisa
   TIDAK deterministik antar-jalan (semgrep `p/default` context7: 90 -> 88 temuan; 0/0 rahasia
   tetap) — catat angka, jangan jadikan jaminan reproducibility. Untuk skrip scan pihak-ketiga:
   serialkan dengan `fcntl.flock` (cegah balapan `__pycache__` antar-instance -> `ModuleNotFoundError:
   sdb_common` intermiten), set `sys.dont_write_bytecode = True`, dan tulis ulang HANYA bila
   tanda-tangan substantif berubah (sisanya "TIDAK BERUBAH").
8. **Gerbang wajib menilai himpunan yang AKAN di-commit, bukan yang sudah ter-commit.**
   Pemindai berbasis `git ls-files` saja buta terhadap berkas baru yang belum `git add`:
   lokal PASS, CI FAIL untuk isi yang sama (nyata 30 Okt 2026 — email uji di berkas baru).
   Aturannya: `git ls-files -co --exclude-standard` (terlacak + baru, hormati `.gitignore`),
   artefak run masuk `.gitignore`, dan **buktikan dengan uji negatif**: berkas belum-commit
   berisi pelanggaran HARUS membuat gerbang lokal FAIL. Berkas baru = kandidat commit,
   jadi menunggu `git add` berarti menilai setelah terlambat.
9. **Paritas CI = daftar prasyarat + daftar langkah, diuji mesin — bukan diingat manusia.**
   Uji keamanan yang bergantung alat host (mis. `tesseract` untuk kanal media) akan merah
   berhari-hari bila image runner tidak memasangnya, tanpa ada kode yang berubah. Karena itu:
   (a) prasyarat dideklarasikan sekali di skrip (`perlu = [...]`), dipasang eksplisit di
   workflow, dan ada tes yang mem-parse workflow untuk memastikan setiap nama muncul di
   baris `apt-get install`; (b) setiap langkah `make check` lokal juga ada di CI — diuji
   dengan tes yang sama (temuan nyata: `make packs` tidak pernah jalan di CI); (c) langkah CI
   mencetak `git ls-files -co --exclude-standard | wc -l` supaya selisih himpunan berkas
   lokal vs runner langsung terbaca di log; (d) uji yang butuh alat host memakai `skip`
   beralasan bila alat tidak ada, JANGAN `xfail`/hapus — dan pastikan CI-lah yang
   menjalankan jalur aslinya.
10. **Gerbang yang tidak pernah sampai ke manusia bukan gerbang.** CI merah 30 Okt 2026
   bertahan berhari-hari (5 run berturut) bukan karena gerbangnya lemah, tetapi karena
   hasilnya hanya masuk surel yang tak dibaca. Wajib ada alarm yang: (a) **idempoten** —
   state menyimpan run yang sudah dilaporkan, satu kegagalan dikirim sekali; (b) **gagal-closed** —
   bila pemeriksa tidak bisa jalan (`gh` hilang, kuota habis, JSON rusak) hasilnya
   "GAGAL MEMERIKSA" (exit 2), bukan "hijau"; (c) **punya bukti lokal** — setiap kejadian
   ditulis ke JSONL sehingga tidak bergantung kanal jaringan; (d) melaporkan keadaan merah
   yang sedang berlangsung saat pemasangan pertama, tetapi tidak membanjiri dengan
   kegagalan historis. Kontrol negatifnya: pemanggilan kedua tidak boleh mengirim ulang,
   dan pemeriksa yang rusak tidak boleh menghasilkan "BERSIH".
- Tidak ada `--force`, `--no-verify`, atau bypass gate. Tidak ada auto-approve untuk aksi destruktif/
  publikasi/produksi.
- Credential hanya lewat secret store; tanpa secret di log/artefak.

## Output
- Konfigurasi pipeline + `reports/deploy-<versi>.md` (build, test, scan, approval, smoke, rollback ref).
