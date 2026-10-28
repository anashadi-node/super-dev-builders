# Audit Fundamental Ekosistem SDB — 29 Oktober 2026

Cakupan: `sdb_platform/` (control plane, billing, worker), `dashboard/`, `scripts/`, `skills/**/scripts`,
riwayat git. Basis: `v0.5.0` (`61d12af`). Hasil: `v0.6.0`.

## 1. Ringkasan

| Ukuran | Sebelum (v0.5.0) | Sesudah (v0.6.0) |
|---|---|---|
| Hipotesis cacat control plane terkonfirmasi | **26 / 27** | **0 / 27** (1 sisa = API internal, lihat §4) |
| Cacat dashboard terkonfirmasi | 3 (D1–D3) | 0 |
| Skrip gagal `--help` | 1 (`md_to_pdf.py`) | 0 |
| Tes | 341 | **384** (`make check` RC=0) |
| Tes regresi baru yang gagal di v0.5.0 | — | **37 / 39** (2 = pagar perilaku yang sudah benar) |
| Secret di riwayat git (gitleaks) | 0 | 0 |
| Temuan semgrep `p/python` + `p/secrets` | 0 | 0 |

Kesimpulan jujur: v0.5.0 **lulus semua tesnya sendiri tetapi punya 8 cacat yang menyangkut uang**, dua
di antaranya kritis (tagihan bisa dihapus tenant; invoice bisa menagih dua kali). Tes lama hanya menguji
jalur yang dirancang, bukan jalur yang bisa disalahgunakan. Semua cacat yang ditemukan sudah diperbaiki
dan dikunci tes. Ini **bukan** jaminan nol bug — §6 mencantumkan yang belum diaudit/dibangun.

## 2. Metode

Falsifikasi dulu, perbaikan kemudian (prinsip Popper, diterapkan ke perangkat lunak):

1. **Baca penuh** kode inti (`store.py`, `billing.py`, `app.py`, `worker.py`) dan permukaan jaringan
   dashboard; susun hipotesis cacat yang spesifik dan bisa salah.
2. **Probe** `/tmp/sdbaudit/repro.py`: tiap hipotesis = skenario nyata pada `Store` / server HTTP sungguhan
   → `CONFIRMED` atau `REFUTED`. Hipotesis yang terbantah **tidak** "diperbaiki" sebagai bug.
3. **Perbaikan minimal** per akar masalah, bukan per gejala (mis. satu transaksi `BEGIN IMMEDIATE` di
   `finish_job` menutup H2, H5, dan balapan penutupan ganda sekaligus).
4. **Tes regresi** per cacat (`tests/test_audit_regressions.py`, `tests/test_dashboard_security.py`).
5. **Uji balik**: tes regresi dijalankan pada worktree `v0.5.0` — harus gagal. 37/39 gagal: tes terbukti
   membedakan kode rusak dan kode sehat.
6. **Bukti lingkungan nyata**: migrasi DB yang dibuat kode v0.5.0, dan smoke E2E HTTP + worker CLI.
7. Pemindai: gitleaks (riwayat penuh, `--redact`), semgrep, ruff (aturan ketat + tersaring), `--help` semua skrip.

## 3. Temuan dan perbaikan

Severity: **KRITIS** = uang/data tenant salah tanpa jejak · **TINGGI** = uang/isolasi salah dalam kondisi
wajar · **SEDANG** = kontrak dilanggar, dampak terbatas · **RENDAH** = ketahanan/kebersihan.

### 3.1 Uang

| ID | Cacat (terbukti di v0.5.0) | Bukti probe | Sev. | Perbaikan |
|---|---|---|---|---|
| H1 | Tenant `POST /finish` menutup job yang sedang dikerjakan worker → hold kembali, worker tak bisa menagih | kredit 24.992.000 → 25.000.000 | **KRITIS** | rute → `410`; penutupan hanya worker pemegang lease atau `/cancel` |
| H2 | `finish_job(status="queued")` diterima → `job_charges` terisi 0, job dikerjakan ulang **gratis** | 5.000 token, kredit tetap | **KRITIS** | status tujuan wajib status penutup |
| H9 | Invoice tumpang-tindih menagih charge yang sama dua kali | inv1 = inv2 = 1.600 | **KRITIS** | tolak tumpang-tindih (`409`), periode wajib sudah tertutup, ts mikrodetik |
| H3 | Batal + worker mati → job macet `queued` selamanya, kredit tertahan | held 8.000 | TINGGI | reaper menutup jadi `cancelled` + release |
| H4 | Batal di detik terakhir → seluruh token gratis | 4.900 token, tagihan 0 | TINGGI | batal setelah kerja ditagih pemakaian (ADR-0007 §3) |
| H5 | Worker lambat menutup job yang sudah diambil worker lain | tertimpa | TINGGI | cek pemilik lease di dalam transaksi |
| H25 | Cek idempotensi/kuota di luar transaksi → `IntegrityError` mentah (500); kuota bisa jebol | errors=[IntegrityError] | TINGGI | cek + INSERT + hold dalam satu `BEGIN IMMEDIATE`; diuji 6 koneksi paralel, kuota 3 → tepat 3 lolos |
| H9b | Periode `'zzz'..'aaa'` jadi invoice | diterima | SEDANG | parse ISO-8601 wajib, start < end |

