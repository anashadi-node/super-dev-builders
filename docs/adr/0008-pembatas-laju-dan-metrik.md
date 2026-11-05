# ADR-0008 — Pembatas laju per tenant dan metrik operasional

Status: diterima · 2026-10-29 · rilis v0.7.0

## Konteks

Audit fundamental (ADR-0007, §6 laporan) menyisakan dua celah yang paling menghalangi skala ribuan
tenant: **(1)** tidak ada pembatasan permintaan per tenant, sehingga satu klien yang salah looping
bisa memonopoli lock global control plane dan memperlambat semua pelanggan lain; **(2)** tidak ada
metrik, sehingga operator tidak bisa menjawab "berapa penolakan kuota hari ini" tanpa membaca log.
Pin dashboard juga belum membatasi percobaan tebak.

## Keputusan

1. **Token bucket per tenant, di memori proses.** `RateLimiter` di `sdb_platform/control_plane/metrics.py`.
   Kapasitas burst = 2× laju per detik (minimal 5 token), isi ulang kontinu, jam `monotonic`.
   Jatah default 600 permintaan/menit (`SDB_RATE_PER_MIN`), dapat ditimpa per tenant lewat kolom baru
   `tenants.rate_per_min` (`limits.rate_per_min` saat membuat tenant, 1..100000).
2. **Hanya jalur tenant yang dibatasi.** Admin dan worker punya kunci sendiri; menahan worker justru
   menunda penyelesaian job (dan penagihan). Penolakan → `429 rate_limited` + header `Retry-After`.
3. **`GET /metrics` admin-only, format teks Prometheus**, tanpa pustaka klien: penghitung
   `sdb_http_requests_total{method,route,status}`, `sdb_jobs_created_total{type}`,
   `sdb_jobs_completed_total{status}`, `sdb_tokens_used_total`, `sdb_rate_limited_total`,
   `sdb_uptime_seconds`. `route` dinormalisasi ke templat (`/v1/jobs/:id`) agar kardinalitas label
   tidak tumbuh per job.
4. **Pin dashboard**: kegagalan autentikasi dihitung per IP dalam jendela 60 detik; lebih dari 30 →
   `429`. Kunci benar tidak pernah terpengaruh.

## Alternatif yang ditolak

- **Batas di reverse proxy (nginx/Envoy).** Lebih tahan restart dan multi-node, tetapi butuh konfigurasi
  di luar aplikasi; jatah per tenant jadi tidak bisa diatur lewat API. Dicatat sebagai langkah produksi
  wajib untuk produksi (belum ada dokumen khusus; lihat `docs/runbooks/RELEASE.md`) — keduanya bisa hidup bersama.
- **Redis / sliding window bersama.** Benar untuk banyak instance, tetapi menambah dependensi baru
  untuk sistem yang masih SQLite satu node (prinsip: dependency yang sudah ada dulu).
- **Timezone/`time.time()` untuk isi ulang.** Jam dinding bisa mundur → jatah gratis; `monotonic` benar.

## Konsekuensi

- Penghitung **hilang saat restart** dan **tidak dijumlahkan antar instance**. Jujur untuk satu node;
  saat pindah Postgres/multi-instance, metrik dan ember harus pindah ke penyimpanan bersama.
- Memori ember dibatasi `MAX_TRACKED_KEYS` (20.000) dengan GC entri diam > 10 menit.
- Satu perintah tambahan per permintaan tenant (`SELECT` tenant untuk jatah khusus) — di dalam lock
  yang sudah ada, terukur < 0,1 ms pada DB lokal.
- `429` adalah kontrak baru bagi klien: SDK/klien wajib menghormati `Retry-After` dan mengulang.

## Verifikasi

`tests/test_metrics_ratelimit.py` (11 tes): penolakan + `Retry-After`, isolasi antar tenant, isi ulang
seiring waktu, admin/worker tidak tertahan, `/metrics` menolak non-admin, isi metrik setelah job
dibuat/diklaim/diselesaikan, kardinalitas rute, dan keselamatan paralel penghitung.
