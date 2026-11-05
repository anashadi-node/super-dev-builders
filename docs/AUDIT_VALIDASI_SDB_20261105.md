# Laporan Audit, Validasi, dan Remediasi SDB — 5 November 2026

**Versi laporan:** 1.0 · **Tanggal pengukuran:** 5 November 2026, 12:30–13:05 WIB
**Objek:** repo `~/super-dev-builders` (HEAD `main`, working tree berisi patch audit)
**Repo resmi:** <https://github.com/anashadi-node/super-dev-builders> (publik, pemilik `anashadi-node`)
**Hubungan dengan dokumen lain:** ini laporan **tindak lanjut** atas “Audit Ganda SDB — Arsitektur, Kualitas Produk & Skalabilitas”. Dokumen A–Z (`docs/SDB_LENGKAP_A_Z_20261105.md`) tetap menjadi gambaran sistem; laporan ini yang mencatat **apa yang diukur, apa yang terbukti, apa yang diperbaiki, dan apa yang belum**.

> **Aturan bukti dalam laporan ini.** Setiap angka punya perintah untuk memverifikasi ulang (§11). Angka **“sebelum”** adalah pengukuran yang dilakukan saat audit berjalan, sebelum patch diterapkan — angka itu **tidak bisa direproduksi** tanpa mengembalikan kode ke commit sebelumnya, dan karena itu selalu diberi label “sebelum”. Angka **“sesudah”** bisa direproduksi kapan saja dengan perintah di §11. Klaim yang tidak bisa saya buktikan ditulis sebagai **tidak dapat diverifikasi**, bukan dihilangkan.

---

## 0. Cara membaca (2 menit)

1. §1 = tabel 18 temuan + statusnya. Cukup baca ini kalau ingin tahu hasilnya saja.
2. §2 = metode. Baca kalau ingin menilai apakah caranya sah.
3. §4–§8 = satu sub-bab per temuan: **klaim → cara verifikasi → akar masalah → perbaikan → bukti sesudah → sisa risiko**.
4. §9 = uji mutasi (cara paling jujur menilai apakah tes benar-benar menjaga sesuatu).
5. §10–§11 = angka akhir + perintah reproduksi.
6. Lampiran B = kamus istilah dalam bahasa awam (indeks, WAL, Nagle, mutan, *coverage*).

---

## 1. Ringkasan eksekutif

**18 temuan** diverifikasi: **15 diperbaiki** di commit audit ini, **3 tidak dikerjakan** karena butuh keputusan/kredensial dari Anda (bukan karena teknis sulit).

| # | Temuan | Bukti sebelum (terukur) | Tindakan | Status |
|---|---|---|---|---|
| T-01 | Klaim job memindai seluruh antrean | `claim_next_job` **92,28 ms** pada 50.000 job | indeks parsial `idx_jobs_claim` + klaim dua langkah | ✅ 0,06 ms |
| T-02 | Setiap commit menunggu fsync | commit **8,3 ms**, `journal_mode=delete` | WAL + `synchronous=NORMAL` + `busy_timeout` | ✅ ~0,2 ms |
| T-03 | Keep-alive health check tertahan 40 ms | `/healthz` **40,28 ms** | `disable_nagle_algorithm=True` | ✅ 0,20–0,23 ms |
| T-04 | Backlog listen default 5 | 16 koneksi paralel → **296 req/s** | `request_queue_size=128` | ✅ 4.538 req/s |
| T-05 | Health check ikut menunggu `api.lock` | healthz tertahan selama klaim/ tulis | jalur `/healthz` dilayani tanpa lock | ✅ (uji regresi) |
| T-06 | Dua sumber kebenaran daftar tahap (16 vs 18) | `workflow_run.py` 16 tahap, dokumen 18 | `workflows/stages.yaml` + `scripts/stage_registry.py` | ✅ satu sumber |
| T-07 | `docs_lint` hanya cek indeks, tidak cek rujukan path | **19 rujukan mati** tak terdeteksi | pemeriksaan rujukan path | ✅ 264 diperiksa, 0 mati |
| T-08 | Higiene repo tidak mengenali path absolut `$HOME/...` | 9 berkas sampah lolos | aturan R6/R7 + pembersihan | ✅ 0 FAIL |
| T-09 | Tidak ada uji mutasi | — | `tools/mutation_gate.py` (10 mutan) | ✅ 50% → **100%** |
| T-10 | *Coverage* tidak diukur, tanpa ambang | tidak diketahui | `coverage --branch` + ambang 85% di CI | ✅ **88%** cabang |
| T-11 | Uji `integrations/` tidak ikut `make test` | 57 uji hanya jalan bila diingat | `make test` = `tests skills integrations` | ✅ |
| T-12 | `docs-lint` tidak dipanggil di CI | aturan dokumen tak pernah bisa gagal di CI | langkah CI baru | ✅ |
| T-13 | 5 mutan sintas (gerbang tanpa uji penjaga) | kill rate **50%** | 5 uji penjaga baru | ✅ 100% |
| T-14 | Sembilan berkas sampah ber-path `$HOME/...` ter-stage | `git status` 9 entri `D` aneh | dihapus dari indeks & disk | ✅ |
| T-15 | Symlink absolut bisa menyusup ke repo | tidak diperiksa | aturan R7 | ✅ WARN/FAIL |
| T-16 | `sdb-control-plane` gagal start terus-menerus | exit 2, **744 restart** | **butuh `SDB_ADMIN_KEY`** = kredensial baru | ⛔ **butuh izin Anda** |
| T-17 | Platform SaaS: 0 tenant, 0 job, 0 rupiah | DB `control.db` kosong | tidak ada kode yang bisa “memperbaiki” ini | ⛔ keputusan bisnis |
| T-18 | Berkas besar & 1 pola PII lolos higiene | three.module 655 KB, trivy 1477 KB, `hello@davidmiller[.]io` | dicatat, bukan dihapus (utang lama) | ⚠️ WARN |

