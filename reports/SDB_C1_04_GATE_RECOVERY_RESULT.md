# SDB C1-04 — Gate Recovery & Safe Sandbox Validation

Tanggal: 2026-11-21 · Mode: BROWNFIELD_RECOVERY → CHANGE_ONLY · Cabang: `feat/c2b2g-ci-hardening`

## Verdict (independen)

| Verdict | Nilai | Alasan satu baris |
|---|---|---|
| CI_GATE | **BLOCKED** | Temuan gitleaks ada di berkas terkini **dan** di riwayat (commit `278f13a`). Gerbang memindai riwayat, jadi memperbaiki working tree saja tidak meloloskannya. Butuh keputusan Owner. |
| FIXTURES | **BLOCKED** (`FIXTURE_REPRODUCIBILITY_BLOCKED`) | Drift toolchain sejak 2026-11-17 + `desktop-mini` bergantung pada direktori kerja. |
| OFFLINE_SANDBOX | **BLOCKED** | Isolasi S3–S7 terbukti. Start Hermes dalam konfigurasi produksi gagal 6/6 (S1). |
| LIVE_HERMES | NOT_STARTED | Tidak ada pemanggilan LLM. |
| INDEPENDENT_ACCEPTANCE | BLOCKED | Tidak ada delta kode untuk direview; gerbang belum hijau. |

`SDB_DONE_POLICY=attested`, `SDB_EVIDENCE_MODE=legacy` tidak diubah. Tidak ada kapabilitas baru dimulai.

## 1. HEAD aktual

`d3b8e1fc4b8666ffb0ca07e694fd882999dccf22` (C1-03). `d3b8e1f` adalah HEAD itu sendiri (ancestor: ya).
`git status`: hanya `reports/SDB_NEW_SESSION_CONTINUATION_RESULT.md` (untracked, tidak disentuh).
20 commit lokal di depan `origin/master`; **0 cabang remote** memuat `278f13a` (belum dipublikasikan). Commit `278f13a` dan `d3b8e1f` berstatus tanda tangan `N` (tidak bertanda tangan).

## 2. CR-01 — Akar masalah gitleaks

| Pertanyaan | Bukti terukur |
|---|---|
| Perintah gerbang | `gitleaks detect --config .gitleaks.toml --redact --baseline-path .github/gitleaks-baseline.json --log-opts=--all` (`tests/test_ci_workflow_policy.py:187-259`, "195 commits scanned") |
| Cakupan | **Seluruh riwayat Git**, bukan berkas terkini |
| Temuan | 2 × `generic-api-key`, `tests/test_be_sp03_contract.py` baris 52 dan 591, keduanya commit `278f13a` |
| Berkas terkini | `--no-git` pada working tree memuat 58 temuan; **hanya 2 berkas yang dilacak git**: `tests/test_be_sp03_contract.py` baris 52 dan 591 (sama dengan riwayat). Sisanya berasal dari berkas tak dilacak/di-ignore (`state/`, `runs/`, `.sdb-run/`, `__pycache__`, 1 laporan untracked) dan **bukan bagian gerbang** (gerbang memakai `--log-opts=--all`: 2 temuan). |
| Asal | Commit `278f13a`; `d3b8e1f` tidak mengubah baris itu |
| Sintetis? | Indikasi kuat, bukan bukti mutlak: panjang 25–30 karakter (syarat `Store.add_api_key` ≥ 24), dipakai sebagai kunci tes, dan **0 kecocokan** di 28 berkas (`~/.hermes/.env`, `.env` semua profil, `secrets/*`; nilai tidak dicetak). Tidak diuji terhadap penyedia eksternal. |
| Literal sejenis lain | Hanya 2 yang ditandai; literal lain tidak memicu aturan |
| Cukupkah memperbaiki working tree? | **Tidak.** Simulasi di klon scratch (S-A): perbaikan ditumpuk di atas HEAD → gerbang tetap rc=1, 2 temuan di `278f13a` |

Dua tes merah: `test_gerbang_rahasia_lulus_dengan_scanner_asli` (`:193`) dan `test_ratchet_menolak_kebocoran_baru` (`:259`, "isi laporan tak terduga").

**Koreksi tidak diterapkan ke repo** (sesuai §3: temuan bertahan di riwayat → STOP, tidak ada rewrite atau pengecualian otomatis). Perbaikan berkas terkini saja menghapus temuan berkas terkini tetapi gerbang tetap merah.

### Bukti perbaikan yang sudah divalidasi di scratch (tidak dalam repo)

Perbaikan runtime (`_synthetic_key(label)` = `"syn-" + sha256(...)[:28]`, tanpa literal berbentuk key; semua asersi negatif dipertahankan):

