---
name: reconstruction-fidelity
description: "Use to measure rebuilt result vs target evidence per dimension, with coverage."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [reconstruction, fidelity, verification, coverage, visual-diff]
    divisions: [D1, D6, D7]
    related_skills: [reconstruction-spec, accessibility-audit, test-pyramid-and-risk]
---


# Reconstruction Fidelity

Mengukur seberapa dekat hasil rebuild dengan target **per dimensi, plus coverage** — tanpa skor tunggal palsu.

## Dimensi & evidence
| Dimensi | Cara ukur |
|---|---|
| Visual | screenshot diff (Playwright assertion) pada viewport yang sama |
| Navigation | bandingkan route/screen graph + journey yang diuji |
| Interaction | checklist form/dialog/state/keyboard/touch |
| Responsive | matriks breakpoint/device |
| Functional coverage | feature matrix: observed / reproduced / intentionally changed / unknown |
| Accessibility | axe-core + manual untuk inconclusive |
| Performance | Lighthouse/runtime, catat environment (jaringan, perangkat, cache) |
| API contract | contract test observed/authorized |

## Prosedur
1. Ambil screenshot target & hasil pada viewport identik, lalu diff (`scripts/fidelity_report.py` untuk agregasi).
2. Jalankan test E2E untuk journey kritis; catat pass/fail per journey.
3. Jalankan axe-core; tandai `incomplete` sebagai butuh review manual — bukan lulus.
4. Lighthouse untuk halaman utama; catat varians antar-run.
5. Susun tabel: dimensi, skor/status, **coverage**, evidence.

## Aturan pelaporan
- Wajib menyertakan coverage; skor tinggi + coverage rendah = laporan menyesatkan.
- Perbedaan visual yang disengaja (mis. lisensi aset) dicatat sebagai `intentionally_changed`, bukan "bug".
- Jangan menyatakan "identik" dalam kondisi apa pun.
