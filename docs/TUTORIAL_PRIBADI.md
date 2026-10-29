# Panduan Pribadi SDB — di PC Ini dan lewat Telegram

Dokumen untuk **satu pengguna**: Anda, di PC ini (Ubuntu 22.04, Yogyakarta). Tutorial lain
(`TUTORIAL_PENGGUNAAN`) membahas kondisi produk sudah launching berbayar; dokumen ini sebaliknya —
PC Anda sendiri, dashboard lokal, dan bot Telegram khusus SDB.

> Versi: v0.7.2. Regenerasi dokumen: `make docs-tutorial`.

---

## Daftar Isi

{{TOC}}

---

## 1. Jawaban atas tiga pertanyaan Anda

**"SDB ini agentic AI dengan kemampuan spesifik tertentu — benar?"**

Benar, dengan satu koreksi penting. SDB = **10 profil agen** yang masing-masing punya peran spesifik
(Orchestrator, Recon-Research, Architect, Frontend, Backend, Reviewer-QA, Security Governor,
Auditor, DevOps-Docs, Keamanan) — dikoordinasi lewat Command Deck. Tapi SDB bukan cuma agen-agen:
ada **control plane** (mesin penagihan uang, SQLite ber-rantai hash) dan **worker runtime** (yang
benar-benar mengerjakan job). Analogi: agen-agen adalah "toko", control plane adalah "kasir", worker
adalah "karyawan gudang". Jadi benar SDB adalah agentic AI, tapi ia **juga** produk SaaS dengan
aspek penagihan — dua hal itu jangan tertukar saat dipakai.

**"Apakah perlu & bisa dibuatkan shortcut apps di PC ini?"**

Sebagian **sudah ada** — saya tidak menggantikannya: peluncur `SDB Command Deck` (Chrome app-mode ke
:8484). Yang **kurang** dan kini saya tambahkan: peluncur tutorial, peluncur kesehatan, dan handler
`sdb://`. Yang **tidak** saya buat: aplikasi Electron/Tauri — tanpa nilai tambah, hanya menambah
permukaan pemeliharaan dan risiko keamanan.

**"Bisakah dibuatkan bot Telegram khusus SDB?"**

Bisa, dan sudah dibuat: `scripts/sdb_tg_bot.py`. Desainnya **read-only** dan berbahaya rendah:
membaca status dari `data/control.db` langsung (koneksi SQLite `mode=ro`, secara fisik tak bisa
menulis) atau dari control plane bila hidup. Tidak ada satu pun perintah yang mengubah uang —
perubahan uang tetap lewat control plane dengan jejak audit di git.

---

## 2. Peta sistem di PC ini (fakta terukur)

```
PC ini (Ubuntu 22.04, WIB)
├─ Command Deck      http://127.0.0.1:8484   systemd --user: sdb-command-deck (AKTIF)
├─ Health timer      sdb-deck-health.timer   tiap hari 07:30 WIB (PONG 10 profil)
├─ Control Plane     http://127.0.0.1:8088   (unit dibuat hari ini; start saat dibutuhkan)
├─ Data              ~/super-dev-builders/data/control.db + ~/sdb-workspace/
├─ Peluncur          ~/.local/share/applications/*.desktop (3 lama + 3 baru)
└─ Bot Telegram      scripts/sdb_tg_bot.py (long polling, read-only)
```

Status systemd yang saya verifikasi saat menulis: `sdb-command-deck` **active (running)**,
`sdb-deck-health.timer` **active (waiting)** — jadi dashboard lokal Anda sehat, jangan diutak-atik.

Tiga lapisan, tiga tingkat risiko:

| Lapisan | Untuk apa | Risiko | Akses |
|---|---|---|---|
| Command Deck :8484 | kerja harian bersama agen | rendah (bind 127.0.0.1) | shortcut / `sdb://deck` |
| Control Plane :8088 | uang: job, tagihan, ledger | menengah | curl / skrip klien |
| Bot Telegram | pantau dari HP, di mana pun | rendah (read-only) | chat Telegram |

