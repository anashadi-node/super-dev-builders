---
name: evidence-normalizer
description: "Use to normalize raw capture into validated JSON evidence with status and confidence."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [reconstruction, evidence, normalization, provenance, lint]
    divisions: [D1]
    related_skills: [observed-network-contract, reconstruction-spec]
---


# Evidence Normalizer

Mengubah artefak mentah (screenshot, DOM, trace, catatan) menjadi evidence ternormalisasi yang bisa dibangun
dan diverifikasi, dengan provenance lengkap.

## Skema
Lihat `docs/EVIDENCE_SCHEMA.md`. Metadata wajib setiap record:
`provenance`, `captured_at`, `redaction_status`, `status` (FACT|INFERRED|UNKNOWN|OUT_OF_SCOPE),
`confidence` (wajib numerik bila INFERRED).

## Prosedur
1. Kumpulkan artefak mentah ke `evidence/<target>/` (raw, tidak dishare ke LLM sebelum redaksi).
2. Kelompokkan menjadi: `inventory.json`, `screens.json`, `components.json`, `actions.json`,
   `network.json`, `assets.json`, `technology.json`.
3. Jalankan `python3 scripts/evidence_lint.py normalized/<target>`.
4. Perbaiki semua error lint (record tanpa provenance, INFERRED tanpa confidence, dugaan pada UNKNOWN,
   pola kredensial tersisa).
5. Baru serahkan ke D3 (architect) / D4-D5 (builder).

## Aturan
- Capture mobile/desktop (Appium, MobSF, Windows UIA) + aturan redaksi header/query: lihat
  `references/multi-platform-capture.md`.
- Aset: hash konten (sha256) + label lisensi (`authorized|open|substituted`); aset tanpa lisensi jelas
  tidak boleh dibawa ke reconstruction.
- Deduplikasi berdasarkan hash, bukan nama file.
- Tidak ada inferensi yang dinaikkan status menjadi FACT tanpa bukti langsung.

## Output
- `normalized/<target>/*.json` (lint PASS) + `reports/<target>/evidence-summary.md`.
