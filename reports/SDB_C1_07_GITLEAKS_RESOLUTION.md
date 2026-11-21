# SDB C1-07 — Historical Secret Findings Resolution

**Mode:** CHANGE_ONLY · **Baseline:** `9266f08b` (C1-06, SHA penuh: `git rev-parse 9266f08b`)
**Tanggal:** 2026-11-22 · **Status gate:** PASS (lihat §5)

---

## 0. Verdict

10 temuan Gitleaks historis **bukan delta**: semuanya pre-existing (commit 2026-10-29/30) dan
sudah dinilai "pre-existing" sejak C1-06. Penyebab selisih C1-05 (0) vs C1-06 (10) **bukan**
perbedaan scanner, versi, konfigurasi, atau rentang commit — melainkan **flag `--baseline-path`**:
C1-05 memakai baseline, C1-06 memakai `make secrets` tanpa baseline.

Ke-10 temuan diklasifikasi ulang satu per satu dengan bukti struktural (bukan asumsi):
**10/10 CONFIRMED_FALSE_POSITIVE**, masing-masing dengan justifikasi berbeda. Exception yang
diterapkan: **2 fingerprint** di `.gitleaksignore` (bukan 10 baris, karena fingerprint Gitleaks
berbutir `commit:file:rule:line` dan 9 temuan berada di satu baris JSON satu-baris).
Tidak ada allowlist rule/path/regex baru, `generic-api-key` tetap aktif, history tidak ditulis ulang.

---

## 1. STEP 1 — Rekonsiliasi scan (akar masalah)

| Dimensi | C1-05 (`5df139f`, 21 Nov 12:09) | C1-06 (`9266f08`, 22 Nov 05:00) | C1-07 (verifikasi ulang) |
|---|---|---|---|
| Binary Gitleaks | 8.28.0 | 8.28.0 | 8.28.0 — `sha256` binary lokal = binary di dalam tarball rilis terpin |
| Digest tarball rilis | `a65b5253…a840eb` (dipin di CI) | idem | `a65b5253…a840eb` — **cocok** (`sha256sum -c` OK) |
| Perintah | `gitleaks detect --config .gitleaks.toml … --baseline-path .github/gitleaks-baseline.json --log-opts="--all"` | `make secrets` → `gitleaks detect --config .gitleaks.toml --log-opts="--all"` (**tanpa baseline**) | keduanya dijalankan ulang |
| Konfigurasi efektif | `.gitleaks.toml` (2 allowlist path-anchored, keduanya tidak menyentuh 10 temuan) | sama | sama (SHA berkas tidak berubah) |
| Rentang | `--all` = 197 commit | `--all` | `--all` = 202 commit (5 commit C1-06), 11,73 MB |
| Cakupan | riwayat penuh (bukan current-file) | riwayat penuh | riwayat penuh |
| Exit code | 0, 0 temuan | 1, 10 temuan | 1 / 10 (tanpa exception) → 0 / 0 (dengan exception) |
| Baseline | **aktif** (10 entri, semuanya `generic-api-key`) | **tidak aktif** | dibuktikan: selisih 10→0 hanya karena baseline/exception |

**Root cause (1 kalimat):** baseline `0654937` (2026-11-20 08:46, ancestor C1-05 `5df139f`)
sudah memuat tepat 10 temuan itu, sehingga pemindaian C1-05 yang memakai `--baseline-path`
melaporkan 0; C1-06 menjalankan `make secrets` yang **tidak** memakai baseline sehingga 10
temuan historis yang sama muncul kembali. Keduanya memindai data yang identik.

**Bukti bahwa exception = satu-satunya pembeda (bukan scanner rusak):** clone bersih tanpa
`.gitleaksignore` → **10 temuan**; clone yang sama + `.gitleaksignore` → **0 temuan**. Angka
10/0 itu dipakai sebagai asersi tes otomatis (§4, tes 6).

Catatan: `--gitleaks-ignore-path` **tidak** bisa dipakai untuk "mematikan" `.gitleaksignore`
root repo (diuji: hasil tetap 0), jadi kontrol negatif dilakukan lewat clone tanpa berkas itu.

---

## 2. STEP 2 — Klasifikasi 10 temuan

Semua nilai sensitif di-redact (`REDACTED`) oleh `--redact`; klasifikasi memakai **bukti
struktural** (jalur JSON, panjang, kelas karakter, relasi antar-field), bukan isi nilai.

### Commit `72eec21b` — `$HOME/.local/share/sdb-deck/profile/Default/Preferences` (9 temuan, line 1)

Berkas ini dump profil Chromium dalam **satu baris JSON**, sehingga 9 match berbagi satu baris.

