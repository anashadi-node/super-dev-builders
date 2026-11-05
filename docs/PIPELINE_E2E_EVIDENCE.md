# Pipeline Reconstruction — Bukti Uji End-to-End (2026-10-04)

Target uji: **`sdb-local-demo`** — aplikasi web kecil **milik sendiri** (Mode A, hanya `127.0.0.1`).
Alasan memakai target sendiri: Gate #0 wajib otorisasi; ini menguji pipeline tanpa menyentuh pihak ketiga.

## 1. Hasil ringkas

| # | Tahap | Perintah | Hasil | Exit |
|---|---|---|---|---|
| 1 | Inisialisasi target | `init_target.py sdb-local-demo --platform web --mode A` | struktur `evidence/ normalized/ reconstruction/` + template manifest | 0 |
| 2 | Gate #0 (positif) | `gate_check.py --target sdb-local-demo` | **PASS** | 0 |
| 3 | Gate #0 (izin ada, approval manusia kosong) | `gate_check.py --manifest /tmp/sdb-e2e-blocked.yaml` | **BLOCKED** | 2 |
| 4 | Gate #0 (jenis otorisasi tak sah) | `gate_check.py --manifest /tmp/sdb-e2e-fail.yaml` | **FAIL** | 1 |
| 5 | Capture terkendali | `capture_web.py --target sdb-local-demo …` | 2 halaman, 6 request/6 response; screenshot, DOM (sha256), fakta UI, network, hasil klik | 0 |
| 6 | Redaksi | `redact_network.py … --in-place` | header `x-demo-session` → `REDACTED`; nilai sensitif 1 → **0**; mentah disimpan `.raw` | 0 |
| 7 | Normalisasi | `normalize_capture.py --target sdb-local-demo` | 5 berkas `normalized/sdb-local-demo/*.json`, 27 record, metadata lengkap | 0 |
| 8 | Evidence lint | `evidence_lint.py normalized/sdb-local-demo` | **PASS** (5 file, 27 record) — sebelumnya FAIL dan menangkap bug nyata di normalizer | 0 |
| 9 | Fidelity | `fidelity_compare.py` + `fidelity_report.py` | 9 dimensi terukur + coverage + gambar diff | 0 |
| 10 | Release gate (tanpa artefak) | `release_check.py --project .` | **FAIL** — benar: tidak ada artefak = tidak ada PASS | 1 |
| 11 | Release gate (artefak lengkap) | `release_check.py --project runs/sdb-local-demo` | **PASS** — 7/7 gerbang, umur artefak < 24 jam | 0 |

## 2. Fidelity — 9 dimensi (bukan klaim, tapi angka)

Dimensi: 8 inti (visual, navigation, interaction, responsive, functional, accessibility, performance,
api_contract) + `external_dependency` (jumlah request ke host pihak ketiga: original vs rebuild).

| Dimensi | Status | Coverage | Bukti |
|---|---|---|---|
| visual | ok | ~0,60 | `verification/sdb-local-demo/diffs/visual-index.png` (gaya **sengaja** diubah) |
| navigation | ok | 1,00 | Jaccard tautan identik |
| interaction | ok | 1,00 | klik `#btn-load` → teks `<state> @ <ts>` di kedua versi |
| responsive | ok | 0,96 | pixel diff viewport 390x844 |
| functional | ok | 1,00 | status HTTP per halaman sama |
| accessibility | ok | 1,00 | `h1` + `role=status` + `aria-label` ada di keduanya |
| performance | ok | 1,00 | rasio load time dibatasi 1,0 |
| api_contract | ok | 1,00 | `GET /api/status` → 200, kunci JSON sama (`state`, `ts`) |

Laporan lengkap: `reports/sdb-local-demo/fidelity-report.md`.

## 3. Bug nyata yang tertangkap gate (bukti gate berguna)

| Temuan | Ditangkap oleh | Perbaikan |
|---|---|---|
| `Path.relative_to()` absolut vs relatif → crash setelah screenshot pertama | jalankan nyata | `os.path.relpath` |
| field `status` ganda: kode HTTP menimpa metadata evidence | **`evidence_lint` FAIL** | dipisah ke `http_status` |
| klaim test "21 custom skill" rapuh saat registry bertambah | pytest | diganti invariant registry ↔ direktori `skills/` |
| header sensitif tersimpan apa adanya | uji redaksi | `redact_network.py` + verifikasi hitungan 0 |

