---
name: architecture-docs
description: "Document architecture: C4 views and data flow"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [documentation, architecture, c4, data-flow, diagram]
    divisions: [D11, D3]
    related_skills: [architecture-decision-record, release-handover-docs]
---


# Architecture Docs

Dokumentasi arsitektur yang **dipakai** (bukan museum): ringkas, akurat, dapat diverifikasi, dan diperbarui saat berubah.

## Isi minimum
1. **Context** (C4 level 1): sistem ini, siapa pengguna, sistem eksternal apa yang disentuh.
2. **Container** (level 2): aplikasi, service, database, queue, storage + teknologi + alasan singkat (tautkan ADR).
3. **Component** (level 3) hanya untuk area kompleks/berisiko (auth, pembayaran, sinkronisasi data).
4. **Data flow**: alur utama data masuk-keluar, tempat transformasi, tempat data disimpan, batas kepercayaan.
5. **Deployment topology**: environment, jaringan, penyimpanan, konfigurasi penting (nama variabel saja).
6. **Cross-cutting**: observability, backup/restore, keamanan, rate limit, batas kapasitas.
7. **Indeks ADR** + status.

## Aturan
- Diagram: teks/ASCII atau Mermaid di dalam repo; harus bisa di-diff (hindari gambar biner saja).
- Setiap komponen harus punya pemilik dan satu alasan keberadaan; komponen tanpa alasan = kandidat hapus.
- Dokumentasi usang adalah cacat: bila kode berubah, perbarui dalam commit yang sama.
- Tanpa rahasia: hanya nama variabel, jangan nilainya.

## Output
- `docs/architecture/ARCHITECTURE.md` (+ `containers.md`, `data-flow.md`, `deployment.md` bila perlu)
- `docs/adr/README.md` sebagai indeks keputusan.
