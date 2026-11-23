# SDB — C1-08 FINAL CLOSEOUT (metrik tes terikat artefak + gate keamanan BE-SP-10)

Status dokumen: **FINAL — review D6/D8 selesai, 5 temuan HIGH/MEDIUM diperbaiki, gate akhir berjalan**.
Mode kerja: `CHANGE_ONLY`. Baseline: `c96d55f`. Tidak ada push/PR/merge/deploy. Tidak ada perubahan konfigurasi OS.

## 0. Verdict satu baris

Perubahan C1-08 **ADA** dan **TERUJI**; D6 awalnya **REJECT** (3 HIGH + 2 MEDIUM terbukti),
semuanya telah diperbaiki dan diuji ulang (47 tes fokus lulus); D8 **APPROVE_WITH_NOTES**.
Final gate dijalankan ulang setelah perbaikan (§10). Commit lokal kanonik sudah dibuat **tepat satu kali**; SHA disebut di balasan chat karena laporan ini tidak menyimpan hash dirinya sendiri.

## 1. Artefak yang dinilai

| Item | Nilai |
|---|---|
| Repo kandidat (clone bersih) | `<scratch>/c1-08-candidate-1795317880` |
| Kandidat pra-review (digantikan) | `3e39aa57bafea4151b141719c0bbf47639a08435` (tree `bfac3501147fcbca4b6fa44e55d0215ec466ea4f`) |
| Commit kandidat tervalidasi final | `733c39aaa7eb954c5e76d4e2da2962ac5b4c8f5c` |
| Parent | `c96d55fc4de2fefd2f78c08b7fa2eb4b9bb2e260` (= baseline C1-08) |
| Branch | `feat/c2b2g-ci-hardening` |
| Tree kandidat tervalidasi final | `eb7c4ee1c587ead3626de793094280ac8baf40e6` |
| Pesan commit | `feat(capability): metrik JUnit terikat artefak + gate keamanan BE-SP-10 fail-closed (C1-08)` |
| Status tree kandidat | bersih (`git status --porcelain=v1 -uall` kosong) sebelum & sesudah semua target |
| Allowlist berkas (6) | `scripts/sdb_junit_reporter.py`, `scripts/sdb_security_gate.py`, `tests/test_junit_reporter.py`, `tests/test_be_sp10_security_gate.py`, `Makefile`, `registry/capability_pilot.yaml` |
| Kesamaan pohon vs repo kerja | `sha256sum` 6 berkas identik (perbandingan `diff` baris hash → `ALL_SIX_IDENTICAL`) |

## 2. Gate wajib — `make check` pada kandidat

Perintah: `PY_SYS=<repo>/.venv/bin/python PYTEST_ADDOPTS="--junitxml=<scratch>/c1-08-full-<rev>.xml" make check`
Log: `c1-08-final-make-check-733c39aa….log` (`check_rc=0`, artefak `c1-08-final-733c39aa….xml` 129.152 B).

| Target | Hasil |
|---|---|
| `lint` (ruff: sdb_platform scripts tests skills dashboard) | `All checks passed!` |
| `lint-registry` | `registry_lint: PASS` — custom skills 43, profiles 9, keep_local 26 |
| `test` (pytest tests skills integrations) | 1087 lolos, 0 gagal (lihat §3) |
| `drift` | `skill drift: 136/136 OK, 0 bermasalah` |
| `hygiene` | `hygiene: PASS (0 FAIL, 3 WARN)` — 611 berkas dinilai; 3 WARN `R1_big_file` (vendor three.module.min.js, 2 json evidence lama) |
| `packs` | `pack: PASS (0 gagal / 9 berkas)` |
| `docs-lint` | `docs_lint: PASS` — 62 dokumen md, 10 html terlacak (diizinkan 10), 43 custom skill |

Jalur `test` **tidak** dijalankan dua kali untuk menghitung angka: angka diambil dari artefak JUnit run tersebut.

