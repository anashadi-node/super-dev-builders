# Telegram SDB — kanal operasional (report 4 jam, tanya-jawab, perintah build)

Dokumen ini menjelaskan cara kerja bot `@super_dev_builders_bot` setelah
penambahan tiga kemampuan: **laporan otomatis**, **tanya-jawab ekosistem**, dan
**perintah membangun produk**.

## 1. Prinsip desain

| Prinsip | Konsekuensi teknis |
|---|---|
| Hanya pemilik | Semua handler membandingkan `chat.id` dengan `SDB_TG_CHAT_ID`; pesan lain diabaikan tanpa balasan (tidak membocorkan bahwa bot hidup). |
| Laporan tanpa LLM | `scripts/sdb_report.py` membaca berkas, git, systemd, SQLite — deterministik, cepat (<1 s), tanpa biaya token, tidak bisa berhalusinasi. |
| Tanya-jawab ber-grounding | `/ask` menyuntikkan laporan nyata sebagai DATA; agen dilarang menjawab di luar data, dan hanya diberi toolset `terminal,file,skills` (tanpa web/browser/delegasi). |
| Build dua tahap | Spesifikasi dulu → manusia menyetujui → baru kode. Tidak ada kode yang lahir dari tebakan. |
| Sandbox kerja | Worker hanya bekerja di `~/sdb-builds/<id>-<slug>/`; direktori itu dipaksa, bukan disarankan. |

## 2. Perintah

### Monitor
| Perintah | Isi |
|---|---|
| `/status` `/health` `/revenue` | ringkasan cepat (sudah ada sebelumnya) |
| `/eco` | kondisi ekosistem lengkap: layanan, timer, deck, control.db, host, alert |
| `/projects` | progres tiap proyek: tugas selesai/total, jumlah berkas, commit terakhir, perubahan belum di-commit |
| `/ask <pertanyaan>` | jawaban analis dari data nyata (contoh: *"proyek mana yang mandek?"*, *"berapa commit 7 hari terakhir?"*) |

### Build
| Perintah | Isi |
|---|---|
| `/build <deskripsi>` | buat job; worker menyusun `SPEC.md`, `PLAN.md`, `QUESTIONS.md` |
| `/job <id>` | status + riwayat + folder kerja |
| `/approve <id>` | setujui spesifikasi → mulai implementasi |
| `/revise <id> <arahan>` | minta spesifikasi diulang dengan arahan baru |
| `/answer <id> <jawaban>` | jawab pertanyaan spesifikasi (dipakai saat implementasi) |
| `/reject <id> [alasan]` | tolak |
| `/retry <id>` | ulangi job gagal/dibatalkan |
| `/cancel <id>` | batalkan job yang belum selesai |
| `/jobs` | daftar job terbaru |

Contoh `/build` yang menghasilkan brief berkualitas:

```
/build Website katalog villa: daftar villa + filter harga & jumlah tamu,
halaman detail dengan galeri, tombol booking WhatsApp yang mengisi pesan
otomatis, admin CRUD villa (tanpa login pihak ketiga), mobile-first,
warna netral, bahasa Indonesia. Tidak perlu pembayaran online.
```

## 3. Alur build (apa yang terjadi setelah `/build`)

```
Telegram /build
   └─> sdb_jobs.create_job()            status: spec_queued
        └─> worker (systemd) claim      status: spec_running
             └─ hermes chat --oneshot --in <dir>
                  SPEC.md PLAN.md QUESTIONS.md
             └─> notifikasi Telegram    status: spec_ready
   Anda /approve <id>                   status: build_queued
        └─> worker claim                status: building
             └─ hermes (resume sesi spec) implementasi + tes + VERIFY.md
                (maks. 3 ronde; bila dokumen belum ada, satu ronde dokumentasi)
        └─> notifikasi + bukti          status: done
                                       status: paused  -> /retry <id> melanjutkan
```