---

## 3. Persiapan sekali jalan (± 10 menit)

```bash
cd ~/super-dev-builders
make test                          # semua tes harus PASS sebelum apa pun
mkdir -p ~/.local/bin ~/.config/sdb
```

Buat `~/.config/sdb/control.env` (mode `600`):

```bash
SDB_ADMIN_KEY=<acak ≥ 24 karakter>
SDB_WORKER_KEY=<acak ≥ 24 karakter>
SDB_TG_BOT_TOKEN=<dari @BotFather>
SDB_TG_CHAT_ID=<chat ID Telegram Anda>
```

Aturan kunci: tidak pernah di chat/git/laporan; yang pernah tercetak di mana saja dianggap **bocor**
→ ganti. `.env` tidak masuk git (`git check-ignore .env` harus mengonfirmasi).

---

## 4. Sehari-hari di PC ini

### 4.1 Membuka Command Deck

Klik peluncur **SDB Command Deck** (yang sudah ada), atau dari terminal:

```bash
sdb-deck        # cek layanan hidup, lalu buka browser app-mode
sdb-health      # PONG 10 profil agen, ringkasan satu layar
```

Di browser mana pun Anda bisa mengetik `sdb://deck` (handler terpasang hari ini).

### 4.2 Menghidupkan control plane (saat dibutuhkan)

```bash
systemctl --user start sdb-control-plane    # hidupkan
systemctl --user status sdb-control-plane   # cek
systemctl --user stop sdb-control-plane     # matikan
curl -s http://127.0.0.1:8088/healthz       # {"status":"ok"} = hidup
```

Control plane tidak wajib hidup 24/7 di PC ini. Hidupkan saat akan membuat job / menagih / menguji.

### 4.3 Yang aman vs berisiko

| Aman | Berisiko — hanya bila paham, catat di commit |
|---|---|
| `start / stop / status` | edit unit di `~/.config/systemd/user/` |
| `curl /healthz`, `/metrics` | mengubah `SDB_RATE_PER_MIN` produksi |
| baca `data/control.db` mode ro | menulis langsung ke DB (jangan pernah) |

---

## 5. Lembar contekan harian

| Kebutuhan | Perintah |
|---|---|
| Status cepat control plane | `curl -s http://127.0.0.1:8088/healthz` |
| Kesehatan 10 agen | `sdb-health` |
| Buka deck | `sdb-deck` atau `sdb://deck` |
| Buka tutorial | peluncur **SDB Tutorial** |
| Buat job | `POST /v1/jobs` — lihat tutorial utama §7 |
| Terbitkan invoice | `POST /v1/admin/invoices` — tutorial utama §10 |
| Lihat buku besar | `curl ... /v1/ledger -H "X-API-Key: ..."` |
| Cek metrik | `curl ... /metrics -H "X-Admin-Key: ..."` |
| Timer kesehatan | `systemctl --user list-timers \| grep sdb` |

---

## 6. Bot Telegram khusus SDB — `scripts/sdb_tg_bot.py`

Sudah dibuat hari ini, stdlib saja (tanpa dependensi baru), read-only.

### 6.1 Perintah

| Perintah | Jawaban |
|---|---|
| `/status` | state control plane + kesehatan deck (dari `data/control.db` & `health.json`) |
| `/health` | PONG per profil agen + umur health.json |
| `/revenue` | total charge/topup/refund agregat (dari DB, read-only) |
| `/help` | daftar perintah |

Perintah dari chat ID selain milik Anda **diabaikan diam-diam** (bukan ditolak dengan pesan — tidak
memberi tahu penyerang bahwa bot ada).

### 6.2 Kenapa long polling, bukan webhook

Webhook butuh URL publik + sertifikat TLS. PC lokal tidak punya keduanya. Long polling hanya
**menarik** update dari Telegram — tidak membuka satu pun port di jaringan rumah Anda. Ini pilihan
keamanan, bukan keterbatasan.