| Skenario (klon scratch) | Hasil |
|---|---|
| Berkas hasil perbaikan: `tests/test_be_sp03_contract.py` | pytest lulus, ruff lulus |
| S-A: perbaikan di atas HEAD, gerbang `--log-opts=--all` | rc=1, 2 temuan di `278f13a` (gagal) |
| S-B: `278f13a` ditulis ulang dengan perbaikan + `d3b8e1f` di-cherry-pick, ref tunggal, gerbang `--all` | **rc=0, 0 temuan** |
| Pohon S-B vs `d3b8e1f` | beda hanya `tests/test_be_sp03_contract.py` (+18/−10) |

Artefak: `runs/capability/c1-04/` (di-gitignore): `option_A_test_fix.patch`, `test_be_sp03_contract.fixed.py`, `gate_*.redacted.json`, `smoke.py`, `smoke.json`.

## 3. Keputusan Owner untuk CR-01 (butuh persetujuan terpisah)

| | A. Perbaikan sempit atas commit belum dipublikasikan | B. Pengecualian false-positive sempit | C. Perbaikan di atas HEAD saja |
|---|---|---|---|
| Aksi | Tulis ulang `278f13a` + anak-anaknya (`d3b8e1f`) di cabang lokal, terapkan patch A | Tambah 2 fingerprint ke `.github/gitleaks-baseline.json` (10 entri sekarang) | Commit patch A di atas HEAD |
| Berkas | `tests/test_be_sp03_contract.py` + riwayat 2 commit | `.github/gitleaks-baseline.json` (dilindungi CODEOWNERS) | `tests/test_be_sp03_contract.py` |
| Meloloskan gerbang? | **Ya** (terbukti S-B, rc=0) | Kemungkinan ya, **belum diuji** | **Tidak** (terbukti S-A, rc=1) |
| Dampak keamanan | Riwayat bersih; nilai sintetis masih ada di reflog sampai `gc` | Mengakui temuan; ratchet melemah 2 entri | Nilai tetap di riwayat |
| Tanda tangan | Dampak nol: kedua commit tidak bertanda tangan | Nol | Nol |
| Reproducibility | SHA `278f13a`/`d3b8e1f` berubah; referensi di laporan C1-02/C1-03 harus dipetakan | SHA tetap | SHA tetap |

**Rekomendasi: A** — satu-satunya opsi yang terbukti meloloskan gerbang tanpa melemahkan aturan. Syarat: persetujuan eksplisit, karena menulis ulang riwayat. Opsi C tidak dianjurkan (terbukti tidak cukup).

## 4. CR-02 — Diagnosis fixture (hanya baca; golden hash tidak diubah)

Revisi sumber: `scripts/build_fixtures.py` dan `fixtures/` bersih terhadap HEAD `d3b8e1f`.

| Pengukuran | Hasil |
|---|---|
| `make fixtures-verify` (rc=2) | `android-mini` 0283a739… vs stamp eb0e943b…; `desktop-mini` 34f94b55… vs 6853475d… |
| Toolchain saat stamp dibuat (dari `.comment` artefak tersimpan) | GCC 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1) |
| Toolchain sekarang | `gcc` 15.2.0, `gcc-13` 13.4.0, binutils 2.46, libc6 2.43 |
| Perubahan paket (`/var/log/dpkg.log`) | 2026-11-17 07:07–07:36: libc6 2.39→2.43, binutils 2.42→2.46, gcc-13 13.3→13.4, `gcc` 4:13→4:15 |
| `android-mini`, build ulang 3× pada 3 cwd + dir tmp berbeda | digest identik (0283a739…) → **deterministik** pada toolchain sama |
| `android-mini` dengan `gcc-13` 13.4.0 | ad5736ac… (≠ stamp) → drift antar-versi GCC |
| `desktop-mini` pada 3 cwd (gcc 15) | 13f828fa…, fb455c01…, 34f94b55… → **bergantung cwd** (`DW_AT_comp_dir` tertanam; artefak tersimpan memuat `/home/anashadi/super-dev-builders`) |
| `desktop-mini` dengan `gcc-13` 13.4.0 | 969f40b8… (≠ stamp 6853475d…) |
| Korupsi artefak? | Tidak: set anggota APK sama, hanya `lib/x86_64/libmini.so` berbeda (15136 vs 15128 byte) |

**Kesimpulan:** penyebab = **toolchain drift** (utama, kedua fixture) + **ketergantungan path** (khusus `desktop-mini`). Bukan korupsi, bukan drift sumber. **Keterbatasan:** GCC 13.3.0 asli tidak terpasang, jadi pembuatan ulang persis stamp lama tidak dapat dibuktikan di host ini.

**Usulan perubahan terkecil (belum diterapkan, butuh persetujuan):** (1) `build_fixtures.py` menambah `-ffile-prefix-map=<dir>=.` dan cwd tetap; (2) catat versi toolchain di stamp dan verifikasi gagal-tertutup bila beda; (3) setelah toolchain dipin (kontainer/versi), Owner menyetujui regenerasi golden hash. Tidak ada regenerasi dijalankan.

