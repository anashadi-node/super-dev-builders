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
| 9 | Fidelity | `fidelity_compare.py` + `fidelity_report.py` | 8 dimensi terukur + coverage + gambar diff | 0 |
| 10 | Release gate (tanpa artefak) | `release_check.py --project .` | **FAIL** — benar: tidak ada artefak = tidak ada PASS | 1 |
| 11 | Release gate (artefak lengkap) | `release_check.py --project runs/sdb-local-demo` | **PASS** — 7/7 gerbang, umur artefak < 24 jam | 0 |

## 2. Fidelity — 8 dimensi (bukan klaim, tapi angka)

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
1. Target eksternal: web publik, APK/IPA, aplikasi desktop (butuh Gate #0 + otorisasi berbeda).
2. Analisis mendalam Mode B (jadx/apktool/ghidra/MobSF) — belum dipasang, masih `quarantine`.
3. CodeQL pada kode internal ekosistem — **dilarang lisensi**; internal memakai Semgrep/ruff/trivy/syft.
4. `syft` pada target demo: "No packages discovered" karena tidak ada manifest — bukan bukti bebas kerentanan.
5. Dimensi backend/internal tetap `UNKNOWN`: tidak diamati dan tidak dikarang.
