# Ronde-3 — Code Review, QA, Keamanan, Audit Assurance (seluruh ekosistem SDB)

Tanggal: 2026-10-11. Status: **INTERIM — LULUS BERSYARAT** (bukan "100% bersih"; lihat Batas Cakupan).
Cakupan bukti mesin: commit `48d8a94` (HEAD) + snapshot audit `/home/anashadi/.hermes/cache/scratch/sdb-stage11-20261011-110452/repo`.

## Tahap 11 — bukti segar (dijalankan ulang 2026-10-11 ~11:15 WIB)

| Pemeriksaan | Perintah | Hasil |
|---|---|---|
| Test suite | `pytest tests skills -rs` | **246 passed, 3 subtests passed, 11,44s** |
| Gerbang lokal | `make check` (lint+registry+test+drift) | **rc=0** — ruff `All checks passed!`; registry_lint `PASS` **tanpa WARN**; drift `110/110 OK` |
| SAST | `semgrep --config=p/default dashboard scripts skills` (exclude vendor) | **rc=0, 0 error**, 3 WARNING — semuanya ditriase FALSE POSITIVE (lihat T11-4) |
| Rahasia | `gitleaks detect` (riwayat 86 commit, pohon berkas) | **40 hit — TIDAK ADA rahasia nyata** (37 SHA git + 3 fixture uji sintetis; lihat T11-2) |
| Layanan | `systemctl --user is-active sdb-command-deck` | **active**, `ActiveEnterTimestamp` = **2026-10-11 15:01:59 WIB** (restart deploy `9852125`) |
| HTTP live | `/`, `/monitor`, `/api/state` via `192.168.1.9:8484` | **200 / 200 / 200** |
| Kontrol keamanan | 4 uji live read-only (tabel di bawah) | **semua sesuai harapan** |

## Kontrol DIVERIFIKASI LIVE (read-only, 2026-10-11)

| Kontrol | Uji | Hasil | Putusan |
|---|---|---|---|
| D-1 DNS-rebinding | `GET /api/ws/whoami` + `Host: evil.test` | `local=False`, token `null` | **TERBUKTI TERTUTUP** (loopback+Host loopback) |
| D-1 LAN | `GET /api/ws/whoami` via `192.168.1.9` | `local=False`, token `null` | **TERBUKTI TERTUTUP** |
| Auth API | `GET /api/ws/projects` tanpa `X-SDB-Token` | **401** | **TERBUKTI** |
| D-2 path traversal | `/../etc/passwd` / `%2e%2e%2e/...` | **403 / 404** | **TERBUKTI TERTUTUP** |
| D-3 file kode | `/server.py`, `/ws_api.py`, `/dashboard/server.py` | **404** | **TERBUKTI TERTUTUP** (allowlist ekstensi) |
| D-2 artifact | `/api/ws/artifact?project=../../etc&file=passwd` | **401** (auth lebih dulu) | **TERBUKTI** (validasi+auth) |

Dasar kode (dibaca baris demi baris): `dashboard/server.py:215-256` (allowlist ekstensi + `resolve().is_relative_to`),
`dashboard/ws_api.py:467-529` (`handle`: `hmac.compare_digest`, `local` = client loopback **dan** Host loopback,
`pdir()` regex `[a-z0-9][a-z0-9_-]{0,59}`), `ws_api.py:86-105` (`get_token` fail-closed + 0600 via `os.link`).

## Tahap 11b — semgrep seluruh repo, installer, HTTP lanjutan (2026-10-11)

**Semgrep `p/default` SELURUH repo** (exclude `.venv`, `vendor`, `node_modules`, `runs`, `*.min.js`): **rc=0, 0 aturan timeout**, 5 WARNING — **semua ditriase, 0 temuan nyata**:

| # | Aturan | Lokasi | Putusan (bukti baca langsung) |
|---|---|---|---|
| 1–2 | `missing-integrity` | `dashboard/index.html:8`, `dashboard/monitor.html:9` | **FP** — keduanya favicon `href="data:image/svg+xml,..."`; SRI tak bermakna pada `data:` URI |
| 3 | `react-unsanitized-method` | `dashboard/ws/app.js:172` | **FP** — `insertAdjacentHTML` dengan `${esc(p.id)}`/`${esc(p.name)}`; `p.id` = slugify `[a-z0-9-]`, `p.name` = judul `[:60]`; `esc()` menutup `&<>"'` |
| 4 | `contains-bidirectional-characters` | `reports/upgrade-evidence/thirdparty-scan-lighthouse.json:12421` | **FP TERBUKTI** — tepat **1** karakter bidi di seluruh berkas: `U+202C` **di dalam string pesan semgrep** (kutipan nama aturan `...bidi.contains-bidirectional-characters`). Artefak teks, bukan kode. **Menutup pertanyaan terbuka laporan lama.** |
| 5 | `dynamic-urllib-use-detected` | `tests/test_dashboard_security.py:34` | **FP** — `urllib.request.urlopen` pada server uji `127.0.0.1:<port>`; hanya harness tes, bukan kode produksi |