**Angka kunci sesudah remediasi (semua terverifikasi hari ini):**

| Metrik | Nilai | Perintah |
|---|---|---|
| Suite uji | **629 lulus** (+3 subtes), 50 berkas, 49,83 s — 533 di antaranya di `tests/` | `make test` |
| *Coverage* cabang `sdb_platform` | **88%** (984 stmt, 99 miss, 268 cabang, 33 parsial) | §11 |
| Uji mutasi | **10/10 mutan terbunuh (100%)** | `make mutation` |
| `make check` | **PASS** (lint, registry, test, drift, higiene, packs, docs-lint) | `make check` |
| Rujukan dokumen | **264 path diperiksa, 0 mati** (dari 5.122 token backtick) | `make docs-lint` |
| Higiene repo | 475 berkas, **0 FAIL**, 4 WARN | `make hygiene` |
| Pack divisi | **8/8 PASS**, drift skill 119/119 | `make packs` |

---

## 2. Metode

Sembilan teknik dipakai; tiap temuan memakai minimal dua yang saling mengecek.

| Teknik | Dipakai untuk | Kenapa dipilih |
|---|---|---|
| 1. Baca kode + peta panggilan | memahami alur sebelum menyalahkan | analisis statis murah, tidak menyentuh sistem |
| 2. `EXPLAIN QUERY PLAN` | membuktikan klaim tidak memakai indeks | rencana SQLite = bukti, bukan dugaan |
| 3. Pengukuran berulang (median 15 sampel) | kinerja klaim, commit, HTTP | median tahan outlier mesin |
| 4. Beban konkuren (16 & 32 thread) | throughput nyata | satu permintaan tidak mewakili server |
| 5. Injeksi kondisi (lock ditahan) | health check saat sibuk | menguji jalur yang justru penting saat sibuk |
| 6. *Branch coverage* | bagian kode yang tak pernah dijalankan | baris tertutup ≠ cabang tertutup |
| 7. Uji mutasi | apakah tes benar-benar menjaga | tes bisa hijau meski logika dirusak |
| 8. Penelusuran rujukan silang dokumen | dokumen vs kode | mencegah dua sumber kebenaran |
| 9. Penelusuran artefak (mtime, ukuran, pola) | kebersihan repo | menangkap sampah yang tak terlihat di `git status` biasa |

**Definisi status yang dipakai konsisten:**

- **Terbukti** — ada keluaran perintah yang bisa diulang orang lain.
- **Terbantah** — klaim audit tidak cocok dengan kode/ukur; saya tulis apa yang sebenarnya.
- **Tidak dapat diverifikasi** — butuh akses/kredensial/data yang tidak ada.
- **Diperbaiki** — ada perubahan kode + uji penjaga yang gagal bila perbaikan dibatalkan (dibuktikan lewat mutasi).
- **Ditahan** — butuh keputusan Anda (kredensial, uang, target bisnis).

---

## 3. Batas kejujuran laporan ini