## 4. Yang BELUM diuji (dinyatakan jujur)
1. ~~Target eksternal web publik~~ **SELESAI SEBAGIAN 2026-10-04**: target open-source MIT teruji (§5). Sisa: APK/IPA, aplikasi desktop, dan web non-open-source (butuh otorisasi berbeda).
2. Analisis mendalam Mode B (jadx/apktool/ghidra/MobSF) — belum dipasang, masih `quarantine`.
3. CodeQL pada kode internal ekosistem — **dilarang lisensi**; internal memakai Semgrep/ruff/trivy/syft. CodeQL hanya dipakai pada target open-source/akademik (§5).
4. `syft` pada target demo: "No packages discovered" karena tidak ada manifest — bukan bukti bebas kerentanan.
5. Dimensi backend/internal tetap `UNKNOWN`: tidak diamati dan tidak dikarang.

## 5. Target KEDUA — web OPEN-SOURCE (`oss-sb-agency`, 2026-10-04)

Target: `startbootstrap/startbootstrap-agency` @ `b2d5d5c6b1396bc5b0e8dd92c693b106cfb7cee1`, lisensi **MIT**
(berkas `LICENSE` dibaca langsung + `license.spdx_id=MIT`). Mode A, salinan `dist/` lokal; host produksi tidak disentuh.

| # | Tahap | Hasil | Exit |
|---|---|---|---|
| 1 | Gate #0 | **PASS** (otorisasi `open_source`, scope `127.0.0.1:8200` target + `:8201` rebuild) | 0 |
| 2 | Capture | 4 capture (desktop 1440x900 + mobile 390x844, original + rebuild), **0 error**, 32/32 & 3/3 request/response | 0 |
| 3 | Redaksi + normalisasi + lint | PII diredaksi; `evidence_lint` **PASS** (5 berkas, 77 record) | 0 |
| 4 | SPEC + rebuild clean-room | `reconstruction/oss-sb-agency/` (280 baris, HTML+CSS+JS sendiri; penyimpangan D1–D6) | 0 |
| 5 | Fidelity | 9 dimensi: visual 0,66 · navigation **1,00** · interaction **1,00** · functional 1,00 · accessibility 1,00 · performance 1,00 · responsive 0,57 · `api_contract` **NOT_OBSERVED** · `external_dependency` **1,00** | 0 |
| 6 | Security statis | CodeQL JS `security-and-quality`: **15/15 berkas, 201 aturan, 0 temuan keamanan**; Semgrep: **45 berkas, 1074 aturan, 0 temuan**; Trivy: 0 vuln/misconfig/secret; SBOM SPDX-2.3 (4 paket) | 0 |
| 7 | Release gate | **PASS** 7/7 (`runs/oss-sb-agency/reports/release-verdict.json`) | 0 |
| 8 | Tes suite | **42 passed** (25 lama + 17 baru untuk logika fidelity) | 0 |

### 5.1 Temuan penting (dan perbaikannya)
| Temuan | Ditangkap oleh | Perbaikan |
|---|---|---|
| `fidelity_compare.py` hardcode demo (`#btn-load`, `/api/status`, `role=status`) — akan memberi "mismatch" palsu di target lain | tinjauan sebelum dipakai | digeneralisasi: interaksi berbasis jejak efek, API `NOT_OBSERVED` bila tak ada, a11y berbasis paritas fitur original, + dimensi `external_dependency` |
| `external_requests()` tidak mengenali `network.json` (`{"items":[…]}`) → dimensi dependensi membaca kosong | **17 tes baru** | diperbaiki + 4 tes khusus |
| Pemicu modal memakai `<button>` → 6 `href` hilang, navigasi 0,57 | fidelity run | diubah ke `<a href="#portfolioModalN">` → **1,00** |
| Klik desktop `.navbar-toggler` timeout (elemen memang tersembunyi di desktop) | capture error | interaksi desktop memakai `.portfolio-link` |
| Semgrep `0 temuan` **vacuous** ("limited to files tracked by git", 0 berkas dipindai) | verifikasi `paths.scanned` | dijalankan ulang dengan `--no-git-ignore`: **45 berkas** dipindai |
| CodeQL pack JS gagal unduh (transient) → pack kosong | verifikasi `.ql` count = 0 | ulangi `codeql pack download` → 363 berkas `.ql` |

### 5.2 Deltas yang disengaja (bukan cacat)
Rebuild tidak menghubungi host pihak ketiga sama sekali: **8 request / 5 host → 0** (Google Fonts, jsDelivr,
FontAwesome, cdn.startbootstrap). Konsekuensinya visual 0,66 dan responsif 0,57 — dilaporkan apa adanya, bukan
dinaikkan dengan menyalin aset pihak ketiga (lisensi & privasi). Detail: `reports/oss-sb-agency/fidelity-report.md` §3.

