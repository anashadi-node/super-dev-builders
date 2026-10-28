---
name: api-contract
description: "Design and review HTTP API contracts and schemas"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux, macos]
metadata:
  hermes:
    tags: [api, contract, openapi, schema, backend, versioning]
    divisions: [D5, D3, D7]
    related_skills: [test-pyramid-and-risk, authz-authn-review]
---


# API Contract

Kontrak API ditulis **sebelum** implementasi (schema-first), supaya frontend/backend/tester punya satu kebenaran.

## Isi kontrak minimum
1. Path + method + ringkasan tujuan.
2. Request: parameter path/query, body schema (tipe, wajib/opsional, validasi, batas panjang/nilai).
3. Response sukses: schema + contoh + status code.
4. Response error: bentuk konsisten (`code`, `message`, `details`), status code per kelas kesalahan,
   tanpa membocorkan detail internal/stack trace.
5. Idempotency: endpoint yang aman diulang (POST dengan `Idempotency-Key`), perilaku retry.
6. Pagination: cursor vs offset, batas maksimum, urutan stabil.
7. Versioning & kompatibilitas: strategi (path/header), aturan breaking change.
8. Auth: skema (bearer/session/API key), scope minimum, perilaku 401 vs 403.

## Prosedur
1. Tulis kontrak (OpenAPI bila HTTP) di `reconstruction/<target>/api/` atau `docs/api/`.
2. Turunkan test kontrak (schema validation) — bukan hanya happy path.
3. Review oleh D6/D7: cek error contract, validasi, idempotency, pagination, kebocoran data.
4. Implementasi baru boleh mulai setelah kontrak disetujui (untuk pekerjaan bersama frontend/backend).

## Aturan
- Validasi input di trust boundary: wajib, jangan disederhanakan (ini pengecualian aturan "kode minimum").
- Tidak ada field respons yang mengekspos internal ID mentah, hash password, token, atau PII berlebih.
- Pada reconstruction: cocokkan **perilaku teramati**, bukan implementasi internal target.