Hal-hal berikut **tidak** diklaim:

1. **Bukan jaminan bebas bug.** 88% cabang berarti 12% cabang belum pernah dijalankan uji — daftarnya bisa dilihat dengan `coverage report -m`.
2. **Angka kinerja bukan SLA.** Diukur di PC ini (lihat §11); mesin lain akan berbeda. Uji regresi karena itu menjaga **mekanisme** (indeks dipakai, WAL aktif, Nagle mati, backlog ≥128), bukan angka detik.
3. **T-17 (0 tenant) bukan cacat kode.** Tidak ada patch yang bisa membuat orang membeli. Itu keputusan produk.
4. **T-16 belum diperbaiki.** Menyalakan layanan berarti membuat kredensial `SDB_ADMIN_KEY` — sesuai aturan yang Anda tetapkan, itu menunggu izin eksplisit (§8.1).
5. **Tiga WARN higiene dibiarkan.** Berkas 655 KB dan 1477 KB adalah artifak bukti pihak ketiga yang sudah terlacak sejak lama; menghapusnya akan memutus jejak bukti. Dicatat sebagai utang, bukan diperbaiki diam-diam.

---

## 4. Temuan A — Kinerja & ketahanan control plane

### T-01 · Klaim job memindai seluruh antrean

**Klaim audit:** `claim_next_job` tidak berskala; bertambah lambat seiring panjang antrean.

**Verifikasi.** Saya isi tabel `jobs` dengan 50.000 baris lalu memanggil `claim_next_job` 15 kali dan mengambil median. Hasil: **92,28 ms**. `EXPLAIN QUERY PLAN` menunjukkan `SCAN jobs` + `USE TEMP B-TREE FOR ORDER BY` — seluruh tabel dibaca dan diurutkan untuk mengambil **satu** baris.

**Akar masalah (bukan gejala).** Kueri lama menyaring `status='queued' AND cancel_requested=0 ORDER BY created_at LIMIT 1` **tanpa indeks yang cocok**. Biayanya O(n log n) per klaim; pada 50.000 job itu 92 ms, dan karena klaim terjadi di dalam `BEGIN IMMEDIATE`, seluruh penulis lain ikut menunggu.

**Perbaikan.**

- Indeks parsial `idx_jobs_claim ON jobs(tenant_id, created_at) WHERE status='queued' AND cancel_requested=0` — hanya berisi job yang benar-benar bisa diklaim, jadi tetap kecil walau riwayat tumbuh.
- `idx_jobs_running` untuk hitungan job berjalan per tenant.
- Klaim dua langkah: pilih tenant yang paling adil (hitungan kecil, terindeks) → ambil job tertua tenant itu lewat `idx_jobs_claim`. Adil antar-tenant dan tidak lagi memindai.

**Bukti sesudah.** `claim_next_job` = **0,06 ms** pada 50.000 job; rencana kueri menyebut `idx_jobs_claim`. Uji `test_klaim_memakai_indeks_antrean` gagal bila indeks dihapus; `test_klaim_tidak_melonjak_dengan_panjang_antrean` gagal bila klaim kembali tumbuh 5× saat antrean 10× lebih panjang.

**Sisa risiko.** Indeks parsial perlu di-`ANALYZE` bila distribusi tenant sangat miring; belum ada job pemeliharaan untuk itu.

---

### T-02 · Setiap commit menunggu fsync

**Verifikasi.** `PRAGMA journal_mode` = `delete`; satu commit diukur **8,3 ms** (mayoritas waktu tunggu fsync).

**Akar masalah.** Mode jurnal `delete` menulis rollback journal dan fsync beberapa kali per transaksi. Untuk basis data antrean job — yang boleh diulang klien karena ada `idempotency_key` — biaya itu dibayar tanpa manfaat.

**Perbaikan.** `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=15000`.

**Bukti sesudah.** commit **~0,2 ms**. Uji `test_wal_aktif_untuk_db_berkas` gagal bila WAL dimatikan.

**Trade-off yang saya tulis di kode, bukan sembunyikan.** Pada mati listrik/OS-crash, transaksi terakhir yang belum ter-checkpoint **bisa hilang**. Untuk job antrean aman (klien mengulang dengan kunci idempoten). **Untuk buku besar uang, `NORMAL` tidak boleh dipakai tanpa pemeriksaan ulang** — catatan ini ada di komentar `store.py` baris 107–111 supaya tidak hilang saat refactor.

---

