# Pinned Vendor: replica-skill @ 77c9436

Sumber: https://github.com/Jakeschincariol/replica-skill
Commit: 77c9436fb3d18c3d58169efb8caf4fe906b0dc51 (2026-10-03)
Vendor: 52 file (11 skill directory + tests + LICENSE + README + .claude-plugin)
SHA-256 file tree: 2d82e189436d3608695fdc4684d9b6486f4252bad99a65d1a9c3f73e16f36278

## Status audit (30 Okt 2026, Hermes Anantara v3)

| Pemeriksaan | Hasil |
|---|---|
| pytest tests/ (upstream) | 57 passed |
| Network sinks (urlopen/socket/subprocess/os.system) | 0 |
| eval/exec/base64 decode/wget/curl di helper | 0 |
| install/postinstall hooks | 0 |
| `.gitattributes`, symlink, binary blob | 0 |
| Helper 6 file: stdlib only (argparse, csv, json, math, struct, zlib, re, unicodedata) | YA |
| Helper hanya write ke path argumen `--out` (imgdiff.py write_png) | YA |
| SKILL.md instruction-injection scan | 0 temuan |

Dilindungi PRD acuan: PRD_Super_Dev_Builders.html Lampiran B
(commit 77c9436 diaudit 2026-10-30 — hasil konsisten dengan vendor ini).

## Aturan penggunaan (dari PRD, bagian 2, 6, 7)

1. Skill ini hanya dipakai untuk Zona B (pembangun) — recon publik, architect,
   design, build, backend, test, diff, brand, launch, deploy.
2. Pembangun TIDAK PERNAH membaca `evidence/<target>/10-evidence/` atau artefak
   mentah REA. Jembatan satu-satunya: `reconstruction/<target>/SPEC.md`.
3. Mode C (tanpa izin khusus): tanpa dekompilasi, tanpa private API, tanpa
   konten berhak cipta. Mode A/B tunduk pada gate0 (workflows/gate0.yaml).
4. Rilis butuh G3: 0 aset hash-sama dengan target, 0 string identik >=40 char,
   0 rahasia + persetujuan manusia.
5. Kenaikan versi upstream = kandidat baru; wajib audit ulang (G0-G2) sebelum
   diaktifkan. Tidak ada @latest.

Tidak diinstal ke Hermes global — vendored + pinned sesuai PRD bagian 12 (Phase 1-2).
