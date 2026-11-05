# Hardening Venv Hermes (PM-managed) — 2026-10-05

Item #10 `reports/human-approval-required.md` (71 advisory OSV di venv Hermes).
Status: **TUNTAS & TERVERIFIKASI**. Tanpa `sudo`, tanpa `pip` manual, tanpa `--force`.

## 1. Topologi venv (koreksi penting)

`~/.hermes/hermes-agent/venv` dan `.venv` = **legacy in-tree, pra-PM**. PM tidak memakainya.
Venv runtime sesungguhnya direkam di:

```
~/.hermes/installs/<install_key>/facts.json     → packages.venv.environment
install_key = sha256(str(project_root.resolve()))[:16]
untuk /home/anashadi/.hermes/hermes-agent → 8f187687540a47e8
```

Nilai `environment` wajib berada di bawah `installs/<key>/environments/<gen>/venv`.
Kode acuan (repo Hermes, luar SDB): `hermes:pm/environments.py` (`selected_venv`, `_recorded_venv`, `committed_venv`, `ACTIVATION_INPUTS`).

Konsekuensi: **jangan** menyimpulkan hasil upgrade dari inspeksi `hermes-agent/venv` — itu pohon mati.

## 2. Temuan & remediasi

| Paket | Sebelum | Sesudah |
|---|---|---|
| pyjwt | 2.13.0 (1 CRITICAL + 8 HIGH) | **2.15.1** |
| urllib3 | 2.7.0 | **2.8.0** |
| tornado | 6.5.8 | **6.5.10** |
| oauthlib | 3.3.1 | **4.0.0** |
| httpx2 / httpcore2 | 2.7.0 | **2.13.1** |

Mekanisme resmi: pin di `pyproject.toml` + `hermes pm lock` + `hermes pm install` (uv 0.12.3, hash-verified via `uv.lock`).
Kuota 14-hari PM ditembus dengan `[tool.uv.exclude-newer-package]` per paket (timestamp = upload-time PyPI +1 detik, filter strict BEFORE).
Resolver uv (minimal-change) menahan `tornado`/`oauthlib` → dipaksa lewat `override-dependencies` (komentar inline "hapus bila upstream naik sendiri").

## 3. Bukti verifikasi

1. **Lock**: `uv.lock` memuat 6 versi fix di atas.
2. **Venv aktif**: `installs/8f187687540a47e8/environments/61316b9b…/venv/bin/python` → `jwt 2.15.1`, `urllib3 2.8.0`, `tornado 6.5.10`, `oauthlib 4.0.0`; dist-info httpx2/httpcore2 = 2.13.1.
3. **Runtime live**: `/proc/<gateway pid>/maps` memuat `…/environments/61316b9b…/venv/lib/python3.14/site-packages/tornado` → proses gateway benar-benar memakai venv ter-upgrade.
4. **Audit**: `hermes security audit` → 71 → **20 finding**, semuanya `hermes-agent@0.0.0`.
5. **Falsifikasi artefak 0.0.0** (oracle OSV langsung):
   - `query package=hermes-agent@0.0.0` → 20 vuln (mereproduksi artefak)
   - `query …@0.19.0` → 4 vuln
   - `query …@0.21.5` → **0 vuln**
   Versi nyata = `hermes --version` → `v0.21.5+6718.g158fd63` (dist-info editable memaksa `Version: 0.0.0`).

**Kesimpulan**: 51 finding paket nyata ditutup; 20 sisanya artefak metadata, bukan kerentanan nyata pada instalasi ini.

## 4. Rollback & presistensi

- Backup penuh: `~/backups/sdb-hardening-20261005_full/` (379 MB) + `venv-pkgs-before.tar.gz`.
- Patch perubahan (jika perlu di-apply ulang):
  `~/backups/sdb-hardening-20261005_full/hermes-agent-deps-20261005.patch`
  sha256 `249b26293ff3a98923fb9e44c448c561e3c1dbafaa36656545bf378e5703ceb6`.
- Perubahan **sengaja tidak di-commit** di checkout `hermes-agent` (HEAD = upstream tip):
  `hermes update` memakai autostash (`hermes-update-autostash-*`) untuk melindungi patch working-tree,
  sedangkan commit lokal justru memutus jalur `git pull --ff-only`.
- Pasca `hermes update`: jalankan `git status --short` di `~/.hermes/hermes-agent`; bila patch hilang → `git apply` patch di atas, lalu `hermes pm lock && hermes pm install` dan verifikasi ulang langkah §3.2–3.5.