Definisi selesai yang dipaksa ke agen: fitur Must berfungsi, ada tes/smoke test
yang benar-benar dijalankan, `README.md` berisi perintah menjalankan,
`VERIFY.md` berisi bukti output, dan `GAPS.md` bila ada yang belum selesai.

## 4. Layanan & jadwal

| Unit | Peran |
|---|---|
| `sdb-tg-bot.service` | long-poll Telegram, semua perintah |
| `sdb-build-worker.service` | menjalankan job build (satu per satu) |
| `sdb-report-4h.timer` | memicu `sdb-report-4h.service` pada 00/04/08/12/16/20 WIB |

Cek status:

```bash
systemctl --user list-timers sdb-report-4h.timer
systemctl --user status sdb-tg-bot sdb-build-worker --no-pager
journalctl --user -u sdb-build-worker -n 30 --no-pager
```

Uji laporan tanpa menunggu jadwal:

```bash
systemctl --user start sdb-report-4h.service
journalctl --user -u sdb-report-4h.service -n 5 --no-pager
```

## 5. Konfigurasi (berkas rahasia, jangan di-commit)

`~/.config/sdb/control.env` — permission `600`, pemilik `anashadi`:

```
SDB_TG_BOT_TOKEN=<token BotFather>
SDB_TG_CHAT_ID=<chat id pemilik>
```

Opsional (boleh ditambah bila perlu):

```
SDB_BUILD_MODEL=            # kosong = model default Hermes
SDB_SPEC_TIMEOUT=900        # detik, batas tahap spesifikasi
SDB_BUILD_TIMEOUT=3600      # detik, batas tahap implementasi
SDB_BUILD_TURNS=160         # maksimum iterasi tool per tahap
```

Token **tidak pernah** diwariskan ke proses agen: worker dan `/ask` menghapus
`SDB_TG_BOT_TOKEN`/`SDB_TG_CHAT_ID` dari environment anak.

## 6. Batas yang perlu diketahui

- Worker memproses **satu job pada satu waktu** — job kedua menunggu di antrean.
- Satu sesi agen punya batas turn, jadi build besar berjalan bertahap: 3 ronde kerja
  (default `SDB_BUILD_ROUNDS=3`) lalu satu ronde dokumentasi. Job yang belum tuntas
  berstatus `paused` (bukan `failed`) agar bisa dilanjutkan tanpa mengulang dari nol.
- Job dianggap selesai hanya lewat **gerbang penyelesaian**: `README.md` dan `VERIFY.md`
  harus berkas regular non-kosong, bukan symlink dan bukan hardlink (hardlink bisa
  menautkan berkas rahasia ke dokumen), direktori kerja harus di dalam `SDB_BUILDS`,
  bukan symlink, namanya sesuai ID job, dan `dir` di DB harus sama dengan job yang
  diproses. Keberadaan dokumen saja tidak cukup, dan isi `VERIFY.md` tidak pernah
  dianggap bukti mesin.
- Kode penolakan ditulis ke kolom `error`: `WORKSPACE_INVALID`, `DOCS_INVALID`,
  `UNVERIFIED`, `EVIDENCE_INVALID`, `VERIFY_FAIL`, `VERIFY_TIMEOUT`,
  `COMPLETION_ERROR`. Job tetap `paused` (bukan `failed`) agar `/retry` bisa lanjut.
- **Level bukti** dicatat pada event `completion`:
  `ATTESTED` = dokumen diperiksa, pengujian TIDAK dijalankan mesin (bukan bukti
  release independen); `VERIFIED` = ada event `verify` PASS yang terikat ke job,
  direktori, dan sidik isi workspace saat itu.
- **Sidik workspace** (`tree_sha256`) menghash isi semua berkas regular; direktori
  dependensi/cache (`node_modules`, `.venv`, `.git`, cache) hanya dicatat
  keberadaannya, jadi perubahan di dalamnya tidak mengubah sidik. Bila anggaran
  byte/waktu hash habis, sidik ditandai **tidak lengkap** (`digest_complete=false`)
  dan bukti `verified` ditolak — sidik parsial tidak dipakai sebagai bukti.
