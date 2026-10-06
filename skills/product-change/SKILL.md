---
name: product-change
description: "Merevisi paket .planora dari perubahan produk yang diminta eksplisit: update PRD/panduan/TODO + bump versi + tandai artefak hilir stale. Tidak mengimplementasikan kode. Panggil eksplisit."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [revision, prd, traceability, change-control]
    divisions: [D0, D2]
    related_skills: [product-kit, product-status]
---

# Product Change (adopsi PLANORA)

Membungkus `planora-change` upstream. Alur kerja asli: `WORKFLOW.md`.

## Prosedur
1. Pastikan perubahan produk diminta eksplisit Owner (skill ini non-implisit).
2. Ikuti `WORKFLOW.md`: identifikasi artefak sumber yang berubah (prd/ui/dx/execution), tulis revisi, pertahankan requirement ID stabil.
3. Propagasi versi via `product-kit`:
   `python <skill-dir product-kit>/scripts/update_revision.py <paket> --changed prd --reason "<alasan>"`
   → artefak hilir otomatis `stale`, `revisionHistory` terisi.
4. Validasi sampai 0 error (validator `product-kit`).
5. Serahkan implementasi ke `feature-workflow`/`bug-workflow` sebagai handoff — skill ini TIDAK menulis kode aplikasi.

## Aturan
- One-way door: revisi tanpa alasan kosong ditolak (`--reason` wajib, guard upstream).
- Status `stale` artinya artefak hilir wajib direview ulang sebelum eksekusi — jangan eksekusi tugas stale tanpa re-approve.
- Tidak melemahkan acceptance criteria saat merevisi (aturan upstream dipertahankan).

## Output
- Paket `.planora` terevisi + manifest `revisionHistory` + bukti validator 0 error.