Catatan kegagalan run pertama (v1, `check_rc=2`) — **bukan** akibat perubahan C1-08: pada clone baru
`make drift` mati dengan `KeyError: 'where'` di `scripts/doctor.py:134` karena `.venv` tidak ada di clone
(baris dependensi tak punya `where`). Direproduksi pada clone baseline `c96d55f` murni (§8). Setelah
`.venv` disediakan di clone (direktori nyata, isi di-symlink; tetap di-ignore git), drift lulus.

## 3. Metrik tes terikat artefak — `make test-count`

Perintah (metadata dari env, tanpa evaluasi shell):

```
JUNIT_XML=<scratch>/c1-08-final-733c39aaa7eb954c5e76d4e2da2962ac5b4c8f5c.xml
TEST_COMMAND="make check"  TEST_EXIT_CODE=0
TEST_RUN_ID="c1-08-final-733c39aaa7eb954c5e76d4e2da2962ac5b4c8f5c"  TEST_REVISION="733c39aaa7eb954c5e76d4e2da2962ac5b4c8f5c"
TEST_MAX_AGE_SECONDS=3600 make test-count   → rc=0, status=METRICS_VALID, `xml_summary_warning=null`
```

| Medan | Nilai |
|---|---|
| `counts.collected / executed / passed / failed / errors / skipped` | `1087 / 1087 / 1087 / 0 / 0 / 0` |
| `xml_summary_tests` (atribut ringkasan XML — menyesatkan) | `1090` |
| Selisih yang sengaja diungkap | **3** (atribut ringkasan ≠ jumlah elemen `<testcase>` nyata) |
| `artifact.sha256` | `bb90ed23f6444d1375cd0af139a333aef7d9d2e7ec6efc3d724eba89412598f3` (129.152 B) |
| `artifact.age_seconds` | 279 (batas 3600) |
| `artifact.modified_at` | `2026-11-22T04:57:22.344969Z` |
| `binding.revision` / `exit_code` / `run_id` | `733c39aa…` / `0` / `c1-08-final-733c39aa…` |
| `binding.sha256` / `command_sha256` | `d2f52f22…` / `4a5b5cf7…` |
| `assurance.level` | `CALLER_ATTESTED` |
| `assurance.acceptance_authority` | `INFORMATIONAL_ONLY` |
| `assurance.command_causality` / `suite_completeness` | `NOT_INDEPENDENTLY_VERIFIED` (jujur: pemanggil yang mengaku) |

Artefak JUnit tidak di-commit (berada di scratch di luar repo).

## 4. Negatif (fail-closed) — bukti keluaran nyata

Semua dijalankan di repo kandidat kecuali ditandai; semuanya **REJECTED / ERROR** dengan kode berbeda.

| # | Percobaan | Hasil nyata | rc |
|---|---|---|---|
| N1b | `TEST_REVISION=c96d55f…` (klaim ≠ HEAD kandidat) | `{"error":"revision_mismatch","status":"REJECTED"}` | 2 |
| N2 | tree kotor (berkas probe ditambahkan) | `{"error":"working_tree_dirty","status":"REJECTED"}` | 2 |
| N3 | `TEST_MAX_AGE_SECONDS=1` (artefak 199 s) | `{"error":"report_stale","status":"REJECTED"}` | 2 |
| N4 | XML bukan JUnit (`<foo><bar/></foo>`) | `{"error":"xml_not_junit","status":"REJECTED"}` | 2 |
| N5 | `TEST_COMMAND` tidak diisi | `{"error":"command_invalid","status":"REJECTED"}` | 2 |
| N6 | `<testcase>` dengan 2 outcome (failure+skipped) | `{"error":"testcase_outcome_invalid","status":"REJECTED"}` | 2 |
| N7 | `TEST_REVISION=not-a-revision` | `{"error":"revision_invalid","status":"REJECTED"}` | 2 |
| N8 | XML 0 byte | `{"error":"xml_empty","status":"REJECTED"}` | 2 |
| N9 | `TEST_EXIT_CODE=1` + artefak hijau | `status=TEST_FAILURE` (counts tetap 1087/0/0/0) | 2 |