- Kebijakan gerbang diatur `SDB_DONE_POLICY`. Default kode `attested` agar perilaku
  lama tidak berubah saat deploy. Nilai `verified` menuntut bukti mesin; nilai kosong
  atau tak dikenal diperlakukan `verified` (fail-closed). Mengubah ke `verified` butuh
  persetujuan Owner karena membuat build tanpa bukti berhenti `paused`. **Jangan
  menyalakannya** sebelum C2-B2 selesai: selama verifier belum terisolasi, `verified`
  hanya menambah lapisan tanpa menambah jaminan.

### 6a. Kontrak evidence `sdb.verify.evidence/1` (C2-B1)

Event `verify` boleh berisi kontrak bertanda tangan. Bukti ini diperiksa penuh;
kegagalan apa pun membuat job tetap `paused` (tidak pernah `done`).

| Bagian | Isi wajib |
|---|---|
| `schema`, `digest_alg` | `sdb.verify.evidence/1`, `tree-sha256/1` |
| `project_id`, `job_id` | identitas job; harus sama dengan job yang memproses |
| `request_nonce` | 64 hex, diterbitkan worker, sekali pakai |
| `snapshot` | `snapshot_id` (`sha256:<64 hex>`), `complete: true` |
| `workspace_digest` | harus sama dengan sidik isi workspace saat gerbang berjalan |
| `timestamps` | `issued_at`, `finished_at`, `expires_at` (epoch detik) |
| `verifier` | `id` harus ada di `SDB_EVIDENCE_VERIFIERS` |
| `signature` | `alg: ssh-ed25519`, `namespace: sdb-verify-v1`, `sig` blok OpenSSH |
| `execution` | exit code, `timed_out`, dan hitungan tes (`collected/passed/failed/…`) |
| `acceptance_criteria` | `id` + `criteria_digest` yang dipin lokal |
| `verdict` | `execution` dan `acceptance` (`PASS`/`FAIL`) |

Tanda tangan dihitung atas **byte kanonik** payload tanpa field `signature`
(kunci terurut, tanpa spasi, UTF-8). Verifikasi memakai `ssh-keygen -Y verify`
terhadap `allowed_signers` yang dipin; tidak ada dependensi Python baru.

**Tiga tingkat bukti** — jangan disamakan:

| Tingkat | Arti |
|---|---|
| `EXECUTION_VERIFIED` | perintah uji benar-benar dijalankan pada snapshot yang dinyatakan, di sandbox, hasilnya terekam |
| `ACCEPTANCE_VERIFIED` | eksekusi + semua syarat penerimaan: nol gagal/error, `collected > 0`, tidak ada `deselect` tanpa alasan, `criteria_digest` cocok |
| `RELEASE_ELIGIBLE` | **tidak pernah** diberikan worker/modul verifikasi; hanya catatan persetujuan Owner |

`exit code 0` bukan penerimaan: tes kosong, tes gagal, atau tes yang dibuang diam-diam
tetap menghasilkan `EXECUTION_VERIFIED` saja, bukan `ACCEPTANCE_VERIFIED`.

Variabel lingkungan baru:

| Variabel | Default | Fungsi |
|---|---|---|
| `SDB_EVIDENCE_MODE` | `legacy` | `legacy` menerima event C2-A lama; `strict` menolaknya (`EVIDENCE_LEGACY_REJECTED`). Nilai tak dikenal → `strict`. **`SDB_DONE_POLICY=verified` menolak berjalan tanpa `strict`** (`EVIDENCE_MODE_REQUIRED`) — jalur tanpa tanda tangan tidak boleh hidup di bawah `verified` |
| `SDB_EVIDENCE_ALLOWED_SIGNERS` | kosong | berkas `allowed_signers` OpenSSH; wajib ada di mode strict |
| `SDB_EVIDENCE_VERIFIERS` | kosong | daftar `verifier.id` yang diizinkan (dipisah koma) |
| `SDB_ACCEPTANCE_CRITERIA_DIGEST` | kosong | sidik kriteria penerimaan yang dipin |
| `SDB_VERIFY_TTL` | `1800` | masa berlaku nonce (60…86400 detik) |
| `SDB_STALE_BUILD_SECONDS` | `7200` | umur maksimum status berjalan sebelum dikembalikan reaper ke `paused` |