### 3.2 Integritas dan isolasi

| ID | Cacat | Sev. | Perbaikan |
|---|---|---|---|
| H6 | Job tenant `suspended` tetap diklaim worker (biaya LLM terus terbakar) | TINGGI | klaim hanya tenant `active`; `deleted` → antrean ditutup + kredit dilepas |
| H11 | URI artefak boleh menunjuk ruang tenant lain. **Laten**: belum ada rute unduh/presign, tapi menjadi jalur baca lintas tenant begitu dibangun | TINGGI (laten) | URI wajib `…/<tenant_id>/…`, tolak `..` |
| H16 | Lease 120 s tanpa heartbeat otomatis untuk job s/d 4 jam → klaim ganda | TINGGI | thread heartbeat (interval lease/3, koneksi DB sendiri) |
| H15 | CLI worker default `echo_executor` = menagih pelanggan atas token fiktif | TINGGI | `--executor` wajib; `echo` butuh `SDB_ALLOW_ECHO_EXECUTOR=1` |
| H13 | Memo ledger tidak terlindung hash; baris saldo bisa diubah lalu hash v1 dihitung ulang | SEDANG | hash v2 (JSON kanonik + `entry_id` + memo) + cek kontinuitas saldo per baris; v1 tetap terverifikasi |
| H7 | Kunci idempotensi sama + isi beda diam-diam mengembalikan job lain | SEDANG | `409 idempotency_conflict` |
| H12 | `entry_id` di respons ≠ di DB | SEDANG | id yang sama dipakai |
| H14 | Refund dua statement tanpa transaksi | SEDANG | `BEGIN IMMEDIATE`, memo wajib, `bool` ditolak |
| H8 | `INSERT OR REPLACE` bisa memindahkan API key ke tenant lain. **Laten**: HTTP hanya memakai kunci acak | RENDAH (laten) | `INSERT` biasa → `409 key_exists` |
| H10 | `retention_until` bukan tanggal diterima | RENDAH | ISO-8601 masa depan, dinormalisasi UTC |

### 3.3 HTTP (control plane + dashboard)

| ID | Cacat | Sev. | Perbaikan |
|---|---|---|---|
| H23 / D3 | Tanpa socket timeout → slowloris menahan thread selamanya | SEDANG | `timeout = 30` di kedua server |
| H22 | `lease_seconds` tanpa batas → job tak pernah dipulihkan | SEDANG | 10..3600 |
| H18–H21 | Body array, `pack`/`budget` non-objek, `lease_seconds` non-int, `Content-Length` cacat → 500 | RENDAH | 400 + kode galat; koneksi ditutup bila body tak bisa dibuang aman |
| H26 | Header kunci non-ASCII → 500 (`compare_digest` pada str) | RENDAH | bandingkan bytes → 401 |
| H24 | Error 500 tidak tercatat di mana pun | RENDAH | traceback ke stderr (method + path saja, tanpa header/body) |
| D1 / D2 | Dashboard: body JSON non-objek → 500 yang membocorkan pesan internal Python | RENDAH | 400; 500 hanya menyebut nama kelas galat |
| — | `md_to_pdf.py --help` RC=2; nama berkas tidak di-escape di HTML | RENDAH | RC=0; `html.escape` |

### 3.4 Upgrade (bukan cacat terbukti)

| ID | Temuan | Keputusan |
|---|---|---|
| H17 | Probe kelaparan antrean **REFUTED** di v0.5.0 | Tetap dibangun fair-share (tenant dengan job berjalan paling sedikit didahulukan), karena FIFO murni membuat satu tenant yang mengantre ribuan job menunda semua tenant lain — risiko nyata pada skala ribuan pelanggan. FIFO dalam tenant kini deterministik (`rowid`). |
| — | Header `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` | ditambahkan ke API |
| — | Invoice diterbitkan admin, bukan tenant | mencegah tenant "memesan" periode aneh sehingga invoice bulanan resmi tertolak |