Percobaan N1 pertama (menjalankan `make test-count` di clone baseline `c96d55f`) **tidak valid sebagai uji**:
Makefile baseline belum punya target itu (`No rule to make target`) — diganti N1b di atas.

## 5. Gate keamanan BE-SP-10 (end-to-end, bukan hanya unit test)

Unit test fokus setelah perbaikan review (kandidat, interpreter `.venv` py3.11):
`tests/test_be_sp10_security_gate.py` + `tests/test_junit_reporter.py` → **47 passed in 2.53s**
(26 tes gate termasuk matriks T1–T12 + provenance/argv, 21 tes reporter termasuk 6 regresi D6), ruff `All checks passed!`.

CLI nyata (`scripts/sdb_security_gate.py …`) — scope yang disetujui registry adalah `allowed_scopes: ["."]`:

| # | Perintah (ringkas) | Hasil nyata |
|---|---|---|
| G1 | `--revision deadbeef` | `execution.errors=[{revision_invalid: "revision wajib SHA-1 penuh 40 hex"}]`, `status=ERROR` |
| G2 | `--revision c96d55f…` (≠ HEAD) | `{revision_mismatch: "source revision tidak sama dengan HEAD yang diverifikasi"}`, `status=ERROR` |
| G3 | `--capability BE-SP-99` | `{capability_unknown: "BE-SP-99 tidak terdaftar di registry pilot"}`, `status=ERROR` |
| G4 | `--scope ../../etc` | `{scope_not_approved: "scope tidak tercantum di registry capability"}`, `status=ERROR` |
| G5b | `env PATH=/usr/bin:/bin` (tanpa gitleaks), `--scope .` | `{scanner_missing: "scanner mandatory tidak tersedia"}`, `status=ERROR`; evidence `execution_status=FAIL`, `acceptance_status=NOT_ACCEPTED`, `release_authorization=NOT_AUTHORIZED` |
| G6b | `--capability BE-SP-10 --scope . --revision <HEAD> --repo .` | `status=PASS`, `findings=[]`, `execution.status=SUCCESS`, `scanner=gitleaks`, `scanner_version=8.28.0`, `scanner_sha256=5fd1b3b0…b3298`, `config_sha256=5915d715…a719f` |

Bukti redaksi/anti-bocor dari G6b: command tercatat
`gitleaks git --log-opts 733c39aa… --config .gitleaks.toml --report-format json --report-path '[ephemeral-report]' --exit-code 1 --redact=100 --no-banner '[repository]'`
→ tanpa lintasan absolut scanner, tanpa lintasan repo nyata, tanpa isi temuan.
Pemisahan wewenang: `evidence_level=AGENT_REPORTED`, `acceptance_status=INFORMATIONAL_ONLY`, `release_authorization=NOT_AUTHORIZED` (build tidak dapat menaikkan dirinya ke independent acceptance — konsisten dengan `docs/BE_SP12_EVIDENCE_CONTRACT.md`).

`make secrets` (gitleaks repo): `201 commits scanned`, `no leaks found`, rc=0.

## 6. Ringkasan berkas yang berubah (dari diff kandidat)