Kode penolakan baru ditulis ke kolom `error`: `EVIDENCE_SCHEMA`,
`EVIDENCE_JOB_MISMATCH`, `EVIDENCE_NO_NONCE`, `EVIDENCE_NONCE_UNKNOWN`,
`EVIDENCE_REQUEST_EXPIRED`, `EVIDENCE_REPLAY`, `EVIDENCE_EXPIRED`,
`EVIDENCE_CLOCK`, `EVIDENCE_SNAPSHOT_INCOMPLETE`, `EVIDENCE_DIGEST_INCOMPLETE`,
`EVIDENCE_DIGEST_MISMATCH`, `EVIDENCE_UNKNOWN_VERIFIER`, `EVIDENCE_NO_SIGNATURE`,
`EVIDENCE_SIGNATURE_ALG`, `EVIDENCE_UNTRUSTED_SIGNER`,
`EVIDENCE_VERIFIER_UNAVAILABLE`, `EVIDENCE_SIGNER_STORE`,
`EVIDENCE_LEGACY_REJECTED`, `EVIDENCE_MODE_REQUIRED`, `ACCEPTANCE_NOT_MET`,
`EVIDENCE_LEVEL_UNKNOWN`, `DONE_CONFLICT`, `DONE_WRITE_FAILED`.

**Dua gerbang, bukan satu.** Di bawah `SDB_DONE_POLICY=verified`, bukti yang sah
tetap bisa berhenti di level **eksekusi**: tanda tangan benar, `workspace_digest`
cocok, tetapi `acceptance` belum terpenuhi (ada tes gagal, `collected=0`,
`criteria_digest` beda, `verdict.acceptance=FAIL`, atau `deselect` tanpa alasan).
Kondisi itu **bukan** `done`: worker menulis `ACCEPTANCE_NOT_MET` dan status
`paused`. Hanya `ACCEPTANCE_VERIFIED` yang boleh menutup job; `RELEASE_ELIGIBLE`
tidak pernah diberikan oleh worker. `exit code 0` bukan bukti kualitas.

**Transisi `done` atomik.** Status `done`, event `verify_accepted` (penanda nonce
terpakai), event `done`, dan event `completion` ditulis dalam **satu transaksi**
`BEGIN IMMEDIATE` (`finish_job`). Status dipindahkan dengan CAS
(`WHERE status IN ('building','spec_running')`); bila job sudah dipindahkan proses
lain, atau penulisan gagal, transaksi di-rollback: **nonce tidak terbakar** dan
`/retry` tetap bisa memakai bukti yang sama. Pemeriksaan nonce diulang di dalam
kunci tulis, jadi dua penerimaan duplikat tidak bisa menghasilkan dua `done`.
Saat transisi gagal, `paused` juga ditulis dengan CAS `status='building'`: job yang
sudah dipindahkan proses lain (`done`, `cancelled`) **tidak** ditimpa dan tidak
diberi kode error palsu — hanya satu notifikasi "diabaikan". Galat basis data saat
menulis (bukan penolakan bukti) dilaporkan sebagai `DONE_WRITE_FAILED` dengan
`paused`, jadi `/retry` langsung bisa dipakai; job tidak menggantung `building`
sampai reaper 2 jam.

**Angka tidak berhingga.** `json.loads` menerima literal `NaN`/`Infinity`,
sedangkan byte yang ditandatangani tidak boleh memuatnya. Payload seperti itu
ditolak sebagai `EVIDENCE_SCHEMA` (bukan `COMPLETION_ERROR`), fail-closed.

