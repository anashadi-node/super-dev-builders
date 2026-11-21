# SDB C1-05 — Unblock & Accelerate Result

Tanggal: 2026-11-21 · Mode: BROWNFIELD_RECOVERY → CHANGE_ONLY · Cabang: `feat/c2b2g-ci-hardening`

## Verdict

| Acceptance | Hasil | Bukti ringkas |
|---|---|---|
| `GITLEAKS_HISTORY` | **PASS** | Gitleaks 8.28.0 memindai 197 commit melalui `--log-opts="--all"`; 0 temuan |
| `CI_POLICY_TESTS` | **PASS** | `make check` exit 0; seluruh pytest mencapai 100% |
| `FIXTURE_REPRODUCIBILITY` | **PASS** | Android/Desktop dibangun 3× di scratch berbeda dengan hash identik; tes fixture 10/10 |
| `OFFLINE_SANDBOX` | **PASS_PREFLIGHT** | startup isolated production-shaped exit 0; negative missing-environment exit 1 sesuai harapan |
| `MAKE_CHECK` | **PASS** | lint, registry, pytest, drift 136/136, hygiene, 9 pack, docs-lint lulus |
| `FIXTURES_VERIFY` | **PASS** | kedua hash hasil rebuild identik dengan stamp |
| `SECURITY_DELTA_REVIEW` | **PASS** | D6 PASS; D8 PASS setelah dua correction cycle |
| `UNRELATED_CHANGES` | **PRESERVED** | `reports/SDB_NEW_SESSION_CONTINUATION_RESULT.md` tetap untracked dan tidak disentuh |

Status ini bukan approval merge, deploy, live-model integration, atau independent release acceptance.
`SDB_DONE_POLICY=attested` dan `SDB_EVIDENCE_MODE=legacy` dipertahankan.

## 1. Track A — riwayat lokal diperbaiki

Old HEAD: `f74294512722301578ac8a467b85ad8e46cd673e`

Corrected HEAD sebelum delta fixture: `5df139f1f6576bfe2970faf322e4b00d8aff6907`

| SHA lama | SHA baru |
|---|---|
| `278f13a0d0d41515d0fb5e60778a428e61ab99e1` | `121711bef9773f9ef26370f1f76f3e106cc49005` |
| `d3b8e1fc4b8666ffb0ca07e694fd882999dccf22` | `2d6523b390302019a44307b81542dd84873c182f` |
| `973f57cfb3e2b7856f3c8ac5ec44b9a1df912d40` | `2f39958b519e8595dd49b65e138413121a2aab2b` |
| `f74294512722301578ac8a467b85ad8e46cd673e` | `5df139f1f6576bfe2970faf322e4b00d8aff6907` |

Correction mengganti dua literal key sintetis dengan `_synthetic_key(label)` berbasis SHA-256 runtime.
Tidak ada perubahan rules atau `.github/gitleaks-baseline.json`.

Backup rejected history berada di luar repo:

- bundle: `$TMPDIR/c105/recovery/old-history.bundle`
- SHA-256: `162824e296f4075700966d21cade9907227a427a6459a817363f1a4ac547585e`
- backup bukan Git ref;
- empat SHA rejected di atas tidak dijangkau cabang yang diperiksa;
- exact scan `git log --all` oleh Gitleaks menghasilkan 0 temuan.

Evidence C1-03/C1-04 yang menyebut SHA lama dianggap **STALE untuk identitas revision** dan digantikan oleh tabel mapping ini; klaim fungsionalnya diverifikasi ulang melalui gerbang C1-05.

## 2. Track B — fixture reproducible dan portable

Commit implementasi lokal: `cf57fa0e69680ce1e82e28afd676d151ed032f42`.

Berkas implementasi:

1. `scripts/build_fixtures.py`
2. `tests/test_fixtures.py`
3. `fixtures/android-mini/artifact/android-mini.apk`
4. `fixtures/android-mini/artifact.sha256`
5. `fixtures/desktop-mini/artifact/desktop-mini`
6. `fixtures/desktop-mini/artifact.sha256`

Perubahan yang terbukti:

- compiler `/usr/bin/gcc-13` dan linker `/usr/bin/ld.bfd` beserta versi eksaknya dipin;
- locale, `PATH`, `SOURCE_DATE_EPOCH`, source path, compilation directory, dan build CWD dinormalisasi;
- ordinary mutable CI boleh skip secara terlihat bila pin host tidak tersedia;
- `SDB_REQUIRE_FIXTURE_TOOLCHAIN=1` mengubah toolchain hilang/bergeser menjadi hard failure;
- tiga build pada scratch/CWD berbeda harus menghasilkan hash identik;
- semua ancestor/descendant symlink dan regular-file hardlink yang sudah ada ditolak;
- input ZIP harus regular file dan anggota APK harus persis enam path yang diizinkan.

Hash golden final:

| Fixture | SHA-256 |
|---|---|
| `android-mini.apk` | `ad5736acfacf561691a8efcd2622eb02f9b23e14a5584b38fa181f27eb5844a7` |
| `desktop-mini` | `5b6aa0672da2e69db8dd2d6fad1e597e1194a877a1438a023afb9323ab77acfb` |

Tiga build bersih di `$TMPDIR/c105/fixture-final-2` memiliki hash identik untuk kedua fixture sebelum golden diperbarui. Functional/content/security validator, DID suite, comparison terhadap golden, dan `make fixtures-verify` lulus.

## 3. Security review dan koreksi

### Initial review

- D6 menemukan tes bergantung tanpa syarat pada toolchain workstation yang tidak diprovisikan oleh `ubuntu-latest`.
- D8 membuktikan dengan data sintetis bahwa symlink dapat memasukkan berkas luar, menimpa target luar, dan memasukkan anggota APK tersembunyi.

### Correction cycle 1

- toolchain check dipisahkan menjadi unit fail-closed dan mandatory real-build mode;
- recursive symlink rejection, regular-file-only ZIP, dan exact APK member allowlist ditambahkan.

Re-review: D6 **PASS**; D8 masih menemukan ancestor symlink dan hardlink overwrite.

### Correction cycle 2

- seluruh komponen ancestor path diperiksa;
- descendant regular-file hardlink ditolak (`st_nlink != 1`);
- `_tulis` memeriksa ulang ancestor dan destination sebelum write;
- regression tests memastikan ancestor symlink tidak membuat berkas luar dan hardlink victim tidak berubah.

Final D8 re-review: **PASS**, 0 blocking finding. Synthetic predecessor/direct variants juga menolak root symlink, descendant directory symlink, descendant hardlink, non-directory root, dan direct `_tulis` escape.

Residual risk yang diterima untuk scope lokal ini: path checks tetap memiliki TOCTOU bila ada aktor konkuren yang sengaja memutasi output tree di antara check dan use. Builder mengasumsikan output tree tidak dimodifikasi proses lain selama build. Mitigasi `openat2`/directory-fd + `O_NOFOLLOW` berada di luar C1-05.

## 4. Track C — Hermes offline sandbox

Diagnosis memakai salinan source/install dan profil sintetis di `$TMPDIR/c105/hermes-offline-3`, terlihat di sandbox sebagai `/opt/c105`; instalasi/profil aktif tidak dimodifikasi.

| Probe | Hasil |
|---|---|
| profil negatif tanpa committed environment | exit 1, error yang diharapkan: `no dependency environment is committed` |
| profil sintetis + committed environment | startup `--version` production-shaped exit 0 |
| install key virtual | `dba7e6e174d88653` |
| HOME/HERMES_HOME child | `/opt/c105/home` dan `/opt/c105/home/.hermes/profiles/synthetic` |
| network | unavailable dalam namespace |
| credential visibility | path active `auth.json` tidak terlihat; isi credential tidak pernah dibaca |
| model/provider | tidak ada live atau paid model invocation |

Verdict dibatasi pada `PASS_PREFLIGHT`, bukan live integration.

## 5. Perintah verifikasi dan hasil

| Perintah | Exit | Hasil |
|---|---:|---|
| `SDB_REQUIRE_FIXTURE_TOOLCHAIN=1 .venv/bin/python -m pytest -q tests/test_fixtures.py` | 0 | 10 passed |
| `.venv/bin/ruff check scripts/build_fixtures.py tests/test_fixtures.py` | 0 | all checks passed |
| `SDB_REQUIRE_FIXTURE_TOOLCHAIN=1 make fixtures-verify` | 0 | dua fixture `SAMA` |
| `make check` dengan policy/evidence/toolchain env | 0 | seluruh sub-gate lulus; hygiene 0 FAIL/3 WARN |
| `make did-suite` | 0 | 5/5 target PASS; halusinasi 0 |
| exact Gitleaks 8.28.0 + baseline + `--log-opts="--all"` | 0 | 197 commit; 0 finding |
| `git diff --check` | 0 | bersih |
| D6 correction re-review | 0 | PASS, 0 blocker |
| D8 final correction re-review | 0 | PASS, 0 blocker |

Log final lokal: `$TMPDIR/c105/final-gates/` (`make-check.log`, `did-suite.log`, `fixtures-verify.log`, `gitleaks-history.json`).

## 6. Batas dan blocker tersisa

Tidak ada blocker C1-05. Yang belum dibuktikan dan tidak diklaim:

1. GitHub Actions dengan runner khusus yang memprovisikan exact pinned toolchain dan mengaktifkan `SDB_REQUIRE_FIXTURE_TOOLCHAIN=1`.
2. Ketahanan terhadap mutasi output-tree konkuren/TOCTOU.
3. Hermes live model/provider integration.
4. Push, PR, merge, deploy, atau release acceptance.

## 7. Keputusan akhir

C1-05 layak ditutup lokal: history scan, fixture determinism, sandbox preflight, full repository check, fixture verification, dan independent bounded security review semuanya hijau. Berhenti setelah C1-05; tidak memulai capability berikutnya.
