# SDB C1 — BE-SP-12 Final Result

- **Waktu verifikasi:** 2026-11-20 (sesi closeout ONE-FIX)
- **Status:** `PASS_VERIFIED_SUBSCOPE`
- **Mode:** `CHANGE_ONLY`
- **Policy:** `SDB_DONE_POLICY=attested`; `SDB_EVIDENCE_MODE=legacy`

## 1. Revision dan commit

| Item | Nilai |
|---|---|
| HEAD sebelum | `cc6a5735bfcc258d7b055e74b6547c2c8bcc481b` |
| Commit lokal BE-SP-12 | Dibuat setelah laporan ini lolos validasi ringan; full SHA dilaporkan owner di percakapan (tidak dapat berada di dalam berkas yang di-commit-nya sendiri) |
| Push / PR / merge / deploy | Tidak dilakukan |

## 2. Berkas scope (staged eksplisit)

1. `registry/capability_pilot.yaml`
2. `registry/capability_evidence.schema.json`
3. `scripts/sdb_capability_evidence.py`
4. `tests/test_capability_evidence.py`
5. `docs/BE_SP12_EVIDENCE_CONTRACT.md`
6. `reports/SDB_C1_BE_SP12_RESULT.md`

`reports/SDB_NEW_SESSION_CONTINUATION_RESULT.md` tetap untracked, tidak diubah, tidak di-stage. Tidak ada perubahan pada `workflows/`, `agents/`, atau `.github/`.

## 3. Acceptance T1–T10

Focused suite mengoleksi **57 tes**, selesai `[100%]`, exit `0`.

| Acceptance | Hasil | Bukti utama |
|---|---|---|
| T1 valid evidence | PASS | record/validate, immutable write, race no-overwrite, no-partial-write |
| T2 capability tidak dikenal | PASS | unknown/malformed ID ditolak |
| T3 revision/hash mismatch | PASS | HEAD binding dan SHA-256 mismatch ditolak |
| T4 JSON/schema/NaN/Infinity | PASS | parser strict dan schema checks |
| T5 exit code gagal | PASS | nonzero exit tidak menjadi PASS |
| T6 zero executed tests | PASS | `no_tests_executed` |
| T7 traversal/symlink/write root | PASS | traversal, symlink, root liar, artefak hilang, read luar root ditolak |
| T8 self-attestation | PASS | builder tetap `AGENT_REPORTED`; test command tidak dieksekusi |
| T9 targeted mutations | PASS | M1–M5 terdeteksi pada scratch copy |
| T10 invariant workflow/agent | PASS | 19 stage dan protected paths tetap utuh |

PASS di atas hanya acceptance lokal untuk execution-evidence contract; bukan independent product acceptance atau release authorization.

## 4. Perintah dan hasil final (state sumber terkoreksi)

| Perintah | Exit | Hasil |
|---|---:|---|
| `make hygiene` | 0 | PASS — 590 berkas dinilai, **0 FAIL**, 3 WARN `R1_big_file` (baseline lama: `dashboard/vendor/three.module.min.js`, dua JSON upgrade-evidence) |
| `.venv/bin/python -m pytest tests/test_capability_evidence.py -q` | 0 | 57 tes, `[100%]` |
| `make check` (fresh, sekali) | 0 | **PASS penuh** — rincian di bawah |

Rincian `make check` (exit 0):

| Tahap | Hasil |
|---|---|
| `ruff check sdb_platform scripts tests skills dashboard` | `All checks passed!` |
| `registry_lint` | PASS — custom skills 43, profiles 9, keep_local 26 |
| `pytest tests skills integrations -q` | **920 passed / 0 failed / 0 skipped** (progress 920 `.` sampai `[100%]`) |
| `skill drift` | 136/136 OK, 0 bermasalah |
| `repo_hygiene` | PASS — 0 FAIL, 3 WARN baseline lama |
| `pack_build verify` | PASS — 0 gagal / 9 berkas pack |
| `docs_lint` | PASS — dokumen md 60, html terlacak 10/10, custom skill 43/43 |

