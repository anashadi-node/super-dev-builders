---
name: product-execution
description: "Execute next .planora TODO item with proof"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [execution, todo, workflow-dispatch]
    divisions: [D0, D4, D5, D7]
    related_skills: [product-status, feature-workflow, bug-workflow, chore-workflow]
---

# Product Execution (adopsi PLANORA `planora-next`)

Alur kerja asli: `WORKFLOW.md`. Dispatch satu tugas, lalu berhenti — bukan loop tak terbatas.

## Prosedur
1. Jalankan `product-status` untuk menentukan tugas berikutnya yang siap-dependensi.
2. Baca tugas di `EXECUTION/TODO.md`: acceptance criteria, `Workflow`, skill pendukung yang dirujuk.
3. Eksekusi TEPAT satu item sesuai workflow-nya (feature/bug/chore), bukan tugas lain sekaligus.
4. Tandai `done` HANYA setelah acceptance criteria + bukti validasi lulus (aturan upstream).
5. Laporkan: item dikerjakan, bukti, status TODO baru, saran item berikutnya.

## Aturan
- Tidak boleh melemahkan acceptance criteria demi menyelesaikan tugas.
- Dependency `blocked`/belum selesai = tugas tidak boleh dieksekusi.
- Prasyarat hilang (browser automation, environment, kredensial) → berhenti SEBELUM mengklaim validasi; laporkan prasyarat persisnya (pola upstream `Blocked`).
- Kredensial apapun tetap [REDACTED] di seluruh laporan (kebijakan rumah).

## Output
- Laporan eksekusi 1 item + bukti + update status TODO.