### T-03 · Keep-alive health check tertahan 40 ms

**Verifikasi.** Permintaan `/healthz` berurutan pada koneksi keep-alive: **40,28 ms** per permintaan. Angka 40 ms itu khas interaksi **Nagle + delayed ACK**: respons kecil ditahan menunggu ACK.

**Perbaikan.** `disable_nagle_algorithm = True` pada handler (`TCP_NODELAY`).

**Bukti sesudah.** **0,20–0,23 ms** rata-rata, p95 **0,39 ms**. Uji `test_server_menyalakan_nodelay_dan_backlog` gagal bila dimatikan.

**Kenapa ini penting secara operasional.** Probe yang lambat membuat orkestrator mengira layanan sehat-padat-padat saja padahal sedang sibuk; 40 ms bukan bencana, tapi ia mengukur hal yang salah.

---

### T-04 · Backlog listen default 5

**Verifikasi.** 16 koneksi paralel → **296 req/s**; sebagian koneksi ditolak/ditunda karena antrean `listen()` hanya 5.

**Perbaikan.** `request_queue_size = 128`, `daemon_threads = True`.

**Bukti sesudah.** **4.538 req/s** pada 16 koneksi paralel; 32 thread → 4.390 req/s (jenuh, wajar untuk GIL + SQLite). Uji regresi menuntut `request_queue_size >= 128`.

**Sisa risiko.** 4.500 req/s adalah batas satu proses Python. Skala berikutnya butuh proses terpisah per inti atau *connection pool* di depan — **belum** dikerjakan dan bukan kebutuhan hari ini.

---

### T-05 · Health check ikut menunggu lock tulis

**Verifikasi.** Saya tahan `api.lock` lalu memanggil `/healthz`: permintaan **menggantung** sampai lock dilepas. Artinya saat satu klaim job lambat (92 ms), probe ikut lambat — persis saat probe paling dibutuhkan.

**Akar masalah.** Handler membungkus **semua** rute dengan `with api.lock`, padahal `/healthz` tidak menyentuh DB sama sekali.

**Perbaikan.** `/healthz` dilayani **sebelum** masuk lock (payload konstan, tanpa DB).

**Bukti sesudah.** Uji `test_healthz_tetap_menjawab_saat_lock_ditahan` menahan lock lalu menuntut `/healthz` menjawab 200 dalam <2 s.

---

## 5. Temuan B — Sumber kebenaran ganda

### T-06 · Daftar tahap: 16 di kode, 18 di dokumen

**Verifikasi.** `scripts/workflow_run.py` mendefinisikan 16 tahap di dalam kode; dokumen menyebut 18. Dua angka benar untuk dua tempat berbeda — itu **dua sumber kebenaran**, dan salah satunya pasti akan basi.

**Perbaikan.** `workflows/stages.yaml` menjadi satu-satunya daftar (18 tahap: kode, urutan, artefak wajib, pemilik kata-kata). `scripts/stage_registry.py` memuat YAML itu; `workflow_run.py` dan `dashboard/ws_api.py` **membaca** dari sana, tidak lagi punya salinan. `tests/test_stage_registry.py` menuntut jumlah = 18, id unik, dan setiap tahap punya artefak.

**Bukti sesudah.** `grep -c "^  - code:" workflows/stages.yaml` → 18; tes registry lulus; menambah tahap di YAML langsung terlihat di CLI dan dashboard.

**Sisa risiko.** YAML baru satu arah (dibaca). Kalau nanti ada penulis otomatis, perlu uji bolak-balik.

---

### T-07 · `docs_lint` hanya memeriksa indeks, bukan rujukan path

**Verifikasi.** Saya jalankan pemeriksa baru ke seluruh dokumen: **19 rujukan path mati** (mis. `docs/…md` yang sudah diarsipkan, `workflows/*.yaml` yang belum ada saat itu). Sebelum perbaikan, `docs_lint` melaporkan PASS karena hanya memeriksa bahwa dokumen **terdaftar** di indeks.

**Akar masalah.** Aturan “setiap dokumen terindeks” tegak, tapi aturan “setiap rujukan hidup” tidak pernah diukur — jadi dokumen bisa menunjuk ke tempat yang tidak ada dan tetap hijau.

**Perbaikan.** Pemeriksaan rujukan path relatif di dalam blok kode-spesifik/backtick: setiap `docs/...`, `scripts/...`, `platform/...`, `workflows/...` yang disebut harus ada di disk (pengecualian eksplisit untuk pola yang memang belum ada).