| Berkas | Inti perubahan |
|---|---|
| `scripts/sdb_junit_reporter.py` | Baca artefak lewat **satu** file descriptor (`os.open` + `O_NOFOLLOW` + `fstat` + `S_ISREG`) → ukuran/isi/mtime tak bisa merujuk objek berbeda (TOCTOU); `_parse_xml` mengembalikan `(root, raw, modified_at)`; mtime dari FD; `--require-clean-repo` wajib; hitung elemen `<testcase>` nyata dan laporkan `xml_summary_tests` terpisah; semua metadata dari env/lib (tanpa `shell=True`); tolak malformed/kosong/terlalu besar/bukan-JUnit/kedaluwarsa/revision-mismatch/tree kotor/multi-outcome |
| `scripts/sdb_security_gate.py` | Trust root hanya dari blob Git pada revisi terikat (`resolve_head` → `_run_gate(expected_revision=…)`), bukan working tree dan bukan argumen pemanggil; snapshot scanner+config ke tempdir privat dengan digest dibekukan (0o500/0o400) → `snapshot provenance mismatch` bila berubah; baca laporan lewat `_read_bounded` (satu FD, ada batas byte); mutasi pohon saat pemindaian → `source_changed_during_scan` tanpa evidence; revisi wajib 40-hex == HEAD terverifikasi; output hanya basename scanner |
| `tests/test_junit_reporter.py`, `tests/test_be_sp10_security_gate.py` | Fixture JUnit sintetis + repo git sementara; tegas untuk jalur fail-closed (config symlink, blob registry hilang, config dari blob vs working tree, konfigurasi gitleaks nyata) |
| `Makefile` | Target `test-count` baru: panggil reporter dengan `--expected-revision "$(git rev-parse HEAD)"`, `--require-clean-repo .`, `--max-age-seconds "${TEST_MAX_AGE_SECONDS:-3600}"` (tanpa menjalankan pytest lagi) |
| `registry/capability_pilot.yaml` | Entri `BE-SP-10` (`status: PILOT`, `security_gate`: scanner gitleaks 8.28.0 + sha256, config `.gitleaks.toml`, `allowed_scopes: ["."]`, `evidence_level_allowed: [AGENT_REPORTED]`, `acceptance: INFORMATIONAL_ONLY`) |

## 7. Review independen D6/D8

Dua reviewer independen read-only dijalankan pada kandidat yang sama:

| Reviewer | Batch | Verdict | Bukti |
|---|---|---|---|
| D6/D8 — BE-SP-10 | `deleg_17d46da2` task 1 | **APPROVE_WITH_NOTES** | 22/22 tes gate lulus; 9 temuan MEDIUM/LOW, tanpa HIGH; gitleaks 8.28.0 sha256 `5fd1b3b0…b3298` cocok pin registry |
| D6 — JUnit reporter | `deleg_17d46da2` task 2 | **REJECT** | 15/15 tes lulus, tetapi 10 temuan (3 HIGH) terbukti lewat probe read-only |
| D6/D8 + D6 (re-review) | `deleg_aac2e673` | **GAGAL (infrastruktur)** | task 1 HTTP 403 tokenrouter, task 2 HTTP 402 billing — bukan verdict kode; tidak di-dispatch ulang dengan model/provider sama |

Temuan D6 yang **direproduksi peneliti utama** sebelum diperbaiki (probe `c1-08-review-probe.py`, 5/5 terbukti):

| # | Finding | Dampak sebelum perbaiki | Status |
|---|---|---|---|
| H1 | `_local_name()` membuang namespace → `<evil:testsuites>` diterima | XML bukan-JUnit dilaporkan `METRICS_VALID`, collected=1 | **DIPERBAIKI** |
| H2 | Guard DTD hanya scan byte ASCII → UTF-16 lolos, entity mengembang (5.120 char) | `METRICS_VALID`, potensi entity-expansion DoS | **DIPERBAIKI** |
| H3 | `revision=None` → `TypeError` tak tertangkap | CLI exit 1 + traceback, bukan JSON `REJECTED` exit 2 | **DIPERBAIKI** |
| M1 | `<testcase><wrapper><failure/></wrapper></testcase>` dihitung passed | tes gagal tercatat lolos | **DIPERBAIKI** |
| M2 | `tests="abc"` menolak seluruh laporan | field non-otoritatif memveto count elemen nyata | **DIPERBAIKI** |

Catatan D8 (APPROVE_WITH_NOTES) — diterima dengan mitigasi/penjelasan, bukan blocker:

