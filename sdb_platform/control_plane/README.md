# Control Plane (Fase 2) — kontrak yang ditegakkan mesin

Bukan mock. Ini service HTTP nyata dengan SQLite, tanpa dependensi di luar stdlib.

```
python3 -m sdb_platform.control_plane.app --db data/control.db --port 8088
# butuh SDB_ADMIN_KEY (>=24 char) di environment
```

## Kenapa `sdb_platform/` bukan `platform/`

`platform` adalah nama modul standar Python. Paket Python tidak boleh bernama `platform`, jadi kode
produk tinggal di `sdb_platform/`, sedangkan `platform/` tetap menjadi tempat *kontrak* (schema, pack, baseline
higiene). Aturan penempatan ada di `docs/PETA_STRUKTUR.md`, keputusannya di `docs/adr/0004-kode-produk-di-sdb-platform.md`.

## Rute

| Metode | Rute | Auth | Guna |
|---|---|---|---|
| GET | `/healthz` | — | liveness |
| POST | `/v1/tenants` | `X-Admin-Key` | buat tenant; mengembalikan `api_key` **sekali** |
| POST | `/v1/jobs` | `X-API-Key` | buat job (idempoten lewat `idempotency_key`) |
| GET | `/v1/jobs/{id}` | `X-API-Key` | status job milik tenant itu |
| POST | `/v1/jobs/{id}/finish` | `X-API-Key` | tutup job + catat token terpakai |
| GET/POST | `/v1/jobs/{id}/artifacts` | `X-API-Key` | daftar/baca artefak |
| GET | `/v1/usage` | `X-API-Key` | pemakaian vs kuota bulan ini |

Semua respons JSON. Galat selalu `{"error": {"code", "message"}}` dengan kode HTTP yang benar
(401/402/403/404/409/413/422/500) — tidak pernah 200 untuk kegagalan.

## Batas yang ditegakkan (bukan saran)

| Aturan | Konsekuensi |
|---|---|
| Tenant hanya melihat barisnya sendiri | `GET /v1/jobs/{id}` milik tenant lain → **404**, bukan 403 (keberadaan tidak bocor) |
| Kuota job bulanan | job ke-(limit+1) → **402 quota_jobs_exceeded** |
| Kuota token | budget job + token terpakai dihitung terhadap plafon; kurang → **402 quota_tokens_exceeded** |
| `idempotency_key` unik per tenant | kirim ulang → job yang sama, `replayed: true`, kuota tidak bertambah |
| Budget wajib eksplisit | `tokens` 1.000–2.000.000, `seconds` 60–14.400 |
| Token aktual > budget | status akhir jadi **budget_exceeded**, bukan `succeeded` |
| Artefak wajib status redaksi | tanpa status → 400; `blocked` → 422 |
| URI artefak wajib object store | `s3://` atau `artifact://`; path lokal ditolak |
| Kuota penyimpanan | total byte artefak > plafon → **402 quota_storage_exceeded** |

## Yang sengaja BELUM ada (jangan diklaim ada)

- autentikasi manusia/OAuth, RBAC per peran, SSO — sekarang hanya API key per tenant;
- billing/pembayaran (kuota sudah ditegakkan, penagihan belum);
- antrean worker dan eksekusi job — job dicatat, tidak dijalankan service ini;
- Postgres, replikasi, rate limit per IP, audit log kriptografis;
- isolasi eksekusi (sandbox kontainer) — baru *model* `pool|bridge|silo`.

Urutan berikutnya ada di `docs/ARSITEKTUR_SAAS.md` (Fase 2 lanjutan → Fase 3).