**Bukti sesudah.** **264 rujukan path diperiksa, 0 mati** (`make docs-lint` PASS; 5.122 token backtick disaring dulu). Sembilan belas rujukan mati itu diperbaiki (diarahkan ke path yang benar atau ke `docs/archive/`).

---

### T-08 · Higiene repo tidak mengenali path absolut `$HOME/...`

**Verifikasi.** `git status` memperlihatkan sembilan entri aneh berawalan `"$HOME/.local/share/sdb-deck/profile/..."` — berkas profil Chromium yang pernah ikut ter-stage dengan path literal. Higiene repo tidak menandainya karena aturannya hanya memeriksa ukuran, PII, dan PDF.

**Perbaikan.** Aturan baru di `scripts/repo_hygiene.py`: **R6** menolak path yang mengandung literal `$HOME`/`${HOME}`/`~` di indeks git; **R7** menolak symlink dengan target absolut (symlink relatif ke luar repo juga ditandai). Uji di `tests/test_repo_hygiene_rules.py`.

**Bukti sesudah.** `make hygiene` → 475 berkas dinilai, **0 FAIL**, 4 WARN (semua utang lama, tercatat di baseline).

---

## 6. Temuan C — Gerbang tanpa uji penjaga

Ini temuan yang paling penting dan paling mudah salah dibaca. Klaimnya **bukan** “kodenya salah”, melainkan **“kodenya benar tapi tidak ada yang menghalangi orang merusaknya”**. Cara mengujinya: uji mutasi.

### T-09/T-13 · Uji mutasi: 50% → 100%

**Cara kerja.** `tools/mutation_gate.py` punya 10 mutan, tiap mutan adalah **satu** perubahan kecil pada logika keamanan/gerbang (mis. `if age_h > max_age:` → `if False:`). Untuk tiap mutan: patching sementara → jalankan suite → **bila suite tetap hijau, mutan itu SINTAS** (= tidak ada tes yang menjaga baris itu) → kembalikan berkas.

**Hasil sebelum.** 10 mutan, **5 sintas** → kill rate **50%**.

**Hasil sesudah.** 10 mutan, **0 sintas** → **100%**. (Detail per mutan di §9.)

**Kenapa ini lebih jujur daripada “coverage 88%”.** *Coverage* bilang “baris ini dijalankan”. Mutasi bilang “baris ini **dijaga**”. Lima mutan yang sintas semuanya berada di baris yang **sudah tercakup coverage** — bukti bahwa coverage saja menipu.

### T-10 · *Coverage* tidak diukur dan tanpa ambang

**Verifikasi.** Tidak ada `coverage` di venv; tidak ada ambang di Makefile/CI. Angka *coverage* yang beredar sebelumnya tidak bisa direproduksi.

**Perbaikan.** `coverage` dipasang sebagai alat pengembangan, pengukuran **branch**, ambang **85%** di CI (`--fail-under=85`).

**Bukti sesudah.** **88%** cabang: `store.py` 95%, `billing.py` 91%, `metrics.py` 87%, `app.py` 85%, `sdb_platform/runtime/worker.py` 77% (paling lemah — worker adalah target perbaikan berikutnya).

### T-11 · Uji `integrations/` tidak dijalankan

**Verifikasi.** `make test` hanya `pytest tests skills`; folder `integrations/` berisi **57 uji** yang hanya berjalan bila ada orang ingat mengetiknya. Uji yang tidak pernah jalan = uji yang tidak ada.

**Perbaikan.** `make test` → `pytest tests skills integrations -q`; CI memakai target yang sama.

### T-12 · `docs-lint` tidak dipanggil di CI

**Verifikasi.** `.github/workflows/ci.yml` menjalankan lint + test + packs, **tanpa** `docs-lint` dan **tanpa** higiene. Akibatnya aturan dokumen (ADR-0008) tidak bisa gagal di CI — hanya bisa gagal di laptop.

**Perbaikan.** Langkah CI baru: `make docs-lint` + `make hygiene`.

### T-13 · Lima mutan yang sintas (dan uji penjaganya)