**Penerbitan nonce (jalur operator).** `verified` tidak bisa dipakai tanpa nonce,
dan nonce hanya keluar lewat perintah resmi:

```bash
python3 scripts/sdb_build_worker.py --issue-nonce <job_id>   # cetak 64 hex ke stdout
```

Nonce disimpan sebagai event `verify_request` beserta `expires_at`
(`SDB_VERIFY_TTL`, batas 60…86400 dtk). Penanda `verify_accepted` ditulis **bersama**
transisi `done` (satu transaksi), jadi nonce baru dianggap terpakai kalau job
benar-benar selesai; job yang gagal di tengah jalan tetap bisa di-`/retry` dengan
bukti yang sama. Event `verify` mentah atau sampah tidak pernah membakar nonce —
kalau dibakar, satu event palsu bisa mematikan jalur `verified` milik job itu
sendiri (DoS diri).
Masa berlaku evidence yang ditandatangani juga dibatasi jendela permintaan yang
sama dan maksimum `SDB_VERIFY_TTL`/86400 detik.

**Syarat berkas signer & alat verifikasi.** `allowed_signers` wajib path absolut,
bukan symlink, bukan world-writable pada dirinya **maupun parent-nya**, milik root
atau user worker, dan ukurannya ≤ 1 MiB; isinya dibaca sekali lalu disalin ke
direktori sementara 0700 sebelum dipakai `ssh-keygen`, sehingga penukaran berkas di
antara pemeriksaan dan pemakaian tidak berpengaruh. `ssh-keygen` dicari hanya di
path absolut milik root (`/usr/bin`, `/bin`, `/usr/local/bin`), dijalankan dengan
`PATH`, `HOME`, `TMPDIR` minimal dan `cwd` sementara — tidak lewat `PATH` worker.
Parent yang group-writable masih diterima: **sisa risiko** (satu grup = satu
kepercayaan), tercatat sebagai temuan C2-B2.

**Reaper status menggantung.** Job berstatus `building`/`spec_running` yang
`updated`-nya lebih tua dari `SDB_STALE_BUILD_SECONDS` dikembalikan ke `paused`
dengan `error=STALE_RUNNING`. Penulisan memakai compare-and-swap
(`WHERE id=? AND status=? AND updated=?`), jadi job yang selesai bersamaan tidak
"mundur" menjadi `paused`. Setiap ronde build mengirim heartbeat yang memperbarui
`updated`, sehingga build panjang tidak dipanen.

**Batas kejujuran (penting).** Verifikasi tanda tangan ini **belum** membuat pipeline
aman: worker, builder, DB, dan `allowed_signers` berada di akun yang sama, sehingga
bukti masih bisa dipalsukan di sisi penyimpanan. Itu sebabnya `verified` tetap
dilarang sampai verifier terisolasi (C2-B2) berdiri.

- Build berjalan sebagai user `anashadi` dengan toolset penuh (perlu menulis
  kode, menjalankan tes). Pembatasnya: hanya direktori job, aturan keras di
  prompt, `--max-turns`, `--run-budget`, dan proses dimatikan paksa bila
  melewati batas waktu.
- Hasil terbaik datang dari brief yang spesifik. Brief satu baris tetap jalan,
  tetapi agen akan menebak lebih banyak — itulah gunanya tahap `QUESTIONS.md`.
- Laporan 4 jam hanya menyentuh berkas state `dashboard/state/report_snapshot.json`
  (untuk menghitung delta). Selebihnya baca-saja.

## 7. Verifikasi (dijalankan saat pemasangan)

```bash
make test                                   # seluruh suite
/usr/bin/python3 -m pytest tests/test_sdb_telegram_ops.py -q
python3 scripts/sdb_report.py --print full  # laporan tanpa kirim
python3 scripts/sdb_jobs.py stats           # isi antrean
```
