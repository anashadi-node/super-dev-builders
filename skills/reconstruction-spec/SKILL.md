---
name: reconstruction-spec
description: "Turn evidence into feature matrix and spec"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux, macos]
metadata:
  hermes:
    tags: [reconstruction, spec, prd, feature-matrix]
    divisions: [D1, D3]
    related_skills: [target-inventory, architecture-decision-record, reconstruction-fidelity]
---


# Reconstruction Spec

Mengubah evidence menjadi spesifikasi yang cukup untuk membangun ulang tanpa menebak.

## Isi wajib (template: `templates/reconstruction_spec.md`)
1. Feature Matrix: setiap area berstatus `observed | reproduced | intentionally_changed | unknown`,
   dengan pointer evidence (`screen:`, `action:`, `network:`).
2. UX & navigation spec dari `actions.json` + `screens.json`.
3. Observable API contract dari `network.json`.
4. Design token teramati; yang tidak teramati = UNKNOWN.
5. Batas rebuild: mana yang direkonstruksi, mana yang dirancang baru, mana yang sengaja diubah (+alasan).
6. Rencana verifikasi per dimensi.

## Aturan
- UNKNOWN tidak boleh diisi tebakan; architect merancang implementasi baru yang memenuhi requirement
  dan mencatatnya sebagai keputusan (ADR bila material).
- Fidelity yang dijanjikan hanya pada apa yang punya evidence.
- Bila ada konflik antar-evidence: catat, pilih yang paling dapat diverifikasi, tandai yang lain.

## Output
- `reconstruction/<target>/SPEC.md` + `FEATURE_MATRIX.md`
- Daftar pertanyaan terbuka untuk Owner (mis. backend privat, data contoh).
