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
| POST | `/v1/jobs/{id}/cancel` | `X-API-Key` | batal; antrean → langsung ditutup, berjalan → ditandai |
| GET | `/v1/billing` | `X-API-Key` | saldo kredit, kredit tertahan, daftar invoice |
| GET | `/v1/ledger` | `X-API-Key` | 100 entri ledger terakhir (ber-rantai hash) |
| GET/POST | `/v1/invoices` | `X-API-Key` | daftar / terbitkan tagihan periode |
| POST | `/v1/worker/claim` | `X-Worker-Key` | worker mengambil satu job (atomik) |
| POST | `/v1/jobs/{id}/heartbeat` | `X-Worker-Key` | perpanjang lease |
| POST | `/v1/jobs/{id}/complete` | `X-Worker-Key` | tutup job + tagih pemakaian |
| POST | `/v1/credits/topup` | `X-Admin-Key` | tambah kredit tenant (μUSD) |
| GET | `/v1/admin/revenue` | `X-Admin-Key` | total tagihan & jumlah job |

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
| Kredit prabayar | harga budget job di-hold saat dibuat; kredit kurang → **402 insufficient_credit** |
| Penagihan | hanya `succeeded`/`budget_exceeded` yang ditagih; gagal/batal → hold dilepas |
| Tagih ganda | `job_charges` unik per job; settle ulang tidak menambah biaya |
| Ledger | append-only ber-rantai hash; `verify_chain()` mendeteksi suntingan |

## Yang sengaja BELUM ada (jangan diklaim ada)

- autentikasi manusia/OAuth, RBAC per peran, SSO — sekarang hanya API key per tenant;
- billing/pembayaran (kuota sudah ditegakkan, penagihan belum);
- eksekusi job di dalam service ini — worker adalah proses terpisah (`sdb_platform/runtime/`);
- gateway pembayaran, pajak, proration upgrade, dunning;
- Postgres, replikasi, rate limit per IP, audit log kriptografis;
- isolasi eksekusi (sandbox kontainer) — baru *model* `pool|bridge|silo`.

Urutan berikutnya ada di `docs/ARSITEKTUR_SAAS.md` (Fase 2 lanjutan → Fase 3).
