# Runbook — Rotasi Kredensial Control Plane

Berlaku untuk `SDB_ADMIN_KEY` dan `SDB_WORKER_KEY` di `~/.config/sdb/control.env`.
Aturan keras: **nilai kredensial tidak pernah ditulis ke chat, log, dokumen, atau git.**
Yang boleh disebut hanya nama kunci dan panjangnya.

## 1. Siapa yang memegang kunci

| Unit systemd | `EnvironmentFile` | Memakai kunci? |
|---|---|---|
| `sdb-control-plane` | `%h/.config/sdb/control.env` | ya (penerbit otoritas) |
| `sdb-build-worker` | `%h/.config/sdb/control.env` | tidak (kerja lewat Telegram), tetap ikut restart agar env tidak basi |
| `sdb-tg-bot` | `%h/.config/sdb/control.env` | tidak untuk admin key (baca DB read-only), tetap ikut restart |
| `sdb-report-4h` | `%h/.config/sdb/control.env` | tidak, dibaca saat unit dijalankan |

Konsekuensi: setelah berkas env berganti, **setiap unit yang memuatnya harus direstart**,
kalau tidak proses lama tetap memegang nilai lama di memori.

## 2. Prosedur (satu perintah, terkendali)

```bash
cd ~/super-dev-builders

# 1) lihat rencana tanpa mengubah apa pun
python3 scripts/rotate_control_keys.py --dry-run

# 2) rotasi + restart + buktikan kunci lama mati
python3 scripts/rotate_control_keys.py \
  --restart sdb-control-plane --restart sdb-build-worker --restart sdb-tg-bot \
  --verify-url http://127.0.0.1:8088/v1/admin/revenue --verify-header X-Admin-Key \
  --verify-url http://127.0.0.1:8088/v1/worker/claim --verify-header X-Worker-Key \
  --verify-method POST --verify-body '{"worker_id":"rotate-check"}'
```

Skrip: mencadangkan env ke `control.env.bak-<stamp>` (0600), menulis nilai baru
atomik (tmp 0600 → `os.replace`), merestart unit, lalu menguji matriks
**baru → 2xx** dan **lama → 401**. Exit ≠ 0 bila salah satu tidak terpenuhi.

## 3. Verifikasi manual (bila skrip tidak dipakai)

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8088/healthz
curl -s -o /dev/null -w '%{http_code}\n' -H "X-Admin-Key: $SDB_ADMIN_KEY" \
  http://127.0.0.1:8088/v1/admin/revenue
curl -s -o /dev/null -w '%{http_code}\n' -H "X-Worker-Key: $SDB_WORKER_KEY" \
  -X POST -H 'Content-Type: application/json' -d '{"worker_id":"cek"}' \
  http://127.0.0.1:8088/v1/worker/claim
systemctl --user show sdb-control-plane -p ActiveState -p NRestarts
```

Yang wajib terbaca: `healthz=200`, admin/worker dengan kunci **baru** = 200,
kunci **lama** = 401, `NRestarts=0`.

## 4. Bukti rotasi 2026-11-05

| Uji | Hasil |
|---|---|
| `/healthz` | 200 |
| `/v1/admin/revenue` kunci baru / lama | 200 / 401 |
| `/v1/worker/claim` kunci baru / lama | 200 / 401 |
| kunci admin dipakai sebagai worker key | 401 |
| nilai kunci baru/lama di jurnal 30 menit | 0 kemunculan |
| nilai kunci di berkas terlacak git | 0 kemunculan |
| mode env + cadangan | 0600 |
| stabilitas 20 s | `active`, `NRestarts=0` |

## 5. Rollback

```bash
cp ~/.config/sdb/control.env.bak-<stamp> ~/.config/sdb/control.env
chmod 600 ~/.config/sdb/control.env
systemctl --user restart sdb-control-plane
```

Rollback hanya untuk keadaan darurat: nilai lama kembali sah, jadi catat alasannya.

## 6. Yang TIDAK bisa dirotasi otomatis

`SDB_TG_BOT_TOKEN` — penerbitnya BotFather. Prosedur: `/revoke` di BotFather → token baru
→ tulis ke env (0600) → `systemctl --user restart sdb-tg-bot` → kirim satu perintah uji
di chat. Rotasi token Telegram **tidak** boleh dilakukan lewat skrip ini.
