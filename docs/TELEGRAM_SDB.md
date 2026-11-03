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
- Job dianggap selesai jika `README.md` dan `VERIFY.md` benar-benar ada — bukan karena
  agen mengaku selesai.
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
