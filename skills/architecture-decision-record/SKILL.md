---
name: architecture-decision-record
description: "Record architecture decisions with context (ADR)"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [architecture, adr, decision, governance]
    divisions: [D3, D11]
    related_skills: [technology-selection, architecture-docs, architecture-compliance-audit]
---


# Architecture Decision Record

Setiap keputusan arsitektur/stack/dependency yang material **wajib** jadi ADR. Tanpa ADR, keputusan tidak sah —
dan developer tidak boleh mengganti framework "karena lebih nyaman".

## Kapan ADR wajib
- Memilih/mengganti framework, bahasa, database, protokol, atau pola arsitektur.
- Menambah dependency berat atau layanan eksternal.
- Memutuskan batas antara mock dan backend privat pada reconstruction.
- Setiap keputusan yang sulit dibalik (biaya/migrasi tinggi).

## Prosedur
1. Copy `templates/adr.md` ke `docs/adr/ADR-<NNN>-<slug>.md` (nomor berurutan, jangan pernah dipakai ulang).
2. Isi Context dengan **fakta + angka**, bukan opini: requirement, batasan, evidence, hasil benchmark.
3. Tulis minimal 2 opsi dengan trade-off jujur (termasuk opsi "tidak melakukan apa-apa").
4. Ambil keputusan maksimum 3 kalimat; tautkan ke Technology Governance (`docs/TECHNOLOGY_GOVERNANCE.md`).
5. Catat konsekuensi + apa yang harus diverifikasi nanti.
6. Bila mengubah keputusan lama: tandai ADR lama `superseded by ADR-XXX`, jangan hapus.

## Aturan
- Dilarang ADR yang hanya restatement keputusan tanpa alternatif dan tanpa risiko.
- Dilarang menandai accepted tanpa pemilik yang jelas.
- ADR ≠ dokumentasi implementasi; detail teknis masuk `architecture-docs`.

## Output
- `docs/adr/ADR-<NNN>-*.md` + entri ringkas di indeks `docs/adr/README.md`