## 5. Perintah verifikasi cepat
```bash
K=8f187687540a47e8
V=$(python3 -c "import json;print(json.load(open('$HOME/.hermes/installs/'+'$K'+'/facts.json'))['packages']['venv']['environment'])")
"$V/bin/python" -c "import jwt,urllib3,tornado,oauthlib;print(jwt.__version__,urllib3.__version__,tornado.version,oauthlib.__version__)"
~/.hermes/hermes-agent/.hermes/bin/hermes --version
ps -eo pid,args | grep -m1 "hermes-agent/.hermes/bin/hermes" | awk '{print $1}' \
  | xargs -I{} grep -o "/installs/[^ ]*site-packages" /proc/{}/maps | sort -u
```

## 6. Hardening 3 workspace npm (item #4 lanjutan) — 2026-10-05

Baseline `npm audit` (pohon yang diperiksa `hermes doctor`): root `--workspaces=false` **2**, `web` **5**, `ui-tui` **4** → **sesudah: 0 / 0 / 0**.

| Paket | Sebelum | Sesudah | Mekanisme |
|---|---|---|---|
| brace-expansion | 5.0.9 | **5.0.12** | `overrides` root |
| js-yaml | 4.3.1 | **4.3.2** | `overrides` root + dep langsung root |
| undici (^7) | 7.29.0 | **7.29.1** | `overrides` root |
| undici (^6, node-gyp/nodejs + ui-tui) | 6.28.0 | **6.28.1** | `overrides` + dep langsung `ui-tui` |
| yaml | 2.8.1 | **2.9.1** | `overrides` root (baru) |
| vitest + @vitest/mocker | 4.1.10 | **4.1.11** | devDep `web` + `ui-tui` |

Catatan mekanika (penting untuk pengulangan):
1. Perbaikan **wajib di root** — repo ini memakai npm workspaces; `npm audit` di dalam `web/`/`ui-tui/` mengukur pohon hoisted yang sama.
2. `.npmrc` repo memakai **`min-release-age=14`** (kuarantina 14 hari, analog PM). Versi yang lebih baru dari 14 hari ditolak (`ETARGET`) kecuali ditambah `min-release-age-exclude[]`; pilih versi fix yang **sudah** melewati kuarantina (undici `6.28.1`, bukan `6.29.0`).
3. `EOVERRIDE` muncul bila paket yang di-override juga dependency langsung — bump keduanya (`js-yaml` root).
4. `npm install` biasa **tidak** selalu me-reify override pada entri lock yang sudah ada → jalankan `npm update <pkg>` untuk memaksa re-resolve (`undici`).
5. `hermes update` menjalankan `npm ci` deterministik dari lockfile, jadi patch ini hidup selama lockfile lokal tetap ada (autostash). **Bila hilang** → `git apply` patch npm di §6.

Bukti uji (bukan sekadar audit):
```bash
npm test --workspace web     # 51 file / 369 tes PASS
npm run build:ink --workspace ui-tui && npm test --workspace ui-tui   # 176 file / 1620 tes PASS (2 skip)
```
`build:ink` wajib lebih dulu: 77 file uji `ui-tui` gagal collect (**pre-existing**, bukan regresi bump) karena `hermes:packages/hermes-ink/dist/entry-exports.js` belum dibundel.

Patch: `~/backups/sdb-hardening-20261005_full/hermes-agent-npm-20261005.patch`
sha256 `e36df7d1db8dec6cb14beb9cd177458b630f57f77e65c1d559a0a06ecfd6847d`.
`ui-tui/packages/hermes-ink/dist/` ditambahkan ke `.git/info/exclude` (artefak build lokal, bukan tracked).

## 7. Sesi lanjutan — token Telegram, plugin, migrasi multiplex, reclaim disk (2026-10-05, pasca-approval Owner)

Semua dijalankan tanpa `--force`, tanpa `sudo`. Gateway di-restart **sekali** (untuk migrasi), bukan untuk npm/config.

### 7.1 Dedupe `TELEGRAM_BOT_TOKEN` (13 profil) — tanpa restart
- Metode berbasis bukti: sha256 nilai token tiap profil dibandingkan milik `default` (`89fcfb04…`) → **13 identik** (persis daftar doctor), 9 profil lain tidak memuat token (cc-*, lokal, villa-agency).
- Aksi: baris `TELEGRAM_BOT_TOKEN=` dihapus dari 13 `.env`; backup per-file mode 600 di `~/backups/sdb-hardening-20261005_full/profiles_env/` (dir 700).
- Skrip idempoten (dry-run default): `~/.hermes/cache/scratch/dedupe_telegram_tokens.py` (`--apply` untuk eksekusi).
- Hasil: salinan secret **14 → 1**.

