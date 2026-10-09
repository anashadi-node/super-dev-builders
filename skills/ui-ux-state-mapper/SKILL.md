---
name: ui-ux-state-mapper
description: "Map screens, navigation, components, states"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [reconstruction, ui, ux, playwright, state-map]
    divisions: [D1]
    related_skills: [evidence-normalizer, observed-network-contract]
---


# UI/UX State Mapper

Mengubah observasi browser menjadi peta UI/UX yang dapat dibangun ulang: layar, navigasi, komponen, state, responsif.

## Prosedur
1. Playwright (primary): buka target, tunggu network idle, ambil screenshot per viewport wajib
   (mobile 390x844, tablet 768x1024, desktop 1440x900 — sesuaikan bila target punya breakpoint sendiri).
2. Simpan DOM/snapshot elemen per layar. Jangan simpan nilai sensitif: bersihkan `input[type=password]`,
   header Authorization, cookie, localStorage berisi token.
3. Bangun navigation graph: dari state X, aksi apa membawa ke state Y (hover/focus/klik/back).
4. Inventaris komponen: nama fungsional, prop yang terlihat, state (default/hover/active/disabled/loading/error/empty).
5. Responsive: catat perubahan layout/nav (hamburger, kolom collapse), bukan hanya ukuran.
6. Tandai design token yang teramati (warna, tipografi, spacing, radius, shadow). Yang tidak teramati => UNKNOWN.

## Format output
- `normalized/<target>/screens.json`, `components.json`, `actions.json`
- Semua record: `status` (FACT/INFERRED/UNKNOWN), `provenance`, `captured_at`, `redaction_status`.

## Larangan
- Tidak menyimpan kredensial/token/PII pada screenshot/DOM (blur atau hapus sebelum menyimpan).
- Tidak mengubah data target (jangan submit form nyata yang mengubah state produksi; gunakan akun test).
- Tidak melakukan aksi destruktif (delete/checkout/cancel order) walau secara teknis bisa.

## Judgement
- "Tampilan mirip" bukan bukti: setiap klaim komponen harus menunjuk screenshot/DOM.