| # | Jalur JSON | Bentuk nilai | Mengapa bukan rahasia | Klasifikasi |
|---|---|---|---|---|
| 1 | `extensions.settings.fignfif…kcf.manifest.key` | str 392 (base64) | `manifest.key` = **public key** manifest extension (dipakai menurunkan ID extension), publik by design | CONFIRMED_FALSE_POSITIVE |
| 2 | `extensions.settings.mhjfbmdgcfjbbpaeojofohoefgiehjai.manifest.key` | str 216 (base64) | idem (public key) | CONFIRMED_FALSE_POSITIVE |
| 3 | `extensions.settings.nkeimhogjdpnpccoofpliimaahmaaome.manifest.key` | str 216 (base64) | idem (public key) | CONFIRMED_FALSE_POSITIVE |
| 4 | `protection.macs.extensions.settings.fignfif…kcf` | hex 64 (256-bit) | `protection.macs` = **penyimpanan MAC/HMAC** preferensi Chrome; nilainya digest | CONFIRMED_FALSE_POSITIVE |
| 5 | `protection.macs.extensions.settings.ghbmnnjooekpmoecnnnilnnbdlolhkhi` | hex 64 (256-bit) | idem (HMAC) | CONFIRMED_FALSE_POSITIVE |
| 6 | `media_router.receiver_id_hash_token` | str 88 (base64) | **hash** receiver id (nama field sendiri: `…_hash_token`) | CONFIRMED_FALSE_POSITIVE |
| 7 | `protection.macs.enterprise_signin.policy_recovery_token` | hex 64 (256-bit) | berada di **`protection.macs`** → digest HMAC dari preferensi, bukan token asli | CONFIRMED_FALSE_POSITIVE |
| 8 | `protection.macs.enterprise_signin.policy_recovery_token_encrypted_hash` | str 68 (base64) | field berakhiran `_encrypted_hash` di dalam `protection.macs` → digest | CONFIRMED_FALSE_POSITIVE |
| 9 | `safebrowsing.hash_real_time_ohttp_key` | str 60 (base64) | **hash** kunci OHTTP (nama field: `hash_…`) | CONFIRMED_FALSE_POSITIVE |

Bukti pendukung bahwa `protection.macs` memang wadah digest: seluruh anak `protection.macs`
berisi preferensi ter-hash (`account_values`, `browser`, `default_search_provider_data`,
`enterprise_signin`, `extensions`, `google`, `homepage`, `homepage_encrypted_hash`), dan kelima
entri `protection.macs.extensions.settings.*` bernilai hex 64 (256-bit).

### Commit `223dc4c4` — `integrations/replica-skill-baseline.json` (1 temuan, line 19)

| # | Jalur | Bentuk nilai | Mengapa bukan rahasia | Klasifikasi |
|---|---|---|---|---|
| 10 | `"replica-design/tokens.json": "<sha256>"` | hex 64 | Nilainya **SHA-256 digest berkas** `integrations/replica-skill/replica-design/tokens.json`; sudah dihitung ulang dengan `hashlib.sha256` → **identik**. Rule terpicu karena *nama kunci* memuat "tokens". | CONFIRMED_FALSE_POSITIVE |

**Rekap klasifikasi:** CONFIRMED_FALSE_POSITIVE = **10** · POTENTIAL_SECRET = **0** ·
UNKNOWN = **0**. Tidak ada pemanggilan ke penyedia eksternal untuk menguji validitas kredensial.

---

## 3. STEP 3 — Exception yang diterapkan (persis)

Berkas baru `.gitleaksignore`, tepat 2 baris (format resmi Gitleaks `<commit>:<file>:<rule>:<line>`):

| # | Commit | Path | Rule | Line |
|---|---|---|---|---|
| 1 | `72eec21b…` | `$HOME/.local/share/sdb-deck/profile/Default/Preferences` | `generic-api-key` | 1 |
| 2 | `223dc4c4…` | `integrations/replica-skill-baseline.json` | `generic-api-key` | 19 |

SHA 40-hex sengaja **tidak** ditulis utuh di laporan ini: rule `sourcegraph-access-token`
menandai deret 40-hex sebagai calon token (kelas false positive yang sama dengan 37 temuan
SHA-1 di §5), dan laporan ini ikut dipindai riwayat. Nilai 40-hex penuh ada di `.gitleaksignore`
(tes 2 menjaga kesetaraannya dengan baseline CI).

Mengapa 2 baris, bukan 10:

