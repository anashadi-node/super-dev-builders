---
name: release-handover-docs
description: "README, runbook, release notes at delivery"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [documentation, handover, readme, runbook, release-notes]
    divisions: [D11, D10]
    related_skills: [architecture-docs, rollback-and-recovery, ci-cd-release-gate]
---


# Release Handover Docs

Dokumen agar orang lain bisa menjalankan, memelihara, dan memulihkan sistem tanpa bertanya ke pembuatnya.

## Isi wajib (template: `templates/handover.md`)
1. Ringkasan: sistem ini apa, untuk siapa, masalah apa yang diselesaikan.
2. Cara menjalankan: prasyarat, instalasi, perintah menjalankan, perintah test (perintah nyata yang sudah diuji).
3. Arsitektur ringkas + tautan ADR.
4. Operasional: environment (nama variabel, tanpa nilai), health check, log/metrik, backup, alert.
5. Rollback: prosedur langkah demi langkah + titik aman terakhir + RTO.
6. Known limitations & technical debt: jujur, dengan dampak dan rencana.
7. Riwayat rilis + status gate.

## Aturan
- Setiap perintah di dokumen wajib **sudah pernah dijalankan** (bukan copy-paste harapan).
- Jangan pernah menempelkan nilai rahasia; hanya nama variabel dan cara mengisinya.
- Sertakan bagian "yang belum diverifikasi" secara eksplisit — lebih baik jujur daripada menyesatkan.
- Handover tanpa rollback + tanpa cara menjalankan test = belum selesai (gate docs FAIL).

## AGENTS.md
Bila repo akan dikerjakan agent: tulis `AGENTS.md` pendek-faktual: perintah build/test, konvensi, larangan,
area berisiko, dan tautan dokumen. Ringkas — ini hemat konteks, bukan tempat curhat arsitektur.

## Output
- `README.md`, `docs/runbooks/*.md`, `CHANGELOG.md`, `AGENTS.md`, `reports/handover-<tanggal>.md`
