# SDB Doctor Fresh-Clone Fix — WS-1 Stage B Final Result

**Verdict: WS-1 STAGE B — PASS.** Patch Doctor lolos focused regression, static quality,
full regression, `make check`, simulasi fresh clone tanpa `.venv`, hygiene, dan secret detection.
Tidak ada blocker atau temuan HIGH baru akibat patch.

## 1. Identitas kandidat

| Item | Nilai |
|---|---|
| Waktu validasi final | `2026-11-22T21:35:47+07:00` |
| Branch | `feat/c2b2g-ci-hardening` |
| Baseline/HEAD | `d14dc02…` (`d14dc02` — SHA penuh disingkat: pola 40-hex polos kena false-positive gitleaks `sourcegraph-access-token`) |
| Tipe kandidat | working-tree patch di atas HEAD; belum staged/commit |
| Staged files | `0` |
| Rilis/push/PR/merge/deploy | tidak dilakukan |
| Production trust | tidak diubah |

Scope Stage B hanya:

1. `scripts/doctor.py`
2. `tests/test_doctor_dep.py`
3. `reports/SDB_DOCTOR_FRESH_CLONE_FIX_RESULT.md`

Dua laporan protected tetap di luar scope dan tidak diedit atau di-stage:

- `reports/SDB_C1_06_TRUSTED_RUNTIME_RESULT.md`
- `reports/SDB_NEW_SESSION_CONTINUATION_RESULT.md`

## 2. Perubahan yang divalidasi

1. `scripts/doctor.py`
   - Memisahkan `bad_skills` dan `bad_deps`.
   - Mencetak setiap kategori memakai field miliknya sendiri.
   - Menghitung skill drift dan dependency drift secara independen.
   - Tetap fail-closed: exit nonzero bila salah satu kategori bermasalah.
2. `tests/test_doctor_dep.py`
   - Meregresikan dependency hilang tanpa traceback.
   - Membuktikan exit `1` dan dua summary yang terpisah.
3. Laporan ini
   - Mengikat hasil final Stage B pada kandidat, command, exit code, dan artefak aktual.

## 3. Evidence matrix

| Gate | Command ringkas | Exit | Bukti aktual | Status |
|---|---|---:|---|---|
| Focused regression | `.venv/bin/python -m pytest -q tests/test_doctor_dep.py -o addopts=` | 0 | `4 passed in 0.15s` | PASS |
| Ruff fokus | `.venv/bin/python -m ruff check scripts/doctor.py tests/test_doctor_dep.py` | 0 | `All checks passed!` | PASS |
| Diff whitespace | `git diff --check` | 0 | tanpa output | PASS |
| Full gate | `PYTEST_ADDOPTS="--junitxml=<scratch>/sdb-ws1-full-junit.xml" make check` | 0 | lint, registry, full pytest, drift, hygiene, packs, docs-lint lulus | PASS |
| JUnit deterministik | `.venv/bin/python -m pytest tests skills integrations -q --junitxml=<scratch>/sdb-ws1-full-junit-valid.xml` | 0 | seluruh testcase selesai tanpa failure/error | PASS |
| JUnit parser | `sdb_junit_reporter.build_report(...)` | 0 | `METRICS_VALID`; 1.088 collected/executed/passed | PASS |
| Fresh clone | `/usr/bin/python3 <isolated>/scripts/doctor.py --drift-only` | 1 | expected fail-closed; tanpa traceback | PASS |
| Secrets allowlisted | `make secrets` | 0 | tidak ada leak yang lolos konfigurasi | PASS |
| Candidate secret scan | `gitleaks dir <isolated-candidate> --redact ...` | 0 | `0` temuan pada tiga file scope | PASS |
| Raw-history control | neutral Gitleaks config di scratch | 1 | `38` temuan historis pra-ada; `0` overlap dengan scope | EXPECTED WARN |

`make check` menghasilkan bukti berikut:

- Ruff: PASS.
- Registry: PASS — 43 custom skills, 9 profiles, 26 `keep_local`.
- Drift: skill `136/136`, dependency `3/3`.
- Hygiene: PASS — `0 FAIL`, `3 WARN` pra-ada untuk tiga berkas besar.
- Pack: PASS — `9/9`.
- Docs lint: PASS — 62 dokumen Markdown, 10 HTML diizinkan, 43 custom skills.

## 4. JUnit — hitungan dari artefak aktual

Artefak final: `<scratch>/sdb-ws1-full-junit-valid.xml`

| Metrik | Nilai |
|---|---:|
| Ukuran | 129.288 byte |
| SHA-256 | `7985096eaa0475660b6fcec1d5157c32518b1d96d98a12a490bda8cf2f989ce2` |
| `<testcase>` collected | 1.088 |
| Executed | 1.088 |
| Passed | 1.088 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |
| Reporter status | `METRICS_VALID` |