1. Granularitas fingerprint Gitleaks adalah `commit:file:rule:line`; 9 temuan berada pada
   **baris 1** dari berkas JSON satu-baris di **satu commit**, jadi secara mekanis hanya ada 2
   fingerprint unik (10 temuan → 2 fingerprint; dibuktikan tes 2 & 6).
2. Setiap baris **terikat commit**: secret baru pada commit lain, atau pada baris lain, akan
   menghasilkan fingerprint berbeda dan **tetap dilaporkan** (dibuktikan tes 7).
3. Berkas `Preferences` sudah **tidak ada** di HEAD (dihapus di commit lain), sehingga tidak ada
   jalur penambahan rahasia baru pada commit tersebut.

Yang **tidak** dilakukan: tidak ada `[[allowlists]]` baru, tidak ada penonaktifan
`generic-api-key`, tidak ada suppress per direktori, tidak ada `--exit-code 0`, tidak ada
penulisan ulang history, baseline CI tidak diubah.

---

## 4. STEP 4 — Negative security test

`tests/test_c1_07_secret_exceptions.py` — **9 tes, semua lulus** (`.venv/bin/python -m pytest tests/test_c1_07_secret_exceptions.py -q` → `9 passed`).

| Tes | Membuktikan |
|---|---|
| 1 `test_ignore_entries_are_fingerprint_scoped` | tepat 2 fingerprint, unik, tanpa wildcard, rule disebut persis sekali |
| 2 `test_ignore_matches_ci_baseline_exactly` | himpunan fingerprint `.gitleaksignore` **identik** dengan baseline CI (anti-drift dua sumber) |
| 3 `test_exceptions_target_real_commits_and_lines` | setiap fingerprint menunjuk commit yang ada, path yang ada di commit itu, dan baris yang valid |
| 4 `test_new_synthetic_secret_with_same_rule_is_detected` | secret sintetis baru **tetap** terdeteksi `generic-api-key` (rule hidup) |
| 5 `test_exception_is_commit_scoped_not_path_wide` | exception per-fingerprint bekerja (0 temuan), lalu **temuan baru di file yang sama** (commit & baris berbeda) tetap dilaporkan |
| 6 `test_historical_findings_map_to_exceptions_and_scan_is_clean` | clone riwayat penuh **tanpa** exception = tepat 10 temuan dan himpunan fingerprint-nya **identik** dengan 2 fingerprint; **dengan** exception = ke-10 temuan historis hilang |
| 7 `test_config_has_no_broad_allowlist` | semua allowlist path-anchored (`…$`), tidak menutupi berkas yang dikecualikan, wajib punya justifikasi, tanpa `targetRules` |
| 8 `test_make_secrets_scans_full_history` | `make secrets` tetap memindai seluruh riwayat (`--all`) dengan config, bukan hanya current files |
| 9 `test_scanner_failure_fails_closed` | config rusak → Gitleaks exit ≠ 0; langkah CI memuat `set -euo pipefail`, cek `command -v gitleaks`, `test -s reports/ci/gitleaks.json`, `--baseline-path` |

---

## 5. STEP 5 — Gate final

| Gate | Perintah | Hasil |
|---|---|---|
| Tes kebijakan rahasia (fokus) | `.venv/bin/python -m pytest tests/test_c1_07_secret_exceptions.py -q` | **9 passed** |
| Pemindaian riwayat terkonfigurasi | `make secrets` | **no leaks found** (202 commit, 11,73 MB, exit 0) |
| Pemindaian riwayat + baseline CI | `gitleaks … --baseline-path .github/gitleaks-baseline.json --log-opts="--all"` | **0 temuan**, exit 0 |
| Kontrol negatif (tanpa exception) | clone + scan tanpa `.gitleaksignore` | **10 temuan** (audited) — membuktikan deteksi tidak dilemahkan |
| Pemindaian riwayat pasca-commit (HEAD C1-07) | `gitleaks … --log-opts="--all"` tanpa baseline | **0 temuan**, exit 0 — termasuk berkas baru C1-07 itu sendiri |
| Pemindaian raw (pembanding audit) | `make secrets-raw` | **38 temuan** di luar filter: 37 `sourcegraph-access-token` (SHA-1 commit di `reports/upgrade-evidence/thirdparty-scan-github-mcp-server.json`, sudah ber-allowlist terdokumentasi) + 1 `generic-api-key` fixture `tests/test_scripts.py` (allowlist fixture terdokumentasi) |
| Hygiene | `make hygiene` | **PASS** (0 FAIL, 3 WARN pre-existing: 3 berkas >512 KB) |
| D6/D8 delta review | review manual diff (2 berkas baru + 1 laporan) | lihat §7 |
| `make check` | `make check` (log: `/tmp/c107_make_check_final.log`) | **PASS, rc=0** — ruff `All checks passed!` · skill drift `136/136 OK` · `registry_lint: PASS` · `hygiene: PASS` (608 berkas, 0 FAIL, 3 WARN pre-existing) · `pack: PASS` (9/9) · `docs_lint: PASS` (62 md, 43 custom skill) · pytest **944 tes** lulus |