Riwayat jujur: `make check` pertama (sebelum closeout) FAIL `R3_pii` pada fixture Git sintetis `test@sdb[.]local` (919 passed, 1 failed). Blocker ditutup dalam satu correction cycle terotorisasi: fixture diganti ke `fixture@sdb.test` (TLD `.test` RFC 2606 di-exempt `repo_hygiene.py`), semantik tes tidak berubah; laporan ini disanitasi dari literal bermasalah; fresh `make check` lulus penuh.

Verifikasi ringan ulang setelah laporan final ditulis: `make docs-lint` + `make hygiene` (lihat §9).

## 5. D6 code review — disposisi

| Finding | Severity | Disposition |
|---|---|---|
| Immutable write check-then-`os.replace` berpotensi race overwrite | MEDIUM | FIXED: hard-link eksklusif; T01e membuktikan file pesaing tidak tertimpa |
| Filesystem/decode error tidak selalu berbentuk output terstruktur | LOW | FIXED: generic `io_error` REJECTED, tanpa membocorkan isi |
| Schema, Git HEAD binding, result arithmetic, artifact hash, strict JSON | — | REVIEWED; tercakup T1–T7 |
| Backward compatibility | — | Modul/registry pilot baru; katalog canonical 26 dan interface lama tidak berubah |

## 6. D8 security review — disposisi

| Finding | Severity | Disposition |
|---|---|---|
| `--root`/input validate dapat menunjuk path arbitrer | MEDIUM | FIXED: dikunci ke `runs/capability/`; symlink chain ditolak (T07g/T07h); validate luar root ditolak |
| Trust escalation/self-attestation | — | PASS: producer hanya `AGENT_REPORTED`; independent review tidak dapat diklaim payload |
| Unsafe command execution | — | PASS: `test_command` hanya data; subprocess hanya argv statis `git rev-parse HEAD` |
| Traversal/symlink/invalid JSON/NaN/Infinity | — | PASS pada negative tests |
| Sensitive-data/network exposure | — | PASS: tanpa akses jaringan/secrets; gitleaks 8.28 (config repo + aturan default) pada 6 berkas scope: **no leaks found**; scan regex kredensial: 0 match |

## 7. Security limitations

1. SHA-256 integrity mendeteksi perubahan, tetapi bukan tanda tangan atau identitas attestor.
2. Test result tetap self-reported level `AGENT_REPORTED`; CI/reviewer independen harus membuat attestation terpisah.
3. `--replace` adalah tindakan operator eksplisit dan tetap dapat mengganti evidence lama.
4. Perlindungan concurrent hostile filesystem belum setara sandbox/kernel isolation; artefak dapat berubah setelah hash dicatat.

## 8. Remaining issue

- **Tidak ada blocker tersisa.** Temuan `R3_pii` (`tests/test_capability_evidence.py:42`) ditutup: fixture `fixture@sdb.test`; hygiene 0 FAIL.
- Catatan non-blocker: 3 WARN `R1_big_file` adalah baseline lama (utang terlacak sebelum fase ini), bukan FAIL baru; tidak disentuh scope BE-SP-12.
- Merge blocker lama branch ini (required signatures/approval) tetap di luar scope dan tidak berubah.

## 9. Finalisasi

1. Laporan final ditulis setelah `make check` lulus.
2. Validasi ringan ulang untuk perubahan teks laporan ini: `make docs-lint` dan `make hygiene` (hasil dicatat di percakapan).
3. Stage eksplisit 6 berkas scope; inspect staged diff (`--name-only`, `--stat`, `--check`); pastikan tanpa berkas tak terkait dan tanpa secrets.
4. SATU commit lokal, tanpa amend/rewrite.
5. Capability berikut yang **hanya direkomendasikan**: `BE-SP-03`; tidak dimulai otomatis.
