---
name: observed-network-contract
description: "Use to record and redact network/API behavior truly observed on a target."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [reconstruction, network, api, redaction, trace]
    divisions: [D1]
    related_skills: [technology-profiler, evidence-normalizer]
---


# Observed Network Contract

Membangun peta endpoint/method/schema dari **request yang benar-benar terjadi** selama interaksi yang diizinkan.

## Prosedur
1. Aktifkan Playwright trace / DevTools record; jalankan journey yang diizinkan (bukan fuzzing).
2. Untuk setiap request yang teramati, catat: id, method, path (parameter dinamis dinormalisasi: `/users/{id}`),
   status, content-type, request/response schema **hasil inferensi struktur**, bukan salinan payload sensitif.
3. Jalankan `python3 scripts/redact_network.py <file>` untuk memastikan header Authorization, Cookie,
   API key, email/telepon, nomor kartu, dan token dihapus sebelum file disimpan/diserahkan.
4. Tandai endpoint yang tidak dipanggil selama journey sebagai **UNKNOWN** (jangan mengarang).

## Larangan keras
- Tidak ada brute-force/enumerasi endpoint.
- Tidak ada TLS interception pada layanan pihak ketiga; proxy hanya Mode B pada environment yang diotorisasi.
- Tidak menyimpan payload yang memuat PII; simpan bentuk skema, bukan data.

## Output
- `normalized/<target>/network.json` + ringkasan: endpoint teramati, auth required (redacted), pola error,
  pagination, idempotency key bila terlihat.
- Setiap record: `status` FACT/INFERRED, `confidence`, `provenance`.

## Judgement
- Kontrak ini adalah **observed contract**, bukan dokumentasi resmi. Implementasi internal target tidak perlu identik:
  yang wajib cocok adalah perilaku yang teramati dan diuji.