Tidak ada gate wajib yang merah. `PRODUCTION_TRUST` tetap **BLOCKED** (tidak ada klaim produksi).

---

## 6. Risiko residual (jujur)

1. **10 temuan tetap ada di history yang sudah dipublikasikan.** Tidak ditulis ulang (sesuai
   instruksi). Isinya non-kredensial, tetapi berkasnya adalah **dump profil browser pribadi**
   (ID extension, preferensi, hash receiver media-router). Bila repo suatu saat dibuka publik,
   ini masalah **privasi**, bukan kebocoran kredensial. Tindakan bila perlu: `git filter-repo`
   **hanya** dengan approval Owner terpisah.
2. **Exception baris-1 mencakup seluruh match `generic-api-key` pada blob itu** di commit
   `72eec21b` — tidak terhindarkan karena berkasnya satu baris. Aman karena terikat commit dan
   berkas sudah tidak ada di HEAD; dijaga tes 5 & 6.
3. **Dua sumber kebenaran** (baseline CI + `.gitleaksignore`) berpotensi drift. Ditutup tes 2
   (kesetaraan himpunan) — bila baseline diperbarui tanpa `.gitleaksignore`, tes merah.
4. **`make secrets` di workstation** tetap `exit 0` bila gitleaks tidak terpasang (kenyamanan
   lokal). Gate otoritatif adalah CI, yang **fail-closed** (tes 9).
5. **Berkas tak terlacak** `reports/SDB_NEW_SESSION_CONTINUATION_RESULT.md` memuat SHA-1 commit
   40-hex yang memicu `sourcegraph-access-token` pada scan raw. Belum di-commit (tidak masuk
   history), tetapi **jangan** `git add -A` tanpa meninjaunya. `state/gitleaks-raw.json`
   (di-gitignore) menyimpan hasil raw yang sudah ter-redact.
6. **Berkas baru ikut dipindai.** Percobaan commit pertama membuat gate merah (2 temuan) karena
   (a) berkas uji memuat literal secret sintetis ber-entropy tinggi, dan (b) laporan memuat
   SHA 40-hex yang ditandai `sourcegraph-access-token`. Perbaikan: nilai sintetis dibuat saat
   runtime (`base64(sha256(...))`) dan SHA di laporan ditulis 8 karakter. Pelajaran: berkas tes
   dan laporan adalah bagian dari permukaan pindai — jangan pernah menaruh literal ber-entropy
   tinggi atau SHA utuh di sana.
7. **Catatan forensik:** upaya awal mencetak konteks temuan memakai offset kolom yang salah,
   sehingga potongan field **non-kredensial** (public key, hash) sempat tampil di transkrip agen.
   Tidak ada nilai kredensial yang tercetak; klasifikasi final memakai jalur JSON + bentuk nilai,
   bukan isi nilai.

---

## 7. D6/D8 delta review (self-review sebelum commit)

| Berkas | Sifat | Penilaian |
|---|---|---|
| `.gitleaksignore` (baru) | konfigurasi, 2 fingerprint + komentar justifikasi | tidak menonaktifkan rule/berkas/direktori; terikat commit+baris; komentar menjelaskan bukti |
| `tests/test_c1_07_secret_exceptions.py` (baru) | tes keamanan (9) | hermetik (clone lokal + repo sintetis), skip bila binary absen, tanpa rahasia asli di dalam berkas |
| `reports/SDB_C1_07_GITLEAKS_RESOLUTION.md` (baru) | laporan | tanpa nilai sensitif (semua redact) |

Tidak ada perubahan kode produk, tidak ada perubahan `workflows/`, `registry/`, `.gitleaks.toml`,
atau `.github/gitleaks-baseline.json`.

---

## 8. Commit

Satu commit lokal untuk C1-07. SHA commit **tidak** ditulis di dalam berkas ini karena laporan
ikut di-commit — sebuah commit tidak dapat memuat SHA-nya sendiri secara sah. SHA final dicatat
pada respons penutupan dan dapat dibaca ulang dengan:

```bash
git log -1 --format='%H %s'
```

Kebijakan yang dipertahankan: `SDB_DONE_POLICY=attested` · `SDB_EVIDENCE_MODE=legacy` ·
`PRODUCTION_TRUST=BLOCKED`. Tidak ada push/merge/deploy/rewrite history.
