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
Kode acuan: `pm/environments.py` (`selected_venv`, `_recorded_venv`, `committed_venv`, `ACTIVATION_INPUTS`).

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
`build:ink` wajib lebih dulu: 77 file uji `ui-tui` gagal collect (**pre-existing**, bukan regresi bump) karena `packages/hermes-ink/dist/entry-exports.js` belum dibundel.

Patch: `~/backups/sdb-hardening-20261005_full/hermes-agent-npm-20261005.patch`
sha256 `e36df7d1db8dec6cb14beb9cd177458b630f57f77e65c1d559a0a06ecfd6847d`.
`ui-tui/packages/hermes-ink/dist/` ditambahkan ke `.git/info/exclude` (artefak build lokal, bukan tracked).
