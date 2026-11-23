# BE-SP-03 — Kontrak API Control Plane v1

Status: **PILOT_VERIFIED_SUBSCOPE (kandidat)** · Mode: BROWNFIELD_RECOVERY → CHANGE_ONLY
Baseline: `abc0cc3fb5a52fb2eed44e238e2425f19a6ce980` (C1-01 BE-SP-12)

Dokumen ini ringkasan manusia. Sumber kebenaran yang dapat diuji adalah kontrak
mesin `fixtures/contracts/control_plane_v1.json` yang dibuktikan oleh
`tests/test_be_sp03_contract.py` (T1–T10). Kalau dokumen ini dan kontrak mesin
berbeda, kontrak mesin + hasil tes yang menang.

## Cakupan (2 keluarga endpoint, sesuai izin Owner)

| Endpoint | Auth | Sukses | Error inti |
|---|---|---|---|
| `POST /v1/jobs` | `X-API-Key` tenant | `201 {job, replayed:false}`; replay idempotent `200 {job, replayed:true}` | 400 `invalid_json`/`invalid_type`/`invalid_pack`/`invalid_target`/`invalid_budget`/`invalid_idempotency_key`/`invalid_content_length`; 401 `unauthorized`; 402 `quota_jobs_exceeded`/`quota_tokens_exceeded`; 403 `tenant_inactive`; 409 `idempotency_conflict`; 413 `body_too_large`; 429 `rate_limited` (+`Retry-After`) |
| `GET /v1/jobs/:id` | `X-API-Key` tenant | `200 {job}` | 401 `unauthorized`; 404 `job_not_found` |

Endpoint dicabut: `POST /v1/jobs/:id/finish` → `410 endpoint_removed` (tanpa auth check).

## Sifat kunci yang dibuktikan tes

1. **Error envelope tunggal**: `{error: {code, message}}` + header `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `Content-Type: application/json`.
2. **Isolasi tenant**: job tenant lain → `404 job_not_found` (bukan 403) supaya keberadaan job tidak bocor; idempotency unik per `(tenant_id, idempotency_key)`.
3. **Field wajib** (5): `type` (enum 7 nilai), `pack` (`id` regex + `version` semver), `target_ref` (`^(artifact|git|upload)://\S+$`, ≤2048), `budget` (`tokens` 1000..2.000.000, `seconds` 60..14400), `idempotency_key` (8..128).
4. **job_object** 15 field dengan tipe tetap (`job_id`, `tenant_id`, `type`, `pack`, `target_ref`, `budget`, `idempotency_key`, `status`, `tokens_used`, `gate_verdict`, `created_at`, `finished_at`, `attempts`, `lease_owner`, `cancel_requested`).
5. **Komitmen kompatibilitas**: menghapus field wajib / mengubah status sukses / mengubah envelope / mengubah masking 404 lintas-tenant / menghapus field job_object = breaking → contract test gagal. Penambahan field response atau error code baru diizinkan.

## Cara menjalankan

```bash
.venv/bin/python -m pytest tests/test_be_sp03_contract.py -q -o addopts=""
```

Semua request lewat server loopback (`Store :memory:`, port 0). Tidak ada
koneksi keluar, tidak ada data produksi, tidak ada perubahan file produksi
(`app.py`/`store.py` READ-ONLY). Mutasi T9 berjalan pada salinan scratch di
`tmp_path` pytest dan hanya membunuh mutan bila contract test bekerja.