**Celah cakupan semgrep (jujur):** `docs/00_MASTER_BLUEPRINT_V2.2.html` & `reports/LAPORAN_SDB_LENGKAP_20261008.html` **PartialParsing** (HTML gagal diparse, `&` tak ter-escape) → isinya **tidak teranalisis**. Tidak ada aturan yang timeout (klaim lama "5 aturan timeout" sudah tidak berlaku).

**Installer (`install.sh`, `scripts/install_skills.py`, `scripts/bootstrap_tools.sh`):**

| Uji | Hasil |
|---|---|
| `install.sh` | default **DRY-RUN**; back-up sebelum timpa; argumen `%q` (tanpa `eval`); tidak ada `rm -rf` polos; tidak membaca rahasia/jaringan |
| `bootstrap_tools.sh` | tanpa `curl \| sh`; pin versi eksplisit; unduh → **verifikasi SHA256** → `install -m 0755`; `trap EXIT` bersihkan temp |
| **Uji fail-open checksum** (hipotesis saya) | `printf '' \| sha256sum -c -` → **rc=1** ("no properly formatted checksum lines found") **dan** skrip memakai `set -euo pipefail` → **fail-CLOSED. Hipotesis GUGUR** — bukan temuan |
| Kelemahan `install_skills.py` | `skill_id` dari registry **dipakai apa adanya** ke `os.path.join` + `shutil.rmtree` — id `..` bisa menghapus di luar namespace. Input = registry repo (tepercaya & direview) → **Rendah, hardening** (pakai `validate_slug` yang sudah ada) |

**Verifikasi HTTP lanjutan (live, read-only):**

