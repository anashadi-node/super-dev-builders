---
name: product-kit
description: "Membuat/merevisi paket perencanaan produk terlacak (.planora): PRD + panduan UI/DX + rencana eksekusi ber-requirement-ID. Panggil eksplisit saat Owner minta paket PRD produk baru atau revisi."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [planning, prd, product, traceability]
    divisions: [D0, D2, D3]
    related_skills: [product-status, product-change, product-execution]
---

# Product Kit (adopsi PLANORA)

Membungkus alur kerja PLANORA `planora-product-kit` (upstream ter-audit 2026-10-06, laporan: `reports/planora_audit_20261006.md`). Alur kerja asli: `WORKFLOW.md` di direktori skill ini. Perbedaan rumah: id di-register ekosistem, bahasa laporan mengikuti konvensi SDB, dan wajib Gate #0 sebelum menyentuh repo target.

## Prosedur
1. Konfirmasi Gate #0 PASS untuk repo target.
2. Ikuti `WORKFLOW.md` langkah 1–10 (intake → klasifikasi ui/dx/hybrid → context ledger → PRD → panduan → eksekusi → manifest → quality gate).
3. Scaffold paket baru:
   `python <skill-dir>/scripts/scaffold_product_kit.py --name "<Nama>" --output <root-absolut> --guide-type ui --locale id-ID`
4. Setelah revisi artefak, propagasi status stale:
   `python <skill-dir>/scripts/update_revision.py <paket> --changed prd --reason "<alasan>"`
5. Wajib tutup dengan validator sampai 0 error:
   `python <skill-dir>/scripts/validate_product_kit.py <paket>`
6. Jalankan test skill sebelum commit perubahan script:
   `python -m pytest <skill-dir>/tests -q`

## Aturan
- Tidak pernah mengubah kode aplikasi target saat membuat/merevisi paket (aturan upstream, dipertahankan).
- Marker `__PLANORA_REQUIRED__` yang tersisa = paket belum sah; jangan dianggap selesai.
- Larangan upstream dipertahankan: tanpa fakta/research/stack yang dikarang; asumsi dilabel eksplisit.
- Skrip hanya menulis di dalam `<output>/.planora`; tolak path `..` (guard upstream sudah ada).

## Output
- `.planora/` lengkap (README.md, manifest.json, PRD/, UI/ atau DX/, EXECUTION/) di root repo target.
- Bukti validator 0 error disisipkan di laporan tugas.
