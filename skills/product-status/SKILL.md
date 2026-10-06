---
name: product-status
description: "Inspeksi read-only paket .planora: status eksekusi, blocker, dan tugas berikutnya yang siap-dependensi. Panggil eksplisit saat Owner tanya 'status proyek ini?' pada repo ber-.planora."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [status, read-only, execution, reporting]
    divisions: [D0, D7]
    related_skills: [product-kit, product-execution]
---

# Product Status (adopsi PLANORA)

Membungkus `planora-status` upstream (read-only murni). Alur kerja asli: `WORKFLOW.md`. Inspector: `scripts/inspect_product.py`.

## Prosedur
1. Jalankan inspector dari root repo:
   `python <skill-dir>/scripts/inspect_product.py --root <repository-root>`
2. Baca laporan JSON: state paket, hitungan tugas (pending/in_progress/done/blocked/skipped), blocker aktif.
3. Untuk konteks, baca `EXECUTION/TODO.md` + fase tugas berikutnya; bila repo memakai Git, gunakan `git status --short` dan `git diff --name-status` sebagai bukti perubahan — bukan bukti kelulusan.
4. Laporkan: tugas `in_progress` (lanjutkan dulu), blocker, tugas pertama yang siap-dependensi + alasannya.

## Aturan
- **Strictly read-only**: tidak pernah mengubah TODO, dokumen, kode, atau state Git (aturan upstream dipertahankan keras).
- Tidak menyimpulkan "selesai" dari keberadaan kode; hanya dari status terekam + bukti validasi.
- Paket hilang/invalid = laporkan + saran koreksi persis; JANGAN memperbaiki file sendiri.

## Output
- Ringkasan status + tugas berikutnya + blocker, dengan bukti (TODO/inspector JSON).