| Uji | Hasil | Catatan |
|---|---|---|
| Header `/`, `/monitor`, `/ws/app.js`, `/style.css` | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Cache-Control: no-store` | **CSP terpasang** (verifikasi ulang 16:05) |
| Header `/api/state` | `Cache-Control` + **`X-Content-Type-Options: nosniff`** | **`nosniff` terpasang** (verifikasi ulang 16:05) |
| Metode | `HEAD` 200; `OPTIONS/PUT/DELETE/PATCH/TRACE` → **501**; `POST /` → **404** | tidak ada verb tak terduga |
| Static terlarang | `/state/health.json` **404**, `/.git/config` **404**, `/ws/`+`/ws` **404** | blokir state & dir terbukti |
| Static diizinkan | `/agents.json` 200, `/vendor/three.module.min.js` 200, `/index.html?x=1` 200, `/app.js` 200 | sesuai allowlist |
| Auth | token salah → **401**, token sah → **200** | token tak pernah dicetak |
| Body | JSON rusak → **400**; 70 KB → **413** | `MAX_BODY` ditegakkan live |

## Temuan dan status (ronde 1–2)

| ID | Sev | Ringkas | Status |
|---|---|---|---|
| D-1 | Sedang | whoami memberi PIN ke `Host: evil.test` (DNS-rebinding) | DITAMBAL + tes + **uji live** |
| D-2 | Sedang | id proyek dari klien tanpa validasi (path traversal) | DITAMBAL + tes + **uji live** |
| D-3 | Sedang | `/server.py`, `/ws_api.py` disajikan HTTP 200 | DITAMBAL + tes + **uji live** |
| D-4 | Rendah | token non-ASCII -> TypeError; Content-Length negatif; token 0664 sesaat | DITAMBAL + tes |
| D-5 | Sedang | `REPO` hard-coded -> CI merah (404) | DITAMBAL |
| T-3 | Sedang | parser YAML fallback tanpa block scalar | DITAMBAL |
| F-01 | Sedang | allowlist Gate #0 `capture_web` pakai startswith | DITAMBAL — kini bandingkan tuple `(scheme, host, port)` hasil `urlparse` (`scripts/capture_web.py:63-78`) |
| F-02..F-10 | Rendah | token kosong fail-open + race, rerun/timpa, config non-dict, race approve, perm berkas, path hard-coded | DITAMBAL |
| F-05 | Rendah | `--host 0.0.0.0`: HTTP tanpa TLS, `/api/state` tanpa PIN | peringatan startup; RISIKO DITERIMA (lihat T11-4) |
| F-09 | Rendah | checksum bootstrap satu sumber dengan aset | trap EXIT ditambah; pin/cosign = RISIKO TERBUKA |

## Temuan BARU / koreksi (Tahap 11)

| ID | Sev | Bukti | Ringkas | Tindakan |
|---|---|---|---|---|
| T11-1 | Rendah | `registry_lint` output | Drift tak memblokir: custom skill **38** vs disetujui Owner **37**; `sdb-command-deck` `version` kosong; `make check` tetap exit 0 | ✅ **SELESAI (Opsi A, Owner)** — `approved_custom_count` 37→38 + catatan bertanggal; metadata `sdb-command-deck` dilengkapi (`version: 1.0.0` dll.); skill dipasang ulang ke `main`+`cc-devops-docs`+`cc-frontend`; `registry_lint` kini **PASS tanpa WARN** |
| T11-2 | Rendah | `gitleaks detect` (86 commit) = 40 hit | **Semua non-rahasia**, terbukti dengan membaca isi yang cocok: 37× `sourcegraph-access-token` = string **SHA git 40-hex** (`pinned_commit`) di `reports/upgrade-evidence/thirdparty-scan-github-mcp-server.json`; 3× `generic-api-key` = **fixture uji sintetis** (2 di salinan `ulang2-clean` yang sudah keluar HEAD, 1 di `tests/test_scripts.py`). Tanpa `.gitleaks.toml` | Tambah allowlist berjustifikasi agar sinyal nyata tidak terkubur noise |
| T11-3 | Rendah | `ws_api.py:519-523` | `artifact` memakai `fp.is_file()` yang **mengikuti symlink**; symlink di `stages/` bisa membaca berkas lain (prasyarat: penulis lokal) | ✅ **DITAMBAL `9852125`** — `resolve()`+`is_relative_to`; uji: symlink→**404**, berkas biasa→**200** |
| T11-4 | Rendah | semgrep 3 WARNING; header respons live | Tanpa **CSP** pada HTML yang disajikan; `/api/state` juga **tanpa `nosniff`**; `--host 0.0.0.0` = HTTP polos di LAN. 3 WARNING semgrep = **FP terbukti** (2× favicon `data:` URI, 1× `esc()`-terlindungi) | ✅ **DITAMBAL `9852125`** — CSP pada semua berkas statis + `nosniff` pada semua respons JSON; render headless: 1 `<canvas>`, `data-err` kosong, **0 pelanggaran CSP**; risiko LAN tetap DITERIMA |
| T11-7 | Rendah | `scripts/install_skills.py:65-84` | `skill_id` dari registry dipakai langsung ke `os.path.join` + `shutil.rmtree` tanpa validasi (id `..` bisa keluar namespace) | ✅ **DITAMBAL `9852125`** — `validate_slug()` fail-closed sebelum `os.path.join`/`rmtree`; uji: 7 id jahat (`..`, `a/b`, `/etc`, `""`, `-x`, `x`*65) semua `skip` |
| T11-5 | Info | `grep /health server.py`; uji live | **`/health` = 404 by design** — bukan rute; kesehatan lewat `--health-check` (tulis `state/health.json`) & `build_state()` | Koreksi catatan lama yang menyebut `/health` sebagai endpoint |
| T11-6 | Info | — | Klaim lama "gitleaks: tidak ada rahasia terlacak" **hanya benar untuk staged/tree**, tidak untuk riwayat | Sudah dikoreksi di T11-2 |
| T11-8 | Rendah | `make lint` = `ruff check scripts tests skills`; `ruff check .` = **20 pelanggaran di 6 berkas** | **`make lint` buta ke `dashboard/`** — padahal di sanalah layanan web berada. Termasuk **3 di `dashboard/server.py`** (I001/E401/F401: `import json, re` + `os` tak terpakai) dan **2 di `dashboard/ws_api.py`** (RUF100: `noqa` tanpa aturan aktif). **Pre-existing, bukan regresi.** Konsekuensi: klaim "ruff All checks passed!" hanya berlaku untuk cakupan gerbang, bukan seluruh repo | **TERBUKA** — perlu keputusan Owner: perluas `make lint` ke `dashboard/` (+rapikan 5 pelanggaran) atau biarkan dengan catatan risiko |
| T11-9 | Sedang (proses) | `ruff` bersih di `48d8a94` → **I001** di `9852125` | Commit `9852125` menyatakan *"PDR 7 langkah … py_compile OK"* tetapi **tidak menjalankan `make lint`**; tambalan T11-7 (menambah `validate_slug` ke daftar import) memecahkan `scripts/install_skills.py` → **`make check` MERAH sejak 15:01:36** | ✅ **DIPERBAIKI** (import dirapikan, gerbang `rc=0`). Aturan proses baru: PDR wajib `make check`, bukan hanya `pytest` + `py_compile` |

## Yang sudah TERBUKTI bekerja (fresh)

- vektor XSS ditutup: `esc()` dipakai konsisten di **semua** sink `innerHTML`/`insertAdjacentHTML` — `dashboard/app.js:11`, `dashboard/ws/app.js:7` (verifikasi grep menyeluruh + baca `app.js` penuh).
- `make check` **exit 0** end-to-end; drift skill **110/110**.
- Sanitasi `ulang2-clean` sukses: direktori **tidak ada di HEAD** (`.gitignore:54`, commit `db75109`) — bukti tersisa hanya di riwayat.
- `install.sh`: default DRY-RUN, back-up sebelum timpa, tanpa `rm -rf`, `%q` untuk path (tanpa `eval`).

## Batas cakupan (jujur)

- **Sumber audit fan-out (5 subagen) GAGAL total** — provider `tokenrouter` rate-limit (HTTP 429) & payload 400; **0 temuan** dihasilkan. Seluruh bukti di laporan ini dikumpulkan langsung (bukan dari subagen).
- `dashboard/vendor/*.js` (three.js) **tidak diaudit** (pihak ketiga, minified) — hanya hash/impor yang diperiksa.
- `ws/world.js` (613 baris), `ws/chars.js`, `ws/toon.js`: diperiksa pola sink + `esc()`, **tidak dibaca baris demi baris**.
- `skills/**`: 9 skrip utama dibaca penuh; 29 sisanya hanya grep pola berisiko.
- `shellcheck` & `bandit` **tidak terpasang** → skrip shell & analisis keamanan Python tidak diperiksa alat khusus.
- `trivy` (vuln dependensi) belum dijalankan ulang pada ronde ini.
- Semgrep **PartialParsing** pada 2 berkas HTML (`docs/00_MASTER_BLUEPRINT_V2.2.html`, `reports/LAPORAN_SDB_LENGKAP_20261008.html`) → isi keduanya tidak teranalisis.
- **Tidak ada klaim "100% bersih".** Putusan: **LULUS BERSYARAT, sisa 3 syarat**: (T11-2) allowlist `.gitleaks.toml` berjustifikasi, (T11-8) putuskan cakupan `make lint` ke `dashboard/`, (F-09) pin/cosign bootstrap.
- **Sudah ditutup:** T11-1 (Opsi A, Owner), T11-3/T11-4/T11-7 (commit `9852125`, terverifikasi live 16:05), T11-9 (regresi gerbang diperbaiki di commit ini — `make check` **rc=0**).

## Bukti penambalan (2026-10-11, commit `9852125`)

| Langkah | Bukti |
|---|---|
| Patch | 7 suntingan di 3 berkas produksi (`dashboard/server.py`, `dashboard/ws_api.py`, `scripts/install_skills.py`) |
| Tes regresi | 6 uji baru: symlink-escape→404, berkas biasa→200, `nosniff` JSON (ws_api + `/api/state`), CSP pada UI, 7 id skill tidak sah ditolak |
| Pre-Deploy Review | secret **BERSIH** (semua hit = prosa/docstring/nama modul, bukan nilai), `shuffle=True` **BERSIH**, `dry_run=False` **BERSIH**, `py_compile` OK, suite **lulus semua** |
| Deploy | `systemctl --user restart sdb-command-deck` → **active**; `/`,`/monitor`,`/api/state`,`/ws/app.js` = **200**; LAN `192.168.1.9` = **200** |
| Verifikasi header live | `/` → CSP + `nosniff`; `/api/state` & `/api/ws/whoami` → `nosniff` |
| Verifikasi UI | headless Chrome: DOM 22,4 KB, **1 `<canvas>`** (kantor 3D jalan), `data-err` **kosong**, log **0 "Refused to"/CSP violation** |
| Kontrol kelayakan CSP | inventaris sumber: semua muatan **same-origin** (`/ws/app.js`, `style.css`, `app.js`, `fetch /api/*`) + `data:` favicon → cocok dengan direktif; **0** `eval`/`new Function`/`WebAssembly`/`Worker` di app maupun vendor |
- Dua pertanyaan terbuka laporan lama kini **tertutup**: karakter bidi di JSON pihak ketiga (FP terbukti, T11b-#4) dan klaim "5 aturan semgrep timeout" (kini 0 timeout, rc=0).
