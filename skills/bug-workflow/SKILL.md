---
name: bug-workflow
description: "One defect: diagnose, fix, verify with evidence"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [bug, diagnosis, verification]
    divisions: [D4, D5, D7]
    related_skills: [feature-workflow, chore-workflow]
---

# Bug Workflow (adopsi PLANORA `bug`)

Alur kerja asli: `WORKFLOW.md`. Selaras disiplin rumah: reproduksi sebelum perbaikan (test reproduksi → PASS setelah fix).

## Prosedur
1. Reproduksi defect secara minimal + deterministik; catat langkah persisnya.
2. Susun rencana perbaikan ringkas sesuai format `WORKFLOW.md` (akar masalah, berkas, verifikasi).
3. Perbaiki + jalankan reproduksi → harus PASS; regresi tetangga dicek (test suite terkait).
4. Jika akar masalah tidak pasti setelah hipotesis habis → BERHENTI, ajukan 1 pertanyaan diagnostik (jangan tebak).

## Aturan
- Verifikasi wajib empiris (output nyata), bukan asumsi.
- Fix tidak boleh menambah dependency baru tanpa alasan + approval (pola Ponytail rumah).
- Side-effect eksternal/kredensial/destruktif → minta konfirmasi dulu (upstream guard dipertahankan).

## Output
- Langkah reproduksi + akar masalah + fix + bukti reproduksi-PASS.
