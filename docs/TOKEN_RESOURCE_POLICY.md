# Token & PC Resource Policy

Sumber: blueprint §8. Target: kapabilitas maksimal dengan konsumsi minimum.

1. **Sequential by default.** Maksimum 1-2 spesialis aktif. Paralel hanya untuk task independen yang benar-benar menghemat waktu.
2. **Progressive disclosure.** Muat SKILL.md/reference hanya saat terpicu; jangan pra-muat seluruh pengetahuan divisi.
3. **Artifact handoff.** Requirement/ADR/diff/SARIF/test report — bukan transkrip lengkap.
4. **Diff-first review.** Reviewer menerima requirement + Git diff + file terkait saja.
5. **Tool before model.** Compiler/linter/test/scanner menjawab fakta deterministik lebih murah dan lebih akurat.
6. **Bounded loops.** Maksimum 2-3 siklus perbaikan, lalu eskalasi. Cegah infinite token loop.
7. **Cheap model untuk rutin**; model kuat untuk arsitektur, debugging kompleks, triase security, audit final
   (lihat `docs/MODEL_ROUTING_MATRIX.md`).
8. **No duplicate skill families.** Satu metodologi utama per kebutuhan; skill kedua hanya bila specialist.

## PC resource policy
- Divisi lazy/on-demand: jangan spawn semua divisi bersamaan (konflik & boros).
- Tool berat (CodeQL, Ghidra, MobSF, emulator mobile) hanya dipanggil saat dibutuhkan — bukan bagian pipeline default.
- Capture/browser worker: batasi viewport, jumlah route, dan retry; simpan artefak ke disk, bukan ke konteks.
- Scan cepat (Semgrep/Trivy) untuk siklus harian; scan berat (CodeQL) untuk milestone/release atau area berisiko tinggi.
- Estimasi konsumsi token dan kapasitas host dicatat di `reports/token-estimate.md`.