### 6.3 Keterbatasan fisik yang jujur

**PC ini bukan server 24/7.** Kalau PC mati/reboot/sleep, bot ikut diam — pemantauan malam hari
tidak berfungsi. Dua pilihan jujur:

1. **PC-in-the-loop** (sekarang): jalankan bot saat PC hidup; cukup untuk pantau siang hari.
2. **VPS** (~$4–6/bln): bot hidup 24/7; sambungkan ke PC via SSH tunnel bila mau membaca DB lokal.

Bot tidak bisa dijalankan di GitHub Actions/cron-servis untuk polling (kredensial bot di cloud pihak
ketiga = permukaan bocor baru; tidak saya sarankan).

### 6.4 Menyiapkan token & chat ID (sekali saja, ± 5 menit)

Langkah yang harus Anda lakukan sendiri — token bot hanya bisa dibuat dari akun Telegram Anda, dan
**jangan pernah mengirimkannya ke chat ini**:

1. Buka Telegram → cari **@BotFather** → `/newbot` → beri nama (mis. `SDB Monitor`) dan username
   berakhiran `bot`. BotFather membalas satu baris token `123456:ABC-...` — itu **kata sandi bot**.
2. Simpan token hanya ke berkas: `~/.config/sdb/control.env` baris `SDB_TG_BOT_TOKEN=...`, lalu
   `chmod 600` berkas itu.
3. Kirim `/start` ke bot Anda dari akun Telegram Anda.
4. Ambil chat ID Anda tanpa membuka API manual:

```bash
source ~/.config/sdb/control.env
python3 - <<'EOF'
import json, os, urllib.request
tok = os.environ["SDB_TG_BOT_TOKEN"]
u = f"https://api.telegram.org/bot{tok}/getUpdates"
d = json.loads(urllib.request.urlopen(u, timeout=15).read())
for r in d.get("result", []):
    m = r.get("message") or {}
    print("chat_id:", (m.get("chat") or {}).get("id"), "| dari:", (m.get("from") or {}).get("first_name"))
EOF
```

5. Masukkan angka itu ke `SDB_TG_CHAT_ID`, lalu uji: `python3 scripts/sdb_tg_bot.py --once`
   dan kirim `/status` ke bot.

Token yang pernah ditempel di chat, screenshot, atau commit **dianggap bocor**: cabut lewat
`/revoke` di BotFather, buat token baru, ulangi langkah 2.

### 6.5 Bila bot diam — tabel diagnosis

| Gejala | Penyebab paling mungkin | Perbaikan |
|---|---|---|
| Tidak ada balasan sama sekali | token salah / bot belum di-`/start` | cek `SDB_TG_BOT_TOKEN`, kirim `/start` |
| Balasan hanya "SDB_TG_BOT_TOKEN / SDB_TG_CHAT_ID belum diset" | env tidak dimuat | `source ~/.config/sdb/control.env`, atau jalankan lewat unit |
| Bot menjawab orang lain tapi bukan Anda | `SDB_TG_CHAT_ID` bukan chat ID Anda | ulangi langkah 4, perbarui nilai |
| Jawaban `/revenue` bilang DB tidak ada | `data/control.db` belum pernah dibuat di PC ini | `make control-plane` sekali, atau arahkan `SDB_DB_PATH` |
| Balasan berhenti tiap malam | PC mati/sleep (bukan bug) | lihat §6.3 — butuh VPS untuk 24/7 |
| `409 Conflict` di log | bot yang sama jalan dua tempat (PC + VPS) | hentikan salah satu; satu token = satu poller |

### 6.6 Menjalankan

```bash
source ~/.config/sdb/control.env
cd ~/super-dev-builders
python3 scripts/sdb_tg_bot.py          # mode polling (berhenti: Ctrl-C)
python3 scripts/sdb_tg_bot.py --once   # tarik update sekali, proses, keluar (cocok cron/timer)
```