| Temuan | Sikap |
|---|---|
| Scope divalidasi tapi scan selalu seluruh repo (over-scan) | Registry saat ini hanya mengizinkan `.`, jadi hasil ekuivalen; dicatat sebagai batas desain, bukan under-scan |
| Jalur ERROR tetap membawa `capability_evidence` | Evidence bertanda `execution_status=FAIL` + `acceptance_status=NOT_ACCEPTED`; tidak ada eskalasi penerimaan |
| Pin provenance tak teruji / override `_run_gate` | **Diperbaiki**: 3 tes baru menguji pin hilang, digest salah, dan pin sah menjalankan gitleaks nyata |
| Argv scanner tak diassert | **Diperbaiki**: tes baru merekam argv dan memverifikasi `--log-opts <revision>`, `--config`, `--redact=100`, `--no-banner`, `--exit-code 1`, redaksi path |
| Allowlist path config menyaring berkas | Sudah didokumentasikan di `.gitleaks.toml`; `make secrets` tetap dijalankan sebagai pelengkap |
| Binding evidence lemah, test_results pseudo-test | Sesuai kontrak BE-SP-12: `AGENT_REPORTED` + `INFORMATIONAL_ONLY`, tidak dapat self-attest |
| `_load_config` cek working tree | Dengan `require_clean=True`, working tree == blob revisi; konsisten |

Reviewer D6 yang gagal karena 402 tidak di-dispatch ulang (instruksi failure: jangan ulang dengan model/provider sama).
Pemeriksaan ekuivalen dilakukan langsung oleh peneliti utama lewat probe nyata + 11 tes regresi baru.

## 8. Cacat pra-ada yang ditemukan (di luar allowlist — tidak diperbaiki)

| Item | Detail |
|---|---|
| Gejala | `make drift` → `KeyError: 'where'` di `scripts/doctor.py:134` |
| Reproduksi | `git clone --no-hardlinks <repo> /tmp/x && git -C /tmp/x checkout c96d55f && cd /tmp/x && .venv/bin/python scripts/doctor.py --drift-only` → traceback, rc=1 (tanpa perubahan C1-08) |
| Sebab | Baris dependensi (`{"skill": dep, "status": …}`) tidak punya kunci `where`, tetapi dicetak dengan `r['where']`; di repo kanonik semua dependensi OK sehingga cabang itu tak pernah jalan. Clone tanpa `.venv` → semua pin MISSING → crash |
| Dampak | `make check` gagal di **setiap clone baru tanpa `.venv`**, bukan hanya di lingkungan ini |
| Perbaikan yang disarankan (belum dilakukan, di luar allowlist C1-08) | `r.get('where', '-')` pada baris cetak, atau tambahkan `where` saat membangun baris dependensi |
| Verifikasi bahwa ini bukan akibat C1-08 | Jalur yang sama gagal pada clone baseline murni `c96d55f` (di atas); repo kanonik dengan perubahan C1-08: `skill drift: 136/136 OK` |

## 9. Yang belum terbukti / batas jujur

1. Commit lokal di repo kanonik sudah dibuat **tepat satu kali** setelah laporan final (SHA di balasan chat). Tidak ada push/PR/merge — memang dilarang.
2. Angka 1087 berasal dari `make check` penuh pada revisi kandidat `733c39aa…` (10 tes regresi baru dari review D6/D8).
   Enam berkas kode/konfigurasi pada commit kanonik identik byte-per-byte dengan revisi yang diuji;
   satu-satunya delta tree adalah laporan ini (dokumen), yang divalidasi ulang dengan docs-lint/hygiene (§10).
3. `make test-count` mengembalikan `CALLER_ATTESTED / INFORMATIONAL_ONLY`: reporter **tidak** dapat
   membuktikan bahwa `make check` benar-benar yang memproduksi artefak; yang diikat adalah hash artefak,
   hash perintah, exit code, revisi, run id, umur, dan kebersihan tree.
4. Gate BE-SP-10 baru diuji pada gitleaks 8.28.0 lokal; `PRODUCTION_TRUST=BLOCKED` tetap berlaku
   (`release_authorization=NOT_AUTHORIZED`).
