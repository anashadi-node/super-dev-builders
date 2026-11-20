# C2-B2M — Restricted Builder Execution Pack (A″)

**Status:** `READY_FOR_OWNER_APPROVAL — BELUM DIEKSEKUSI`. Tidak ada user, group, ACL,
`chown`, atau unit systemd yang dibuat/diubah oleh dokumen ini. Kesiapan berarti pack
dapat dieksekusi apa adanya setelah approval, bukan bahwa OS sudah diubah.
**Keputusan Owner:** D1 — A″ disetujui sebagai *target design*; eksekusi OS ditahan.
**Skrip pendamping:** `docs/c2b2m/preflight.sh`, `apply.sh`, `verify.sh`, `rollback.sh`.
Bukti yang benar-benar dijalankan hari ini: `bash -n` keempat berkas = OK; `preflight.sh`
= exit 0 (`HASIL: PASS`); `apply.sh` dan `rollback.sh` tanpa dua kunci = exit 2 (menolak).
`apply.sh`/`verify.sh`/`rollback.sh` **belum pernah** dijalankan terhadap sistem.

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

Tambahan uji 11–16 menutup empat celah yang sebelumnya hanya dinarasikan:
11 bisa kerja di workspace, 12 identitas subprocess, 13 skills salinan sendiri
(`/srv/sdb-workspace/skills`, bukan `~/.hermes`), 14 tidak baca workspace proyek lain,
15 tidak tulis `/etc/systemd/system`, 16 proses pekerja mewarisi UID builder.

Canary dibuat oleh `apply.sh` sebagai berkas **palsu** (`fake_key.pem` berisi string
`CANARY-SINTETIS-JANGAN-DIPAKAI`, `fake_token.txt` serupa) dengan mode `0600`. Tidak
ada berkas rahasia asli yang dibaca, disalin, atau di-hash oleh skrip mana pun.

## 3b. Peta butir validasi direktif §7 → bukti di pack

| Butir §7 | Bagaimana pack memenuhi | Status |
|---|---|---|
| Isolasi akun & grup | `apply.sh` membuat grup/user khusus; `verify.sh` 01–04 | siap (belum dieksekusi) |
| Akses persis yang dibutuhkan builder | workspace `/srv/sdb-workspace/{repo,skills,out,venv}`; `verify.sh` 11 | siap |
| Akses ke skills & tools bersama | **salinan** `$SRC_REPO/skills` (bukan symlink ke `~/.hermes`); `verify.sh` 13 | siap, menunggu keputusan (lihat §7) |
| Menjalankan proses builder terbatas | seluruh proses via `sudo -u sdbbuild`; `verify.sh` 12 & 16 | siap |
| Perlindungan kredensial Owner | home Owner `0750`, `~/.hermes` `0700`, canary `0600`; `verify.sh` 05–07 | siap |
| Perlindungan workspace proyek lain | `verify.sh` 14 (probe `~/vsb`) | siap |
| Perlindungan service systemd | `verify.sh` 15 + tidak ada unit builder | siap |
| Pemulihan bila builder gagal | `rollback.sh` idempoten (aman pada apply separuh jalan) | siap |
| Rollback tanpa menghapus data pengguna lain | `userdel --remove` hanya `sdbbuild`; `groupdel` bila grup kosong; tidak menyentuh home Owner | siap |
| Definisi "nama profil terbatas ≠ eksekusi terbatas" | klaim dibuktikan lewat UID/GID nyata (12 & 16), bukan nama | siap |
| Canary sintetis saja | `fake_key.pem`/`fake_token.txt` berisi string penanda, bukan kredensial | siap |

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
| Builder butuh dependensi yang hanya ada di venv Owner | Build gagal, bukan bocor | venv sendiri di `/srv/sdb-workspace/venv` (dibuat `apply.sh`); `.venv` Owner tidak terbaca dan tidak dipakai |
| `git clone` menyalin riwayat berisi artefak profil Chromium | Data non-rahasia ikut tersalin | Terdokumentasi di laporan §7; tidak ada kredensial (audit: kunci publik + MAC) |
| Builder menulis ke `runs/` produksi | Artefak bukti rusak | Clone terpisah; `runs/` hanya ada di repo Owner |
| Escalation via kernel/`.so` lokal | Di luar cakupan akun | Dicatat sebagai batas: bukan sandbox, hanya pembatasan identitas |

## 7. Dua keputusan Owner yang tersisa sebelum `apply.sh` dijalankan

1. **Kebijakan skills builder** — pack memilih *salinan* `skills/` ke `/srv/sdb-workspace/skills`
   (bukan akses ke `~/.hermes/skills`, yang akan membuka profil Owner). Konsekuensi: skills
   builder tidak otomatis ikut terbarui saat repo Owner berubah; sinkronisasi ulang harus
   dijalankan manual (`cp -a`). Alternatif: symlink baca-saja ke satu subdirektori skills —
   ditolak default karena memperluas permukaan baca ke pohon profil Owner.
2. **Cara kerja proses builder** — pack hanya menyediakan jalur eksekusi manual
   (`sudo -u sdbbuild`). Bila `sdb_build_worker.py` akan dijalankan sebagai builder, dibutuhkan
   keputusan: unit systemd `sdbbuild.service`, cron, atau supervisor Hermes. Belum dibuat;
   `verify.sh` 16 hanya membuktikan proses anak mewarisi UID.