| Mutan | Yang dirusak | Mutan sintas karena | Uji penjaga baru |
|---|---|---|---|
| M1 | pemeriksaan umur **artefak** dimatikan | tidak ada tes yang memakai artefak kedaluwarsa | `test_release_gate_rejects_stale_artifact` |
| M2 | pemeriksaan umur **verdict** dimatikan | idem untuk verdict | `test_release_gate_rejects_stale_verdict` |
| M6 | pemeriksaan `prev_hash` audit-log dilewati | tes hanya menambah entri, tak pernah menghapus | `test_audit_log_detects_removed_head_of_chain` |
| M7 | penolakan `..` di `validate_slug` dilewati | tes hanya memakai `../x`, tak pernah `a..b` | `test_validate_slug_rejects_dotdot_inside_plain_name` (4 kasus) |
| M9 | penolakan origin di dalam loop capture dilewati | `origin_allowed()` diuji, pemanggilnya tidak | `test_redirect_keluar_scope_membatalkan_capture` (Playwright palsu, redirect ke `evil.test`) |

**Catatan kejujuran tentang M2.** Pada run gerbang, ringkasan otomatis mencetak nama tes `test_release_gate_rejects_stale_artifact` untuk M2, padahal pembunuhnya sebenarnya `test_release_gate_rejects_stale_verdict`. Saya buktikan ulang secara manual: dengan mutan M2 aktif hanya uji `…stale_verdict` yang gagal. Artinya **M2 benar-benar terbunuh**, tapi **pelaporan gerbang punya cacat kecil** (mengambil nama tes gagal pertama dari keluaran `pytest -x` yang dipotong). Cacat pelaporan itu dicatat di sini, belum diperbaiki.

---

## 7. Temuan D — Kebersihan repo

### T-14 · Sembilan berkas sampah ber-path `$HOME/...`

**Verifikasi.** `git status --short` menunjukkan sembilan entri `D` dengan nama literal `"$HOME/.local/share/sdb-deck/profile/…"` — sisa percobaan Command Deck lama yang tersimpan di indeks git sebagai path **relatif** (direktori bernama `$HOME` di dalam repo).

**Perbaikan.** Dihapus dari indeks dan disk. Aturan R6 (T-08) mencegah terulang.

**Bukti sesudah.** `git status --short | grep '\$HOME'` → kosong. `find . -maxdepth 1 -name '$HOME'` → kosong.

### T-15 · Symlink absolut

**Verifikasi.** Belum ada symlink absolut hari ini, tapi tidak ada aturan yang melarangnya — satu `ln -s /home/anashadi/.ssh/id_rsa repo/` akan masuk tanpa peringatan.

**Perbaikan.** R7 di `repo_hygiene.py`: symlink dengan target absolut = FAIL; target relatif keluar repo = WARN.

---

## 8. Temuan E — Operasional (butuh keputusan Anda)

### T-16 · `sdb-control-plane` gagal start terus-menerus

**Verifikasi (hari ini, 13:00 WIB):**

```
systemctl --user status sdb-control-plane
  Active: activating (auto-restart) (Result: exit-code)
  Process: ... code=exited, status=2
systemctl --user show sdb-control-plane -p NRestarts
  NRestarts=744
```

**Akar masalah.** `app.py` menolak start bila `SDB_ADMIN_KEY` kosong/`< 24` karakter. Unit systemd memakai `EnvironmentFile=%h/.config/sdb/control.env`, dan berkas itu **hanya berisi 2 kunci**: `SDB_TG_BOT_TOKEN`, `SDB_TG_CHAT_ID`. Jadi bukan bug kode — **kunci admin memang belum pernah dibuat**.

**Mengapa saya tidak memperbaikinya sendiri.** Membuat `SDB_ADMIN_KEY` berarti membuat **kredensial baru**. Aturan yang Anda tetapkan: kredensial baru butuh izin eksplisit. Selain itu ada jebakan nyata: `control.env` **sudah berisi 2 kunci Telegram** — kalau ditulis dengan perintah `cat > control.env` seperti yang tertulis di dokumen A–Z §Q.3, **dua kunci Telegram itu akan terhapus**. Ini salah satu dari tiga hal yang saya tahan di item 3 dan minta izin dulu.

### T-17 · 0 tenant, 0 job, 0 rupiah

**Verifikasi.** `data/control.db` berisi tabel lengkap tapi tanpa tenant. Ini **bukan** cacat teknis; ia mengukur bahwa produk belum pernah dipakai orang lain. Tidak ada patch yang bisa mengubahnya, dan saya tidak akan menulis angka lain.

### T-18 · Berkas besar & satu pola PII

**Verifikasi.** `make hygiene` → 4 WARN: `dashboard/vendor/three.module.min.js` 655 KB, `reports/upgrade-evidence/thirdparty-scan-crawlee.json` 1477 KB, `…lighthouse.json` 521 KB, dan pola `hello@davidmiller[.]io` di `trivy-oss-agency.json`.