Untuk mode PC-in-the-loop yang rapi: unit `systemd --user sdb-tg-bot.service` — dibuat bersamaan
hari ini, start dengan `systemctl --user start sdb-tg-bot`.

---

## 7. Shortcut apps di PC ini

Yang **sudah ada sebelumnya** (tidak disentuh): `sdb-command-deck.desktop` (Chrome app-mode ke :8484).

Yang **ditambahkan hari ini**:

| Peluncur | Fungsi | Berkas |
|---|---|---|
| **SDB Tutorial** | buka HTML tutorial utama di browser | `sdb-tutorial.desktop` |
| **SDB Tutorial Pribadi** | buka dokumen ini | `sdb-tutorial-personal.desktop` |
| **SDB Health** | jalankan `sdb-health` (terminal) | `sdb-health.desktop` |
| Handler `sdb://deck` | buka deck dari browser/CLI mana pun | `sdb-url.desktop` + x-scheme-handler |

Semua di `~/.local/share/applications/`, tanpa hak admin. Contoh isi:

```ini
[Desktop Entry]
Type=Application
Name=SDB Tutorial Pribadi
Exec=google-chrome --new-window file:///home/anashadi/super-dev-builders/docs/TUTORIAL_PRIBADI.html
Icon=text-html
Terminal=false
Categories=Development;
```

Pemasangan ulang kapan saja (idempoten, tanpa hak admin):

```bash
bash scripts/install_shortcuts.sh
update-desktop-database ~/.local/share/applications/   # sudah dipanggil skrip
xdg-mime query default x-scheme-handler/sdb            # harus: sdb-url.desktop
```

Helper CLI yang ikut dipasang: `sdb-deck` (buka deck), `sdb-health` (PONG 10 profil), `sdb-open`
(pembuka `sdb://`). Semuanya mode `700`; tidak ada yang berjalan sebagai root.

---

## 8. Dua bahaya utama dan pagar masing-masing

1. **Kunci admin bocor** — orang lain bisa mengubah saldo, menagih sembarangan, suspend tenant.
   Pagar: kunci acak ≥ 24 karakter, mode `600`, tidak pernah masuk chat/git/laporan; bila ragu →
   rotasi (buat kunci baru, cabut lama).
2. **Salah paham arsitektur** — mengira Command Deck adalah mesin penagihan, atau mengira PC ini
   server 24/7. Pagar: dokumen ini §1 dan §6.3; produk berbayar jalan di server, bukan di PC kantor.

---

## 9. FAQ

**Q: Kenapa bot read-only, bukan bisa order juga?**
Karena WhatsApp/Telegram bukan tempat yang tepat untuk aksi menulis uang: tidak ada audit trail
kuat, mudah salah kirim, dan memperluas permukaan serangan. Baca = aman; tulis = tetap lewat
control plane + git.

**Q: Bot baca `data/control.db` langsung — aman?**
Aman: koneksi dibuka `mode=ro` — SQLite menolak tulisan secara fisik. Tidak ada skenario di mana
bot mengubah data.

**Q: Bisakah bot dikirim perintah tulis oleh orang yang punya akses HP saya?**
Bisa saja secara fisik, tapi tetap ditolak: chat ID diverifikasi dan perintah tulis memang tidak
pernah diimplementasi. Lapisan kedua: kunci admin tidak pernah dikirim ke bot.

**Q: Control plane hidup atau tidak saat bot jalan?**
Bot tidak tergantung padanya — bot baca DB langsung. Control plane hidup hanya menambah data
"segarnya" jawaban (mis. metrik). Deck dan timer kesehatan berjalan sendiri.

**Q: Kalau mau upgrade ke VPS nanti?**
Jalankan `scripts/sdb_tg_bot.py` yang sama di VPS; arahkan `SDB_DB_PATH` ke salinan DB atau SSH
tunnel ke PC. Tidak ada perubahan kode.

---

*Dokumen ini bagian dari ekosistem SDB v0.7.2. Bila perilaku sistem berbeda dari tulisan di sini,
yang benar adalah kode dan tesnya.*
