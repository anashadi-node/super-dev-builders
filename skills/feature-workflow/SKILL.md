---
name: feature-workflow
description: "Scoped feature: plan, implement, verify"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux, macos]
metadata:
  hermes:
    tags: [feature, implementation, scoped-change]
    divisions: [D4, D5]
    related_skills: [bug-workflow, chore-workflow, product-execution]
---

# Feature Workflow (adopsi PLANORA `feature`)

Alur kerja asli: `WORKFLOW.md` (6,6 KB, pola rencana-terstruktur upstream).

## Prosedur
1. Klarifikasi ruang lingkup fitur: perilaku, batasan, non-goals; pertanyaan hanya untuk keputusan produk yang benar-benar menghalangi.
2. Susun rencana implementasi ringkas sesuai format `WORKFLOW.md` (langkah, berkas yang disentuh, verifikasi).
3. Implement + verifikasi per langkah rencana; guard upstream dipertahankan: lanjut di tugas yang sama kecuali ada keputusan produk/kredensial/side-effect eksternal/aksi destruktif yang butuh input user.
4. Tutup dengan bukti: test/exercize nyata, bukan klaim.

## Aturan
- Validate inputs di trust boundary; error handling anti data-loss (aturan upstream §engineering).
- Tidak pernah menaruh secret di source/log/fixture/commit (upstream §security, selaras Red Lines rumah).
- Perubahan di luar scope fitur = tolak; gunakan `chore-workflow` untuk maintenance ter-scope.

## Output
- Rencana implementasi + kode + bukti verifikasi per langkah.
