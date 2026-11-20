# C2-B2M — Restricted Builder Execution Pack (A″)

**Status:** `PROPOSED — BELUM DIEKSEKUSI`. Tidak ada user, group, ACL, `chown`, atau
unit systemd yang dibuat/diubah oleh dokumen ini.
**Keputusan Owner:** D1 — A″ disetujui sebagai *target design*; eksekusi OS ditahan.
**Skrip pendamping:** `docs/c2b2m/preflight.sh`, `apply.sh`, `verify.sh`, `rollback.sh`
(sudah lolos `bash -n`, belum pernah dijalankan).

## 1. Fakta host yang diukur (bukan asumsi)

| Objek | Nilai terukur | Konsekuensi desain |
|---|---|---|
| `/home/anashadi` | `drwxr-x--- anashadi:anashadi` | Builder TIDAK bisa menembus home Owner → tidak perlu ACL sama sekali |
| `~/.hermes`, `~/.ssh` | `drwx------` | Rahasia sudah tertutup bagi user lain; lapisan kedua tetap dipasang |
| `~/super-dev-builders` | `drwxrwxr-x` (grup bisa tulis) | Builder DILARANG masuk grup `anashadi`, kalau tidak ia bisa menulis repo Owner |
| `/var/run/docker.sock` | `srw-rw---- root:docker` | Builder DILARANG masuk grup `docker` (setara root) |
| grup `sudo`, `docker`, `lxd` | semuanya memuat `anashadi` | Tiga jalur eskalasi ini harus kosong untuk builder |
| `/etc/sudoers.d` | hanya `README` | Tidak ada aturan tersembunyi yang perlu dibersihkan |

Karena home Owner sudah `0750`, pendekatan **workspace terpisah** (`/srv/sdb-workspace`)
dipilih dan **tidak ada ACL rekursif** yang diterapkan ke home atau repo — persis
larangan di §3 direktif.

## 2. Desain identitas

```text
user    sdbbuild   UID otomatis (>=1000), shell /bin/bash, home /home/sdbbuild (0750)
group   sdbbuild   (grup utama, tanpa anggota lain)
tambahan: TIDAK ADA. Dilarang: sudo, adm, docker, lxd, plugdev, disk, systemd-journal
workspace /srv/sdb-workspace          owner sdbbuild:sdbbuild, 0750
  ├── repo/       git clone (bukan symlink ke home Owner)
  └── out/        artefak hasil build untuk diambil Owner
systemd  tidak ada unit builder. Builder tidak boleh menyentuh `systemctl --user`
         milik Owner; itu dijaga oleh kepemilikan unit di ~/.config/systemd/user
         (0700) + tidak adanya polkit rule untuk sdbbuild.
secret   TIDAK ada salinan kredensial Hermes. Builder tidak punya direktori config
         Hermes; pemanggilan model dilakukan oleh Owner, bukan oleh builder.
```

Alasan `/bin/bash` (bukan `nologin`): builder harus menjalankan `pytest`, `git`,
`python` di workspace. Batasnya bukan shell, melainkan UID/GID, grup, dan filesystem.

## 3. Matriks verifikasi (semua memakai canary sintetis)

| # | Uji | Perintah | Hasil yang diminta |
|---|---|---|---|
| 1 | Identitas terbatas | `id -u sdbbuild` / `id -nG sdbbuild` | UID ≥ 1000; grup tepat `sdbbuild` |
| 2 | Tanpa sudo | `sudo -l -U sdbbuild` | "not allowed to run sudo" |
| 3 | Tanpa docker | `id -nG sdbbuild \| grep -w docker` | kosong + socket tidak terbaca |
| 4 | Tanpa LXD | `id -nG sdbbuild \| grep -w lxd` | kosong |
| 5 | Tidak baca rahasia Owner | `test -r /home/anashadi/.hermes` sebagai sdbbuild | `Permission denied` |
| 6 | Tidak baca canary kunci | `cat /home/anashadi/.sdb-canary/fake_key.pem` | `Permission denied` |
| 7 | Tidak tulis repo Owner | `touch /home/anashadi/super-dev-builders/.probe` | `Permission denied` |
| 8 | Tidak ubah systemd Owner | `systemctl --user restart hermes` sebagai sdbbuild | gagal (tidak ada bus user) |
| 9 | Bisa kerja di workspace | `pytest -q` + `git status` di `/srv/sdb-workspace/repo` | jalan, UID sama di subprocess |
| 10 | Identitas subprocess | `python -c "import os;print(os.getuid())"` | sama dengan UID sdbbuild |

Canary dibuat oleh `apply.sh` sebagai berkas **palsu** (`fake_key.pem` berisi string
`CANARY-SINTETIS-JANGAN-DIPAKAI`, `fake_token.txt` serupa) dengan mode `0600`. Tidak
ada berkas rahasia asli yang dibaca, disalin, atau di-hash oleh skrip mana pun.

## 4. Prosedur (setelah approval)

```bash
# 1. preflight — hanya membaca, tidak mengubah apa pun
docs/c2b2m/preflight.sh

# 2. apply — butuh dua kunci eksplisit, default-nya menolak
SDB_B2M_APPLY=1 SDB_B2M_CONFIRM="SETUJU-B2M" docs/c2b2m/apply.sh

# 3. verify — 10 uji di §3, keluar != 0 bila satu pun gagal
docs/c2b2m/verify.sh

# 4. rollback — idempoten, aman dijalankan walau apply gagal separuh
SDB_B2M_APPLY=1 SDB_B2M_CONFIRM="SETUJU-B2M" docs/c2b2m/rollback.sh
```

Rollback menghapus: user + home `sdbbuild`, workspace `/srv/sdb-workspace`, canary
`/home/anashadi/.sdb-canary`. Rollback **tidak** menyentuh repo Owner, `runs/`,
konfigurasi Hermes, unit systemd, maupun hak akses Owner.

## 5. Yang tetap dilarang setelah pack ini disetujui

- Menaruh kredensial Hermes/LLM di home builder (dilarang mutlak; §3 poin 7).
- Memberi builder grup `anashadi`, `docker`, `lxd`, `sudo`, `disk`.
- ACL rekursif ke `/home/anashadi` atau ke repo.
- `sudo` tanpa password untuk perintah apa pun.
- Menjalankan `apply.sh` tanpa `SDB_B2M_APPLY=1` **dan** `SDB_B2M_CONFIRM` yang cocok.

## 6. Risiko bila dieksekusi

| Risiko | Dampak | Mitigasi di pack |
|---|---|---|
| Builder butuh dependensi yang hanya ada di venv Owner | Build gagal, bukan bocor | venv sendiri di `/srv/sdb-workspace/repo/.venv`; tidak memakai `.venv` Owner |
| `git clone` menyalin riwayat berisi artefak profil Chromium | Data non-rahasia ikut tersalin | Terdokumentasi di laporan §7; tidak ada kredensial (audit: kunci publik + MAC) |
| Builder menulis ke `runs/` produksi | Artefak bukti rusak | Clone terpisah; `runs/` hanya ada di repo Owner |
| Escalation via kernel/`.so` lokal | Di luar cakupan akun | Dicatat sebagai batas: bukan sandbox, hanya pembatasan identitas |