## 4. Verifikasi

| Bukti | Hasil |
|---|---|
| `repro.py` sebelum → sesudah | 26/27 CONFIRMED → semua REFUTED kecuali H1 pada **API Python internal** `Store.finish_job` tanpa `worker_id` (disengaja: dipakai admin/tes; jalur HTTP H1b → `410`) |
| `repro_dash.py` sebelum → sesudah | 3 CONFIRMED → 0 |
| Fair-share | 5/5 run berturut-turut stabil |
| Tes regresi di worktree v0.5.0 | 37 gagal / 2 lulus (`test_h05_penutupan_ganda…`, `budget` berupa list) |
| `make check` | RC=0 · 384 tes · skill drift 116/116 · hygiene 0 FAIL / 4 WARN · pack 8/8 |
| Migrasi DB nyata (dibuat kode v0.5.0) | rantai v1 5 baris `ok`; baris v2 menyambung; 24.990.025 + 8.000 − 3.200 = **24.994.825** ✓ |
| Smoke E2E HTTP + worker CLI | create 201 · replay 200 · `/finish` 410 · worker `succeeded` 1.518 token → **2.429 μUSD** (⌈1.518 × 1,6⌉) · invoice 201 · tumpang-tindih 409 · `verify_chain` ok · `verify_invoice` ok · 0 traceback |
| ruff tersaring (50 temuan) | 0 cacat nyata: 3 `BLE001` di control plane disengaja (handler puncak, isolasi executor, rollback+raise); `gate_check.py` gagal-tertutup (exception → `FAIL`); sisanya skrip alat |
| gitleaks direktori kerja (`--no-git`) | 44 pola, **0 di berkas terlacak**; semuanya positif palsu di berkas yang di-`.gitignore`: sidik jari kunci GPG publik image Python (laporan trivy) dan SHA commit di laporan gitleaks lama (field `Secret` sudah `REDACTED` semua) |

Artefak bukti (di luar repo, `chmod 600`): `~/sdb-archive/audit-20261029/{repro.py, repro_before.txt, repro_after.txt, repro_dash.py,
repro_dash_before.txt, repro_dash_after.txt, check_after.log, check_final.log, gitleaks.json, gl_wt.json, semgrep.json}`.

## 5. Perubahan tidak kompatibel (v0.6.0)

- `POST /v1/jobs/{id}/finish` → `410`. `POST /v1/invoices` → `POST /v1/admin/invoices`.
- Worker CLI wajib `--executor`. URI artefak wajib berprefiks tenant.
- DB v0.5.0 termigrasi otomatis saat dibuka (kolom `ledger.hv`, indeks `idx_jobs_status`,
  `idx_charges_tenant`). Tidak ada baris lama yang ditulis ulang.

## 6. Sisa celah (tidak diklaim selesai)

Celah yang **diketahui dan belum dibangun** — bukan bug tersembunyi, tetapi batas produk saat ini:

1. **Belum ada**: RBAC/SSO, sandbox eksekusi, payment gateway, pajak/proration/dunning, rate limit per
   tenant, metrik Prometheus, antrean terdistribusi (Postgres `SKIP LOCKED`), executor produksi nyata.
2. **TLS**: kedua server HTTP polos; wajib di belakang reverse proxy TLS sebelum dibuka ke internet.
3. **Satu DB = satu host** (SQLite). Fair-share memakai subquery O(antrean) per klaim — memadai satu node.
4. **Dashboard**: PIN 72-bit tanpa rate limit; aman untuk loopback/LAN, **tidak** untuk internet publik.
5. **Pemindaian bergantung aturan**: semgrep/gitleaks 0 temuan ≠ 0 kerentanan.
6. **Hygiene 4 WARN** (berkas besar vendor/bukti, satu email publik di laporan pihak ketiga) — diterima.
7. **Remote origin** masih memegang riwayat lama 38 MB; push paksa menunggu keputusan Owner.

## 7. Langkah berikut yang disarankan

1. Owner memutuskan push paksa `main` + tag ke origin (riwayat bersih) — destruktif, butuh persetujuan.
2. Fase 2c: rate limit per tenant + metrik — dua celah terbesar untuk skala ribuan tenant.
3. Executor produksi pertama (mis. pack `sdb-recon`) di balik sandbox.