## 5. CR-03 — Smoke sandbox offline (STARTUP_PREFLIGHT saja)

Konfigurasi: argv produksi `_sandbox_base` (allowlist mount namespace), profil sintetis kosong (`config.yaml` saja, **tanpa `auth.json`**), HOME sintetis, `--unshare-net` (menghapus `--share-net`), tanpa panggilan model.
Kontrol: konfigurasi sama dengan `--share-net`, supaya probe terbukti peka.

| Cek | Terisolasi | Kontrol (share-net) |
|---|---|---|
| S3 path host terlindungi terlihat (docker.sock, /run, /root, ~/.ssh, repo, profil lain, dst.) | **0 dari 23** | 0 |
| S4 `auth.json`/`.env` runtime tak kosong/env mirip rahasia/canary host terbaca | **tidak ada** | tidak ada |
| S5 connect abstract-unix host | **gagal** (0 socket abstrak terlihat) | **berhasil** (20 terlihat) |
| S5 connect loopback host | **gagal**, antarmuka hanya `lo` | **berhasil**, 13 antarmuka |
| S6 anak proses (`sh -c`, `setsid`) | `0 0 0 0` (mewarisi pembatasan) | `1 1 0 0` |
| S7 tulis `/usr`, runtime Hermes | ditolak (errno 30, read-only) | ditolak |
| S7 tulis `$HOME`, `/etc`, `/tmp`, profil | berhasil **di tmpfs namespace** | sama |
| S7 efek di host | **tidak ada** berkas, `git status` identik, daftar profil identik, runtime identik | — |
| S8 galat start | terbatas: 88 byte, 0,07 dtk, rc=1 | — |

**S1 (executable terselesaikan, start):**

| Konfigurasi | Hasil |
|---|---|
| `HERMES_HOME` = profil sintetis (bentuk produksi), 6 kali | **rc=1, 6/6**: `no dependency environment is committed for this install; run hermes pm repair` |
| `HERMES_HOME` tidak diset, atau `/tmp/hh` | rc=0, `Hermes Agent v0.23.2`, Python 3.14.9 |

Penyebab S1 **belum ditentukan**. Fakta pendukung: ada `~/.hermes/.hermes-update-in-progress.lock` (tanggal 2026-10-08) dan proses `hermes` lain berjalan; runtime memeriksa lingkungan dependensi yang sudah di-commit. Percobaan di host (di luar sandbox) bertentangan dengan sandbox (HERMES_HOME tak ada gagal di host, lolos di sandbox), jadi ini mungkin tergantung keadaan update. Tidak dicoba mengakali isolasi, tidak dijalankan `hermes pm repair` (mengubah instalasi).

Preflight versi **bukan** invokasi Hermes live yang berhasil.

## 6. Gerbang

| Gerbang | Perintah | Hasil |
|---|---|---|
| G0 | `ruff` (via `make check`) | lulus |
| G1/G3 | `make test` (tes CI policy + gitleaks) | **gagal**: 2 tes, akibat temuan riwayat di §2 |
| G2 | `tests/test_be_sp03_contract.py` pada berkas perbaikan (scratch) | lulus |
| G4 | D6/D8 delta | **tidak dijalankan**: tidak ada delta kode (hanya laporan + indeks); reviewer tidak dipanggil |
| G5 | `make -k check` pada kondisi saat ini | **rc=2** (`make test`; `fixtures-verify` terpisah rc=2). `hygiene`: PASS (0 FAIL, 3 WARN); `packs` OK |

`make check` akhir yang hijau **tidak mungkin** dicapai tanpa keputusan Owner di §3. Satu-satunya `make check` yang dijalankan adalah baseline; tidak ada suite penuh duplikat.

## 7. Komit

Hanya laporan ini dan satu baris `docs/INDEX.md`. Tidak ada koreksi tes, karena gerbang tidak bisa hijau lewat working tree. SHA komit dicatat di balasan.

## 8. Blocker keamanan tersisa

1. Gerbang rahasia merah di riwayat `278f13a` (2 temuan sintetis).
2. Fixture tidak reproducible (drift toolchain + path-dependence).
3. Start Hermes di sandbox bentuk-produksi gagal; live belum teruji.
4. M-1/M-2/M-3 dari C1-03 serta egress jaringan belum difilter (di luar scope C1-04).
5. Token/biaya: NOT_MEASURED (tidak ada telemetri provider).

## 9. Keputusan Owner berikutnya

**Setujui salah satu:** (A) tulis ulang `278f13a`+`d3b8e1f` lokal dengan patch sintetis yang sudah divalidasi (rekomendasi), atau (B) pengecualian baseline 2 fingerprint. Lalu **setujui terpisah** perubahan `build_fixtures.py` + pin toolchain sebelum golden hash diperbarui, dan izinkan diagnosis S1 (cek `hermes pm repair` pada salinan, bukan instalasi aktif).