### 7.2 Plugin `hermes-session-reset-policy` — audit dulu, baru pasang
- Audit kode @ SHA terpin `493df020496d2782d3fe15308cc3b6672c2224c4`: 395 baris, dep runtime **nihil**, satu hook `pre_gateway_dispatch`; grep pola berisiko (`subprocess|socket|requests|urllib|eval|exec|open|environ`) = **0 temuan**.
- `plugins install … --ref <SHA>` (tanpa `--force`); verifikasi `cmp` kode lokal vs kode yang diaudit → **identik** (sha256 `f2a6a662…`); `git rev-parse HEAD` = SHA terpin.
- Status awal **not enabled** (patuh aturan "plugin tidak default aktif") → di-`enable` eksplisit; gateway memuat ulang plugin tanpa restart.

### 7.3 Migrasi multiplex (arsitektur)
`hermes gateway migrate --multiplex` → satu host gateway melayani **23 profil**; unit gagal `hermes-gateway-sodex-cex-monitor.service` dicopot; `gateway.multiplex_profiles: true` tertulis di `config.yaml`; entri hantu systemd dibersihkan (`daemon-reload` + `reset-failed`). Bukti: `systemctl --user is-active` = active; log Telegram "Connected to Telegram (polling mode)".

### 7.4 Reclaim disk 3,0 GB
Dihapus: `state.db.pre-update-emergency-2026-09-29…bak` (1,53 GB) + `…2026-09-30…bak` (1,63 GB) + sidecar `-shm`/`-wal`. **Disimpan**: `…2026-10-03T23-08-47-576Z.bak` (1,9 GB).
Dasar: state.db live memuat 313.027 pesan sejak 2026-08-26 (lebih tua dari kedua backup) → keduanya strict subset.

### 7.5 urllib3 `2.7.0` → `2.8.0`
`~/anantara-sakti/requirements-research-venv.txt` (murni file spec; venv-nya tidak ada di disk → sistem trading live tak tersentuh, tanpa install/restart).

### 7.6 VACUUM state.db — dieksekusi otomatis di jendela offline (2026-10-05)
Temuan verifikasi: pemegang `state.db` = `hermes-gateway.service` **dan** proses `hermes … serve --host 127.0.0.1 --port 0` milik Desktop app (anak app Electron) → VACUUM mustahil dari dalam sesi Desktop. `hermes sessions optimize` menolak dengan aman selama masih ada pemegang; `--force` **dilarang** (menulis ulang store di bawah live writer bisa membuat semua agent menolak turn).
Eksekutor: `scripts/vacuum_state_db_offline.sh` dijalankan sebagai unit systemd user transient `hermes-vacuum-offline` (cgroup terpisah → bertahan saat app ditutup). Watcher menunggu sampai satu-satunya pemegang = gateway, lalu menjalankan:
```bash
systemctl --user stop hermes-gateway
hermes sessions optimize && hermes sessions optimize-storage --yes
systemctl --user start hermes-gateway
```
Sifat: fail-closed (batal + gateway dinyalakan kembali bila masih ada pemegang lain), timeout `VACUUM_WAIT_HOURS` (default 18 jam), log `~/.hermes/logs/state-db-vacuum-*.log`. Batalkan: `systemctl --user stop hermes-vacuum-offline`.
Baseline 2026-10-05: state.db **2,09 GB** + WAL **67 MB**; `freelist` ~0 → ruang yang direklaim bukan dari baris terhapus, melainkan **duplikasi indeks FTS lama** → sasaran utama `optimize-storage` (layout v23), disusul `optimize` (merge segmen FTS5 + VACUUM). Disk bebas 119 GB; preflight v23 butuh ~ukuran file → aman.
Catatan: `sessions.auto_prune` default **sudah True** (retensi 90 hari) → warning doctor soal state.db adalah soal **ukuran**, bukan kebijakan hapus. `auto_archive` **tidak** diaktifkan (tak mengurangi ukuran, hanya soft-hide).

### 7.7 Tidak dilakukan (keputusan sadar)
- rename `cc-*` → `sdb-*` (item #8): alias via `agents/*.yaml` sudah berfungsi; risiko riwayat sesi tanpa manfaat nyata.
- `hermes setup` (API key platform): butuh kredensial Owner.