**Keputusan.** Dibiarkan, tercatat di `platform/hygiene-baseline.json`. Ketiganya **artefak bukti pihak ketiga**; menghapusnya akan memutus jejak audit. Kalau Anda ingin repo bebas PII, berkas itu harus dipindah ke object store (ADR-0002) — bukan di-`sed` diam-diam.

---

## 9. Uji mutasi — tabel lengkap

`make mutation` (≈40 s, 10 mutan). Kolom “pembunuh” = uji yang gagal saat mutan aktif.

| Mutan | Berkas | Yang dirusak | Sebelum | Sesudah | Pembunuh |
|---|---|---|---|---|---|
| M1 | `scripts/release_check.py` | umur artefak diabaikan | SINTAS | KILLED | `test_release_gate_rejects_stale_artifact` |
| M2 | `scripts/release_check.py` | umur verdict diabaikan | SINTAS | KILLED | `test_release_gate_rejects_stale_verdict` |
| M3 | `tools/recon-forge.py` | batas izin target dilewati | KILLED | KILLED | `tests/test_recon_forge.py` |
| M4 | `tools/recon-forge.py` | pemisahan data terlarang dilewati | KILLED | KILLED | `tests/test_recon_forge.py` |
| M5 | `scripts/gate_check.py` | pemeriksaan pemilik izin dilewati | KILLED | KILLED | `tests/test_gerbang_g1.py` |
| M6 | `tools/audit-log.py` | `prev_hash` tidak diperiksa | SINTAS | KILLED | `test_audit_log_detects_removed_head_of_chain` |
| M7 | `scripts/sdb_common.py` | `..` lolos dari `validate_slug` | SINTAS | KILLED | `test_validate_slug_rejects_dotdot_inside_plain_name[4 kasus]` |
| M8 | `scripts/capture_web.py` | `origin_allowed` selalu benar | KILLED | KILLED | `tests/test_capture_scope.py` |
| M9 | `scripts/capture_web.py` | origin tidak dicek di loop capture | SINTAS | KILLED | `test_redirect_keluar_scope_membatalkan_capture` |
| M10 | `scripts/evidence_lint.py` | label bukti tidak divalidasi | KILLED | KILLED | `tests/test_evidence_lint.py` |

**Skor: 5/10 (50%) → 10/10 (100%).** Tanpa mutasi, kelima celah ini tidak terlihat: suite tetap hijau 533 tes.

---

## 10. Angka akhir terverifikasi

| Metrik | Nilai | Catatan |
|---|---|---|
| Item tes | **629 lulus** (+3 subtes), 50 berkas, 49,83 s | `make test` = `tests skills integrations`; `def test_` = 471 di `tests/`, sisanya parametrize |
| *Coverage* cabang `sdb_platform` | **88%** | 984 stmt / 99 miss; 268 cabang / 33 parsial |
| Mutan terbunuh | **10/10** | `make mutation` |
| `make check` | **PASS** | 7 gerbang |
| Rujukan dokumen | **264 path diperiksa, 0 mati** (dari 5.122 token backtick) | `make docs-lint` |
| Higiene | 475 berkas, **0 FAIL**, 4 WARN | `make hygiene` |
| Pack divisi | **8/8 PASS** | `make packs` |
| Drift skill | **119/119 OK** | `make drift` |
| Service control plane | **exit 2, 744 restart** | butuh `SDB_ADMIN_KEY` (izin Anda) |
| Tenant / job / pendapatan | **0 / 0 / 0** | apa adanya |

---

## 11. Reproduksi (salin-tempel)

```bash
cd ~/super-dev-builders

# 1. Seluruh gerbang lokal
make check                                   # lint, registry, test, drift, higiene, packs, docs-lint

# 2. Jumlah tes yang sebenarnya
.venv/bin/python -m pytest tests skills integrations 2>&1 | tail -1   # "629 passed ..."
.venv/bin/python -m pytest tests/ 2>&1 | tail -1                       # "533 passed ..."

# 3. Coverage cabang
.venv/bin/python -m coverage run --branch --source=sdb_platform -m pytest tests/ -q
.venv/bin/python -m coverage report -m

# 4. Uji mutasi (10 mutan)
make mutation

# 5. Bukti indeks dipakai (bukan dugaan)
.venv/bin/python - <<'PY'
from sdb_platform.control_plane.store import Store
s = Store(":memory:")
print(" ".join(r[3] for r in s.db.execute(
  "EXPLAIN QUERY PLAN SELECT job_id FROM jobs WHERE tenant_id=? AND status='queued'"
  " AND cancel_requested=0 ORDER BY created_at, rowid LIMIT 1", ("t",))))
PY

# 6. Kondisi layanan (jujur, apa adanya)
systemctl --user show sdb-control-plane -p ActiveState -p Result -p NRestarts
```