5. Atribut ringkasan `tests` JUnit bersifat non-otoritatif: rusak → `xml_summary_warning`, tidak membatalkan
   count elemen `<testcase>`; selisih 1090 (ringkasan pytest) vs 1087 (elemen nyata) sengaja dilaporkan,
   bukan disembunyikan.
6. Depth/L4 dan rilis produksi tidak disentuh di C1-08.

## 10. Siklus koreksi 1 + gate akhir (bukti fresh)

Review D6 **REJECT** memicu satu siklus koreksi terikat (maksimal dua sesuai mandat). Semua perbaikan
dikerjakan di kandidat terisolasi, bukan di repo kanonik, sebelum commit lokal dibuat.

| Langkah | Perintah / artefak | Hasil nyata |
|---|---|---|
| Reproduksi 5 finding | `c1-08-review-probe.py` (read-only) | **5/5 terbukti**: namespace diterima, UTF-16 DTD mengembang 5.120 char, `revision=None` → TypeError, nested failure → passed, `tests="abc"` → REJECTED |
| Perbaikan + regresi | `47 passed in 2.53s`, ruff `All checks passed!` | 6 tes reporter baru + 4 tes gate baru + 1 assert findings diperkuat |
| Commit kandidat | `git commit --amend --no-edit` (satu commit di atas `c96d55f`) | `733c39aaa7eb954c5e76d4e2da2962ac5b4c8f5c`, tree `eb7c4ee1c587ead3626de793094280ac8baf40e6`, `git status` **kosong** |
| Full gate | `make check` + `PYTEST_ADDOPTS=--junitxml=…` pada kandidat | **`check_rc=0`**; artefak `129152` byte, sha256 `bb90ed23f6444d1375cd0af139a333aef7d9d2e7ec6efc3d724eba89412598f3` |
| Count elemen nyata | `xml.etree.ElementTree` iter `<testcase>/<failure>/<error>/<skipped>` | **1087 / 0 / 0 / 0**; ringkasan `tests=1090` (non-otoritatif, selisih 3) |
| `make test-count` positif | env binding lengkap, revisi `733c39aa…` | **rc=0, `METRICS_VALID`**, counts `1087/1087/0/0/0`, `assurance=CALLER_ATTESTED / INFORMATIONAL_ONLY` |
| 9 probe negatif | `c1-08-final-validation.sh` | **9/9 fail-closed**, rc=2, 0 traceback: `revision_mismatch`, `working_tree_dirty`, `report_stale`, `xml_not_junit`, `revision_invalid`, `xml_unsafe`, `xml_namespace_invalid`, `testcase_outcome_invalid`, `TEST_FAILURE` (exit_code=1) |
| Secret scan | `make secrets` | **rc=0**, 201 commit, 11,67 MB, **0 temuan** |
| Gate E2E | `sdb_security_gate.py --repo <candidate> --capability BE-SP-10 --scope . --revision 733c39aa…` | **rc=0, `PASS`**, 0 findings, 0 errors, evidence `INFORMATIONAL_ONLY / NOT_AUTHORIZED / PASS` |
| Drift | `make drift` (di dalam `make check`) | `skill drift: 136/136 OK, 0 bermasalah` |
| Commit kanonik | `git commit` tepat satu kali di atas `c96d55f` | 7 berkas (6 kode/konfigurasi + laporan ini); 6 berkas hash-identik dengan revisi tervalidasi; docs-lint + hygiene PASS pasca-edit dokumen; focused 47 passed di HEAD kanonik |

Semua angka di atas berasal dari eksekusi nyata pada 2026-11-22 (WIB). Tidak ada angka yang diambil dari
klaim reviewer tanpa reproduksi. Re-review D6/D8 yang gagal (403/402) tidak dijadikan dasar penerimaan;
penggantinya adalah probe langsung + 11 tes regresi yang dijalankan peneliti utama.

