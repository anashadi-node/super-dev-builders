---
name: chore-workflow
description: "Scoped maintenance that preserves behavior"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [maintenance, refactor, behavior-preserving]
    divisions: [D4, D5]
    related_skills: [feature-workflow, bug-workflow]
---

# Chore Workflow (adopsi PLANORA `chore`)

Alur kerja asli: `WORKFLOW.md`.

## Prosedur
1. Definisikan scope maintenance + bukti "perilaku tetap" (test yang membuktikan tidak ada perubahan perilaku).
2. Rencana ringkas sesuai format `WORKFLOW.md` (langkah, berkas, verifikasi).
3. Eksekusi + jalankan test perilaku → PASS; tanpa perubahan semantik di luar scope.
4. Laporkan sebelum/sesudah (ukuran, jumlah berkas, hasil test).

## Aturan
- Behavior-preserving = acceptance criteria lama tidak boleh diubah sama sekali.
- Tidak menggabungkan chore dengan perubahan fitur/bug (satu commit satu maksud).
- Test suite wajib PASS sebelum klaim selesai (selaras Pre-Deploy Review rumah).

## Output
- Rencana + perubahan + bukti test PASS + ringkasan before/after.