---

## 12. Sisa risiko & urutan tindakan berikutnya

| Prioritas | Tindakan | Alasan | Butuh izin? |
|---|---|---|---|
| 1 | Isi `SDB_ADMIN_KEY` di `~/.config/sdb/control.env` — **tambahkan**, jangan menimpa (2 kunci Telegram sudah ada) | layanan crash-loop 744× | **ya** |
| 2 | Ukur ulang + naikkan cabang `sdb_platform/runtime/worker.py` (77%) | satu-satunya modul di bawah 85% | tidak |
| 3 | Perbaiki pelaporan nama tes pada `mutation_gate` (cacat M2 di §9) | laporan bisa menyesatkan | tidak |
| 4 | Pindahkan 3 artefak besar ke object store (ADR-0002) | 1477 KB + 655 KB + 521 KB di git | tidak |
| 5 | Tambah job `ANALYZE` berkala untuk `control.db` | indeks parsial bisa salah pilih rencana | tidak |
| 6 | Uji bolak-balik `stages.yaml` bila kelak ada penulis otomatis | mencegah dua sumber kebenaran kembali | tidak |

---

## Lampiran A — Berkas yang berubah karena audit ini

**Kode:** `sdb_platform/control_plane/store.py`, `sdb_platform/control_plane/app.py`, `scripts/docs_lint.py`, `scripts/repo_hygiene.py`, `scripts/workflow_run.py`, `dashboard/ws_api.py`.
**Baru:** `workflows/stages.yaml`, `scripts/stage_registry.py`, `tools/mutation_gate.py`.
**Uji baru:** `tests/test_control_plane_perf.py`, `tests/test_stage_registry.py`, `tests/test_mutation_gate.py`, `tests/test_repo_hygiene_rules.py`, + 8 uji tambahan di `tests/test_scripts.py` dan `tests/test_capture_scope.py`.
**Gerbang:** `Makefile` (target `check`, `test`, `mutation`), `.github/workflows/ci.yml` (docs-lint, hygiene, coverage).
**Dokumen:** laporan ini, `docs/INDEX.md`, `docs/SDB_LENGKAP_A_Z_20261105.md` (angka & status repo).

---

## Lampiran B — Kamus awam (untuk item 3)

| Istilah | Arti sederhana |
|---|---|
| **Indeks basis data** | Daftar isi buku. Tanpa indeks, mencari satu nama berarti membaca semua halaman (92 ms). Dengan indeks, langsung ke halaman yang tepat (0,06 ms). |
| **WAL** | Cara menulis buku harian: catat dulu di lembar Coretan cepat, baru disalin ke buku besar nanti. Tulis jadi cepat; risiko: kalau listrik mati sebelum disalin, coretan terakhir bisa hilang. |
| **Nagle** | Kebiasaan “tunggu sebentar, siapa tahu ada surat susulan biar bisa dikirim satu amplop”. Bagus untuk kiriman besar, buruk untuk jawaban pendek seperti health check (40 ms). |
| **Backlog** | Panjang bangku tunggu di depan pintu. Isinya 5 kursi: begitu 6 orang datang bersamaan, sisanya ditolak. Dinaikkan jadi 128 kursi. |
| **Mutan** | Sengaja merusak satu baris kode untuk melihat apakah alarm berbunyi. Kalau alarm tetap sunyi, berarti tidak ada alarm di titik itu. |
| **Coverage** | Berapa banyak halaman buku yang pernah **dibuka**. Tidak menjamin isinya **dipahami** — karena itu perlu mutan. |
| **Kredensial** | Kunci rumah. Membuat kunci baru = mengubah siapa yang bisa masuk, jadi butuh izin pemilik. |

---

*Laporan ini dibuat dari pengukuran langsung pada mesin `anashadi`, 5 November 2026. Setiap klaim punya perintah verifikasi di §11; setiap angka “sebelum” diberi label sebagai angka historis. Repo: <https://github.com/anashadi-node/super-dev-builders>*
