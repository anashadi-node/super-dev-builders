# GETTING STARTED — Super Dev Builders

Panduan ini ditulis supaya siapa pun bisa mulai dari **nol** sampai bisa memakai
ekosistem ini sendiri. Bahasa sederhana, urut dari A sampai Z.

Acuan arsitektur (sumber kebenaran): `docs/00_MASTER_BLUEPRINT_V2.2.html`.

---

## Daftar Isi

1. [Apa ini, dalam satu paragraf](#1-apa-ini-dalam-satu-paragraf)
2. [Konsep dasar: 4 kata yang harus dipahami dulu](#2-konsep-dasar-4-kata-yang-harus-dipahami-dulu)
3. [Prasyarat](#3-prasyarat)
4. [Langkah 1 — Periksa kapabilitas host (read-only)](#langkah-1--periksa-kapabilitas-host-read-only)
5. [Langkah 2 — Pasang (dry-run dulu, selalu)](#langkah-2--pasang-dry-run-dulu-selalu)
6. [Langkah 3 — Verifikasi pemasangan](#langkah-3--verifikasi-pemasangan)
7. [Langkah 4 — Buat target baru](#langkah-4--buat-target-baru)
8. [Langkah 5 — Jalankan Gate #0 (otorisasi)](#langkah-5--jalankan-gate-0-otorisasi)
9. [Langkah 6 — Jalankan workflow 16 tahap](#langkah-6--jalankan-workflow-16-tahap)
10. [Langkah 7 — Release gate](#langkah-7--release-gate)
11. [Referensi CLI `sdb` (17 perintah)](#referensi-cli-sdb-17-perintah)
12. [Referensi target `make`](#referensi-target-make)
13. [Struktur direktori: apa yang ada di mana](#struktur-direktori-apa-yang-ada-di-mana)
14. [Tujuh aturan yang tidak bisa dinegosiasikan](#tujuh-aturan-yang-tidak-bisa-dinegosiasikan)
15. [Pemecahan masalah (troubleshooting)](#pemecahan-masalah-troubleshooting)
16. [Copot pemasangan](#copot-pemasangan)
17. [Pertanyaan yang sering muncul](#pertanyaan-yang-sering-muncul)

---

## 1. Apa ini, dalam satu paragraf

Super Dev Builders adalah **ekosistem kerja software engineering berbasis Hermes**
untuk merancang, membangun, menguji, mengaudit, mengamankan, mendokumentasikan,
dan men-deploy website / web app / mobile / desktop / backend / API / database /
integrasi AI-agent — **termasuk Authorized Reverse Engineering & Reconstruction**
(membangun ulang sistem yang Anda punya izin penuh untuk bangun ulang).

Intinya: setiap langkah kerja punya **bukti deterministik**, dan setiap keputusan
"lulus/gagal" diambil oleh **gate berbasis bukti**, bukan berdasarkan perasaan LLM.

---

## 2. Konsep dasar: 4 kata yang harus dipahami dulu

| Kata | Arti sederhana | Analogi |
|---|---|---|
| **Agent** | Divisi yang punya tanggung jawab & batas izin sendiri | Departemen di sebuah perusahaan |
| **Skill** | SOP / prosedur kerja yang dimuat hanya saat relevan | Buku manual kerja |
| **Tool** | Alat yang menghasilkan bukti nyata (compiler, test runner, scanner, Playwright) | Mesin ukur di pabrik |
| **Gate** | Keputusan PASS / FAIL / BLOCKED berdasarkan bukti | Pintu pemeriksaan kualitas |

Divisi di sini **lazy / on-demand** — tidak pernah dijalankan serentak. Divisi
hanya dipisah kalau memang perlu batas izin atau konteks berbeda.

### Divisi yang tersedia

| Profil | Fokus |
|---|---|
| `sdb-orchestrator` | Koordinasi, klarifikasi, keputusan jalur kerja |
| `sdb-recon` | Rekognisi & pengumpulan evidence (dengan izin) |
| `sdb-architect` | Arsitektur, ADR, rencana implementasi |
| `sdb-builder` | Implementasi front-end / back-end |
| `sdb-reviewer` | Code review, QA, integrasi, E2E |
| `sdb-security` | SAST, dependency, secret scanning, audit |
| `sdb-devops` | Deploy, observability, smoke test, rollback |

---

## 3. Prasyarat

| Kebutuhan | Versi / catatan | Cara cek |
|---|---|---|
| Python | 3.11+ (repo diuji pada 3.11.16 & 3.12.3) | `python3 --version` |
| PyYAML | wajib (dipakai membaca registry) | `python3 -c "import yaml"` |
| Git | 2.x | `git --version` |
| Hermes | untuk pemasangan skill ke profil | `ls ~/.hermes` |
| Playwright | hanya bila menjalankan capture web | `python3 -c "import playwright"` |

Kalau `PyYAML` belum ada:

```bash
python3 -m pip install pyyaml     # atau:  uv pip install pyyaml
```

---

## Langkah 1 — Periksa kapabilitas host (read-only)

Ini **tidak mengubah apa pun**. Fungsinya memberi tahu Anda alat apa yang tersedia
di komputer ini, dan apakah skill yang terpasang masih sinkron dengan repo.

```bash
cd ~/super-dev-builders
make doctor
# atau:  python3 scripts/doctor.py
```

Yang dilaporkan:

- keberadaan tool (git, ruff, pytest, trivy, semgrep, playwright, …)
- **skill drift** — perbandingan skill di repo vs skill yang sudah terpasang di profil
- pin dependency (aturan #6: pihak ketiga harus dipin ke revisi tertentu)

Contoh keluaran sehat:

```text
skill drift: 106/106 OK, 0 bermasalah
```

Kalau ada baris `WARN` soal `tools.yaml[...] tanpa version_pin`, itu **peringatan
kebijakan**, bukan kerusakan: artinya tool tersebut belum dipin revisinya.

---

## Langkah 2 — Pasang (dry-run dulu, selalu)

**Aturan besi: installer selalu mulai dengan DRY-RUN.** Tidak ada yang berubah di
komputer Anda kecuali Anda menambahkan `--apply`.

```bash
cd ~/super-dev-builders
./install.sh                    # DRY-RUN — hanya menampilkan rencana
```

Anda akan melihat tiga bagian:

1. **Pemetaan skill → profil**, dibaca langsung dari `registry/skills.yaml`
2. **Rencana perintah `sdb`** (shim yang akan ditulis ke `~/.local/bin/sdb`)
3. **Langkah berikutnya**

Kalau rencananya sudah sesuai, baru terapkan:

```bash
./install.sh --apply              # pasang skill + perintah sdb
./install.sh --apply --no-cli     # hanya skill, tanpa perintah sdb
./install.sh --apply --main-only  # hanya namespace utama ~/.hermes/skills
```

Apa yang dilakukan installer saat `--apply`:

1. **Back-up dulu** ke `~/.hermes/backups/super-dev-builders-<stempel-waktu>/`
   — termasuk shim `sdb` lama bila ada. Tidak ada penimpaan tanpa cadangan.
2. Memasang 37 skill custom ke profil yang relevan (mengikuti registry).
3. Menulis shim `~/.local/bin/sdb`.

Installer **fail-closed**: kalau bukan root repo yang benar, atau PyYAML tidak ada,
ia berhenti dengan pesan jelas — bukan jalan setengah-setengah.

> **Jumlah skill per profil** (dibaca dari `registry/skills.yaml`, 37 skill custom):
> `sdb-builder` 18 · `sdb-devops` 11 · `sdb-architect` 9 · `sdb-security` 9 ·
> `sdb-recon` 8 · `sdb-orchestrator` 7 · `sdb-reviewer` 7.
> Sebuah skill bisa masuk beberapa profil sekaligus, jadi totalnya melebihi 37.

---

## Langkah 3 — Verifikasi pemasangan

Setelah `--apply`, pastikan dua hal:

```bash
# 1. Perintah sdb bisa dipanggil
sdb list

# 2. Skill terpasang dan sinkron dengan repo
sdb doctor
```

Kalau `sdb: command not found`, tambahkan `~/.local/bin` ke PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
# permanen: tambahkan baris di atas ke ~/.bashrc
```

Verifikasi cepat bahwa shim menunjuk ke repo yang benar:

```bash
head -5 ~/.local/bin/sdb
```

---

## Langkah 4 — Buat target baru

"Target" = satu pekerjaan / satu sistem yang sedang Anda kerjakan. Setiap target
punya ruang kerjanya sendiri.

```bash
sdb init nama-target-saya
# sama dengan: python3 scripts/init_target.py nama-target-saya
```

Perintah ini membuat struktur kerja per target:

```text
evidence/<target>/       # evidence mentah (WAJIB sudah diredaksi)
normalized/<target>/     # evidence yang sudah dinormalisasi ke JSON
reconstruction/<target>/ # hasil rebuild clean-room
verification/<target>/   # hasil verifikasi visual/behavioral/a11y/security
reports/<target>/        # laporan gate, fidelity, handover
runs/<target>/           # jejak eksekusi
```

Aman dijalankan dua kali (**idempoten**) — tidak akan menimpa data yang sudah ada.

**Aturan nama target:** huruf/angka/`_` di awal, sisanya huruf/angka/`.`/`_`/`-`,
maksimal 64 karakter, **tanpa `/` dan tanpa `..`**. Ini bukan formalitas: nama
target dipakai untuk membentuk jalur direktori, jadi membiarkannya bebas berarti
membuka celah path traversal (CWE-22). Validator ada di `scripts/sdb_common.py`
(`validate_slug`) dan dipakai oleh **semua** skrip pembentuk jalur.

Contoh nama yang sah: `sdb-local-demo`, `target_1`, `_selftest_init`, `x.y-z`.

---

## Langkah 5 — Jalankan Gate #0 (otorisasi)

**Tidak ada deep scan tanpa otorisasi tertulis.** Ini gerbang pertama dan tidak
bisa dilewati.

```bash
sdb gate nama-target-saya
```

Hasilnya salah satu dari tiga:

| Status | Arti | Tindakan |
|---|---|---|
| `PASS` | Manifest otorisasi lengkap & sah | Boleh lanjut ke tahap berikutnya |
| `FAIL` | Ada isi manifest yang tidak sah / kurang | Perbaiki isinya, ulangi |
| `BLOCKED` | Manifest tidak ada atau tidak bisa dibaca | Buat dari template dulu |

Template ada di `templates/`. Contoh manifest nyata untuk referensi:
`evidence/oss-sb-agency/authorization.yaml`.

Status gerbang ditulis ke `reports/<target>/gate0-verdict.json` — jadi keputusan
ini **terekam dan bisa diaudit**, bukan hanya tampil di layar.

---

## Langkah 6 — Jalankan workflow 16 tahap

```bash
sdb workflow nama-target-saya
# atau:  make workflow TARGET=nama-target-saya
```

Runner ini memeriksa **keberadaan artefak nyata** di setiap tahap, lalu
melaporkan mana yang ada dan mana yang belum.

```text
01    USER OBJECTIVE
01A   AUTHORIZATION/SCOPE GATE          tool=gate_check.py
01B   RECON/EVIDENCE PACKAGE
02    ORCHESTRATOR: KLARIFIKASI
03    RESEARCH (bila perlu)
04    ARCHITECTURE + ADR
05    HUMAN DESIGN APPROVAL
06    IMPLEMENTATION PLAN
07    IMPLEMENTASI (FE/BE)
08    CODE REVIEW
09    QA / INTEGRATION / E2E
10    SECURITY (SAST/DEP/SECRET)
11    CODE AUDIT & ASSURANCE
12    RELEASE GATE                      tool=release_check.py
13    HUMAN APPROVAL PRODUKSI
14    DEVOPS DEPLOY
15    OBSERVABILITY/SMOKE/ROLLBACK
16    DOCS + HANDOVER
```

Penting dipahami: runner ini **memeriksa keberadaan, bukan menilai kualitas**.
Baris `MISSING` adalah laporan jujur bahwa tahap itu belum dikerjakan — bukan bug.

Opsi berguna:

```bash
sdb workflow --list-stages              # daftar 18 baris tahap, tanpa menjalankan
sdb workflow nama-target-saya --json    # keluaran mesin-terbaca
sdb workflow nama-target-saya --require-all   # exit non-nol bila ada yang MISSING
```

`--require-all` dipakai ketika runner ini dijadikan gate (harus lengkap), bukan
sekadar laporan.

> Catatan jujur: saat ini **3 dari 19 tahap punya tool deterministik**
> (`gate_check.py`, `did_validate.py`, `release_check.py`). Sisanya masih dijalankan oleh agen /
> manusia. Ini keterbatasan yang diketahui, bukan klaim palsu bahwa semuanya
> sudah otomatis.

---

## Langkah 7 — Release gate

```bash
sdb release nama-target-saya
# atau:  make release-check TARGET=nama-target-saya
```

Gate ini menilai kesiapan rilis berdasarkan **artefak yang benar-benar ada**.
Tanpa bukti build/test/scan yang segar, tidak ada status lulus — sesuai aturan #4.

---

## Referensi CLI `sdb` (17 perintah)

`~/.local/bin/sdb` hanyalah **shim**; isi sebenarnya ada di `scripts/sdb.py`.
CLI ini hanya memetakan nama perintah ke skrip yang tepat dan **meneruskan exit
code** apa adanya. Ia **fail-closed**: perintah tak dikenal atau tanpa argumen
menghasilkan exit `2`, bukan diam-diam sukses.

| Perintah | Fungsi |
|---|---|
| `capture` | Capture terkendali (wajib Gate #0 PASS) |
| `doctor` | Kapabilitas host + drift skill + pin dependency |
| `fidelity` | Bandingkan capture original vs hasil rebuild |
| `fidelity-report` | Laporan fidelity 9 dimensi |
| `gate` | Gate #0 (otorisasi & scope) → PASS/FAIL/BLOCKED |
| `init` | Buat workspace target |
| `install` | Pasang skill + CLI ke host (dry-run default) |
| `inventory` | Inventaris ekosistem |
| `lint` | Evidence lint (metadata, confidence, redaksi) |
| `list-skills` | Daftar / pasang skill ke profil |
| `normalize` | Normalisasi artefak capture → JSON |
| `redact` | Redaksi rahasia pada artefak jaringan |
| `registry-lint` | Validasi registry skill/tool |
| `release` | Release gate berbasis artefak |
| `scan` | Pindai pola eksekusi/eksfiltrasi pihak ketiga |
| `uninstall` | Hapus pemasangan (dry-run default) |
| `workflow` | Runner 16 tahap berbasis bukti |

Semua argumen setelah nama perintah diteruskan apa adanya ke skrip tujuan:

```bash
sdb gate sdb-local-demo
sdb workflow sdb-local-demo
```

---

## Referensi target `make`

| Target | Fungsi |
|---|---|
| `make help` | Daftar target |
| `make doctor` | Kapabilitas host (read-only) |
| `make inventory` | Inventaris ekosistem |
| `make test` | Test suite |
| `make lint` | Lint (ruff) |
| `make lint-registry` | Validasi registry skill/tool |
| `make drift` | Cek skill repo vs terpasang |
| **`make check`** | **Gerbang lokal lengkap**: lint → lint-registry → test → drift |
| `make gate-init` | Menyiapkan Gate #0 |
| `make release-check` | Release gate |
| `make skills-list` | Daftar skill per profil |
| `make workflow` | Runner 16 tahap (`TARGET=` untuk memilih target) |
| `make install-dry-run` | Simulasi pemasangan |
| `make install-main` | Pasang ke namespace utama |
| `make clean-pyc` | Bersihkan `__pycache__` |

**`make check` adalah gerbang lokal wajib sebelum commit.** Ia harus keluar
dengan kode `0`.

---

## Struktur direktori: apa yang ada di mana

```text
docs/            blueprint + arsitektur, divisi, workflow/gate, policy, rollback
registry/        registry skill + tool (sumber, revisi terpin, status)
skills/          sumber kanonik 37 skill custom (dipasang ke profil, tidak disalin liar)
agents/          charter mesin-terbaca per divisi (izin, input/output, batas)
workflows/       definisi gate + tahap workflow (machine-readable)
templates/       template manifest otorisasi, target manifest, ADR, handover
scripts/         deterministik: doctor, inventory, init-target, install-skills, gate-check, release-check, workflow-run, sdb
evidence/        evidence mentah (wajib redacted)   → per target
normalized/      evidence ternormalisasi            → per target
reconstruction/  hasil rebuild clean-room           → per target
verification/    hasil verifikasi visual/behavior/a11y/security → per target
reports/         laporan gate, audit, upgrade, fidelity, handover
tests/           test untuk scripts/ (dijalankan sebelum commit)
```

---

## Tujuh aturan yang tidak bisa dinegosiasikan

Ini disalin apa adanya dari `README.md` — bukan ringkasan, bukan tafsiran:

1. Tidak ada deep scan tanpa `authorization.yaml` berstatus PASS (Gate #0).
2. Tidak ada bypass auth / CAPTCHA / anti-bot / paywall / DRM / licensing / pinning / access control.
3. Tidak ada credential, session token, cookie, atau PII di evidence maupun konteks LLM.
4. Tidak ada klaim "selesai/lulus" tanpa fresh build/test/scan evidence.
5. Security/Audit tidak punya hak deploy produksi. Deploy produksi = approval manusia.
6. Skill/MCP pihak ketiga: source check → pin revisi → scanner → review manual → sandbox → approval.
7. Release = residual risk diketahui, gate lulus, risk owner manusia menerima sisa risiko.

**Prinsip #0** berada di atas semua aturan ini: *Security, Safety & Privacy*
adalah hal paling utama — di atas kecepatan dan kenyamanan. Semua target, repo,
link, dependency, skill, MCP, dan artefak capture diperlakukan **untrusted**
sampai lolos gate.

---

## Pemecahan masalah (troubleshooting)

| Gejala | Sebab | Solusi |
|---|---|---|
| `sdb: command not found` | `~/.local/bin` belum di PATH | `export PATH="$HOME/.local/bin:$PATH"` |
| `FATAL: PyYAML wajib` | PyYAML belum terpasang | `python3 -m pip install pyyaml` |
| `FATAL: registry/skills.yaml tidak ada` | Dijalankan di luar root repo | `cd ~/super-dev-builders` dulu |
| `No module named pytest` | Interpreter tidak punya pytest | pakai `.venv/bin/python -m pytest` atau `make test` |
| `ERROR: slug tidak sah: '...'` | Nama target mengandung `/` atau `..` | pakai nama satu segmen (lihat Langkah 4) |
| `skill drift: ... 0 bermasalah` diikuti `DIFF` | Skill repo ≠ skill terpasang di profil | sinkronkan salinan profil, jalankan `make drift` lagi |
| Gate #0 `BLOCKED` | `authorization.yaml` belum ada | salin dari `templates/`, isi, ulangi `sdb gate` |
| Tahap `MISSING` di workflow | Tahap itu memang belum dikerjakan | kerjakan, atau pakai `--require-all` hanya saat jadi gate |
| Deck berhenti di "Menyiapkan Super Dev Builders Workspace…" | GPU/EGL PC tidak bisa membuat konteks WebGL (sejak 0.7.5 deck otomatis jatuh ke mode 2D + pesan, tidak lagi menggantung) | tutup jendela, buka lagi lewat ikon **SDB Command Deck** (launcher memakai `--enable-unsafe-swiftshader`); kalau tetap 2D, itu batas driver — seluruh fitur selain kantor 3D tetap jalan |
| Dialog "Invalid Permissions on Desktop File" | `.desktop` tanpa bit `x` / tanpa `metadata::trusted` | `bash scripts/sdb-fix-launcher.sh` (juga otomatis tiap hari + tiap `sdb-deck`) |

Perintah diagnosis yang aman dijalankan kapan saja (semuanya read-only):

```bash
sdb doctor
sdb list
sdb workflow --list-stages
make help
```

---

## Copot pemasangan

```bash
cd ~/super-dev-builders
./install.sh --uninstall            # DRY-RUN: tampilkan apa yang akan dihapus
./install.sh --uninstall --apply    # benar-benar copot
```

`uninstall.sh` adalah pembungkus tipis untuk perintah yang sama:

```bash
./uninstall.sh --apply
```

Cadangan Anda tetap tersimpan di `~/.hermes/backups/super-dev-builders-<stempel>/`.

---

## Pertanyaan yang sering muncul

**Apakah installer aman dijalankan tanpa saya periksa dulu?**
Ya — ia DRY-RUN secara default dan tidak menyentuh apa pun sampai Anda menulis
`--apply`. Sebelum menimpa, ia membuat cadangan.

**Apakah repo ini membaca atau menyimpan kredensial?**
Tidak. Installer tegas: *"Tidak membaca/menulis rahasia apa pun. Tidak ada akses
jaringan."* Scanner rahasia hanya menyimpan sidik jari (fingerprint), bukan nilainya.

**Kalau saya tidak jadi memakainya secara komersial?**
Tidak ada masalah. Ekosistem ini berdiri sendiri sebagai alat kerja; tidak ada
langkah pemasangan yang bergantung pada rencana komersialisasi.

**Bagaimana cara tahu skill yang terpasang masih sesuai repo?**
`make drift` (atau `sdb doctor`). Keluaran sehat: `skill drift: N/N OK, 0 bermasalah`.

**Boleh langsung deploy produksi?**
Tidak tanpa dua hal: Gate #0 `PASS` **dan** approval manusia untuk produksi
(aturan #5 dan #7). Deploy adalah keputusan manusia yang menerima sisa risiko.

**Di mana saya melihat perintah apa saja yang tersedia?**
`sdb list` (daftar perintah CLI) dan `make help` (daftar target make).

---

*Terakhir diperbarui: 2026-10-07 · Selaras dengan `docs/00_MASTER_BLUEPRINT_V2.2.html`*