Atribut summary XML menyatakan `tests=1091`, sedangkan elemen `<testcase>` berjumlah 1.088.
Selisih tiga berasal dari tiga `unittest.subTest` pada
`skills/product-kit/tests/test_product_kit.py`; pytest 9.1.1 menghitung tiga report subtest
namun menserialisasi parent sebagai satu testcase. Parser kanonik SDB menghitung elemen testcase
konkret, menandai `xml_summary_matches_counts=false`, dan tetap menghasilkan
`METRICS_VALID`. Tidak ada failure yang disembunyikan.

## 5. Fresh-clone negative test

Isolated tree dibuat melalui `git archive HEAD` di scratch; hanya kandidat
`scripts/doctor.py` disalin ke tree tersebut. Hash source dan salinan identik. Tree isolated
tidak memiliki `.venv` dan dijalankan memakai `/usr/bin/python3`, bukan interpreter repo.

| Assertion | Hasil |
|---|---|
| `.venv` absent | benar |
| Candidate hash match | benar |
| Exit code | `1`, expected fail-closed |
| Traceback | tidak ada |
| stderr | kosong |
| Skill summary | `136/136 OK, 0 bermasalah` |
| Dependency summary | `0/3 OK, 3 bermasalah` |
| Missing dependency dilaporkan | benar |
| Skill/dependency count terpisah | benar |

## 6. Hygiene dan security

1. Hygiene gate: `0 FAIL`, `3 WARN` pra-ada untuk berkas besar; bukan regresi Doctor.
2. Allowlisted full-history scan: exit `0`.
3. Isolated scan atas tiga file Stage B: `0` temuan.
4. Neutral raw-history scan Gitleaks 8.28.0: `38` temuan pada dua file/two commits historis,
   terdiri dari 37 `sourcegraph-access-token` dan 1 `generic-api-key`; seluruhnya committed,
   tidak overlap dengan tiga file Stage B, dan nilainya tidak dibaca/ditampilkan.
5. `state/gitleaks-raw.json` yang sudah ada juga berisi `38`, sehingga komentar Makefile
   “normal = 40” adalah warning dokumentasi pra-ada, bukan defect patch Doctor.

## 7. Integrity

Hash baseline sebelum eksekusi:

| Berkas | SHA-256 baseline |
|---|---|
| `scripts/doctor.py` | `1d5d87c32df06fa678707b45bd48df8405e57cb6e77e40a19c84176bb9f43d5c` |
| `tests/test_doctor_dep.py` | `039894216df8349e83632906e6f25f6cd2f9601e85aae38d2f96bd964025ae22` |
| laporan Stage B ini, sebelum finalisasi | `d8b9f9fd7d4e55476ac3adde727e2df5c26014bea8a7e7f287eea2fac5a7c63b` |
| `reports/SDB_C1_06_TRUSTED_RUNTIME_RESULT.md` | `10844035dd166c6e822b40906820a02608757f298a9eead3a1ea00c68cd559f7` |
| `reports/SDB_NEW_SESSION_CONTINUATION_RESULT.md` | `a61ffbb17090384ed8652de8e01b2819ce389b12132ae7efeb9645a746d8629f` |

Sebelum laporan ini difinalkan, kelima hash identik dengan baseline. Perubahan sesudahnya
hanya finalisasi laporan allowlisted ini. Hash final laporan dicatat secara eksternal agar
tidak membuat self-referential hash. Final integrity wajib menunjukkan kedua protected report
tetap identik, staged count `0`, dan tidak ada path baru akibat pengujian.

## 8. Remaining findings

- **Blocker/HIGH baru:** tidak ada.
- **Warning pra-ada:** tiga large-file hygiene warning.
- **Warning pra-ada:** komentar `secrets-raw` menyebut 40, sedangkan baseline aktual dan scan
  fresh sama-sama 38.
- **JUnit note:** summary attribute 1.091 vs 1.088 testcase dijelaskan oleh tiga subtest;
  canonical reporter berstatus `METRICS_VALID`.

## 9. Stage C boundary

Exact proposed Stage C commit scope:

```text
scripts/doctor.py
tests/test_doctor_dep.py
reports/SDB_DOCTOR_FRESH_CLONE_FIX_RESULT.md
```

Dua protected reports, Flexible REA, Gate #0, DID, registry, workflow stages, dan production
trust tidak termasuk commit. Stage B tidak melakukan staging, commit, amend, fetch/pull,
history rewrite, push/PR, merge, atau deploy.

Minimum approval berikutnya:

> **APPROVE STAGE C WS-1 DOCTOR COMMIT ONLY**

Approval itu hanya mengizinkan staging eksplisit tiga path di atas dan satu commit lokal
terfokus; tidak mengizinkan push, PR, merge, deploy, atau perubahan REA.
