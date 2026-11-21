# SDB C1-06 — SECURITY CLOSEOUT

**Tanggal:** 2026-11-22 (WIB) · **Mode:** CHANGE_ONLY · **Prioritas:** P0 SECURITY
**Baseline:** working tree C1-06 belum commit, `HEAD = c30a506` (`c30a506ba15df474959fe5f921e07993208767d3`), branch `feat/c2b2g-ci-hardening`.
**Otorisasi Owner:** koreksi terbatas router/trust/test, tes regresi keamanan baru, fixture approval sintetis, review D6/D8 delta, `make check` final, **satu** commit lokal.
**Tidak diotorisasi (dan tidak dilakukan):** push, merge, deploy, perubahan OS, tulis ulang history, kredensial nyata, `auth.json` aktif, model berbayar, eksekusi Hermes live.

---

## 1. Preflight

| Item | Hasil |
|---|---|
| `git rev-parse HEAD` | `c30a506ba15df474959fe5f921e07993208767d3` |
| `git branch --show-current` | `feat/c2b2g-ci-hardening` |
| Berkas C1-06 yang disentuh | `scripts/sdb_capability_trust.py`, `scripts/sdb_capability_router.py`, `tests/test_capability_routing.py`, `tests/test_capability_e2e_dispatcher.py` (baru), `docs/SDB_C1_CAPABILITY_ROUTING.md` |
| Kontrak dipakai ulang | BE-SP-12 (schema evidence, `scripts/evidence.py:336-400`), BE-SP-03 (task pack/lane), C1-05 (registry routing) — **tidak ada** perubahan schema BE-SP-12 |
| Laporan fase sebelumnya | `reports/SDB_C1_06_TRUSTED_RUNTIME_RESULT.md` (untracked) **digantikan** oleh laporan ini; klaim handshake/`passed: 1` di dalamnya tidak lagi berlaku |
| Delta sebelum kerja | 3 M + 3 ?? (`router` +60/−6, `trust` +7/−1, `routing test` +104/−4, `e2e` 322 baris, 2 laporan) |

---

## 2. Step 2 — Replay protection (yang diimplementasikan)

Model: approval **tidak lagi** disimpan di working copy. Trust anchor dan replay ledger berada di
state dir mesin, di luar repo, sehingga clone tidak dapat memuat, menghapus, atau memutar ulang ledger.

```
$SDB_APPROVAL_STATE_HOME            (default $XDG_STATE_HOME/sdb → ~/.local/state/sdb)  0700
  instance.json                     identitas instance, dibuat modul trust (bukan dari executor)
  approval_pubkey.pem               kunci verifikasi Ed25519 (kunci privat tidak pernah di repo)
  approvals/<approval_ref>.yaml     satu record approval bertanda tangan, 0600
  approval-replay/                  marker sekali-pakai, 0700
```

Record `sdb.capability.execution-approvals/2` menandatangani satu dokumen kanonik berisi:
`approval_ref`, `task_digest`, `capability_id`, `lane`, `allowed_write_roots`, `scope_digest`,
`nonproduction`, `issuer`, `issued_at`, `expires_at`, `nonce`, `source_revision`,
`execution_instance`, `issuer_key_id`, `signature`.

| Persyaratan brief | Implementasi | Kode |
|---|---|---|
| Approval terikat capability, task digest, scope, revisi sumber, instance | 5 field di atas + `scope_digest` kanonik; `source_revision == git rev-parse HEAD`; `execution_instance == instance_id(state)` | `sdb_capability_trust.py:load_trusted_approval` |
| Issuer eksplisit + expiry | `APPROVAL_ISSUERS` allowlist; `expires_at > issued_at`, `expires-issued <= MAX_APPROVAL_TTL`, cek `not_yet_valid`/`expired` | idem |
| Integritas kriptografis, verifier tepercaya | Ed25519, verifikasi `openssl pkeyutl -verify -pubin -rawin` dengan `approval_pubkey.pem`; opsional pin `SDB_APPROVAL_PUBKEY_SHA256` | `verify_approval_signature` |
| Sekali pakai, state tepercaya | marker `O_CREAT\|O_EXCL\|O_NOFOLLOW` 0600, key `sha256(ref \|\| NUL \|\| nonce)` di luar repo | `consume_approval`, `replay_marker_path` |
| Tidak bergantung ledger `.git/` | ledger `.git/sdb-capability-approval-replay` **dihapus** dari jalur kode | `consume_approval` |
| Instance ID tidak dari executor/repo | `instance.json` dibuat modul trust, `O_EXCL` 0600, diverifikasi tiap load | `instance_id` |
| Gagal-tertutup saat state hilang/rusak | `trust_state_missing/untrusted/corrupted/unavailable`, `trust_anchor_missing/mismatch` | `_require_state_dir`, `approval_public_key` |
| Kunci nyata tidak bocor | kunci sintetis hanya di state dir test (0700) yang dibuat per-test; repo/prompt/sandbox tidak memuat kunci | `tests/test_capability_routing.py:_keypair` |
| Produksi nonaktif bila anchor belum ada | `TRUST_MODE="test_only"`, `PRODUCTION_TRUST_ENABLED=False`; record `nonproduction: false` → `production_trust_unavailable` | `sdb_capability_trust.py:54-70`, `load_trusted_approval` |

Kode gagal-tertutup yang kini ada: `trust_state_missing`, `trust_state_untrusted`,
`trust_state_corrupted`, `trust_state_unavailable`, `trust_anchor_missing`, `trust_anchor_mismatch`,
`approval_record_missing`, `approval_record_untrusted`, `approval_record_corrupted`,
`approval_unsigned`, `approval_signature_invalid`, `approval_issuer_untrusted`, `approval_expired`,
`approval_not_yet_valid`, `approval_time_invalid`, `approval_task_mismatch`,
`approval_scope_digest_mismatch`, `approval_scope_mismatch`, `approval_revision_mismatch`,
`approval_instance_mismatch`, `approval_replayed`, `production_trust_unavailable`.

---

## 3. Step 3 — Evidence correctness

| Klaim lama | Koreksi | Bukti |
|---|---|---|
| `test_results.passed = 1` sintetis (BE-SP-12 wajib `total > 0`) | Jumlah tes dibaca dari **JUnit XML yang dihasilkan eksekusi** (`artifacts/capability/junit.xml`); tidak ada laporan → `evidence_no_tests`, evidence ditolak | `sdb_capability_router.py:_read_junit` |
| `test_command` = handshake HMAC | `test_command = "junit:artifacts/capability/junit.xml"` — handshake tidak lagi dipresentasikan sebagai hasil tes | `_write_evidence` |
| PASS bisa berdampingan dengan laporan tes merah | `evidence_result_unverified: PASS contradicts the executed test report` | `_write_evidence:571-576` |
| Eksekusi non-PASS bisa tercatat `exit_code 0` | eksekusi non-positif mencatat `max(1, exit_code)` → tidak bisa terbaca PASS oleh konsumen berbasis exit code | `_write_evidence` |
| Handshake = bukti eksekusi tugas | Dinyatakan eksplisit di artefak invocation: `trust.attestation = "self_reported_no_independent_anchor"`, `trust.mode = "test_only"`, `trust.replay_state = "machine_local"` | `write_invocation_artifact` |

**Perubahan schema BE-SP-12 yang dibutuhkan (dilaporkan, TIDAK diubah):** BE-SP-12 mewajibkan
`test_results.total > 0`, sehingga eksekusi tanpa tes tidak dapat direpresentasikan jujur — satu-satunya
pilihan lama adalah memalsukan `passed: 1`. Implementasi sekarang menolak menulis evidence
(`evidence_no_tests`) alih-alih memalsukan. Perbaikan kontrak yang diusulkan (terpisah, butuh persetujuan):
tambah field `tests_expected: bool` (atau izinkan `total: 0` dengan `test_command: "none"`) plus
`attestation: "self_reported" | "independent"`.

---

## 4. Step 4 — Security acceptance (T1–T12)

Perintah: `.venv/bin/python -m pytest tests/test_capability_routing.py tests/test_capability_e2e_dispatcher.py -q --junitxml=/tmp/e4.xml`

| # | Uji | Nama tes | Hasil |
|---|---|---|---|
| T1 | Approval sah diterima sekali | `test_t1_valid_synthetic_approval_is_accepted_exactly_once` | PASS |
| T2 | Replay ditolak | `test_replayed_approval_is_rejected` | PASS |
| T3 | Replay lintas-clone ditolak | `test_t3_cross_clone_replay_is_rejected` | PASS |
| T4 | Instance salah ditolak | `test_t4_approval_for_another_execution_instance_is_rejected` | PASS |
| T5 | Revisi / capability / scope salah ditolak | `test_t5_wrong_source_revision_is_rejected`, `test_t5_signed_scope_must_match_authorized_roots`, `test_approval_for_wrong_task_is_rejected` | PASS |
| T6 | Approval dimodifikasi ditolak | `test_modified_approval_record_is_rejected`, `test_index_flags_cannot_hide_a_modified_approval_record` | PASS |
| T7 | Issuer tak tepercaya / unsigned / kunci asing / anchor tak di-pin ditolak | `test_t7_untrusted_issuer_is_rejected`, `test_t7_unsigned_approval_is_rejected`, `test_t7_swapped_verification_key_is_rejected`, `test_t7_signature_from_an_untrusted_key_is_rejected`, `test_unpinned_verification_key_fails_closed`, `test_record_bound_to_another_key_id_is_rejected` | PASS |
| T8 | Expired / not-yet-valid ditolak | `test_expired_approval_is_rejected`, `test_t8_not_yet_valid_approval_is_rejected` | PASS |
| T9 | State hilang/rusak/tidak tersedia gagal-tertutup | `test_t9_missing_trust_state_fails_closed`, `test_t9_corrupted_instance_state_fails_closed`, `test_t9_group_readable_state_dir_is_untrusted`, `test_t9_missing_verification_key_fails_closed`, `test_replay_state_inside_the_working_copy_is_refused`, `test_trust_state_inside_the_working_copy_is_refused` | PASS |
| T10 | Executor tidak bisa memalsukan PASS otoritatif | `test_t10_executor_pass_is_refused_when_the_test_report_contradicts_it`, `test_t10_no_junit_report_means_no_evidence`, `test_stale_junit_report_cannot_become_evidence`, `test_forged_unknown_approval_is_rejected`, `test_committed_approval_store_is_not_an_authority`, `test_unverified_result_cannot_create_positive_evidence` | PASS |
| T11 | Eksekusi gagal tidak bisa menjadi evidence sukses | `test_nonzero_executor_exit_is_captured_and_fails`, `test_unverified_result_cannot_create_positive_evidence` | PASS |
| T12 | Batas sandbox tetap utuh | `test_sandbox_write_escape_is_denied_through_dispatcher`, `test_test_only_executor_is_offline_and_credential_blind`, `test_routing_inconsistent_when_sandbox_net_flags_disagree` | PASS |

Hasil: **84 tes, 0 gagal, 0 error, 0 skip** (routing 68 + e2e 16), exit 0.

### Demonstrasi dispatcher (bukan tes unit)

`.venv/bin/python runs/capability/c1-06/smoke.py` → exit **0**, 6 kasus:

| Kasus | Exit | Verdict | Evidence |
|---|---|---|---|
| `01-positive` | 0 | `INTEGRATION_TESTED_NONPRODUCTION` | `junit:...` 1/0, `PASS`, `INFORMATIONAL_ONLY` |
| `02-forged-result` | 1 | `FAIL` | `junit:...` 0/1, `FAIL`, `NOT_ACCEPTED` |
| `03-untrusted-approval` | 2 | — | `approval_record_missing` |
| `04-nonzero-exit` | 1 | `FAIL` | `junit:...` 0/1, `FAIL` |
| `05-credential-network-probe` | 0 | `INTEGRATION_TESTED_NONPRODUCTION` | tanpa kredensial terbaca, tanpa jaringan |
| `06-replayed-approval` | 2 | — | `approval_replayed: C1-03-TEST-APPROVAL` |

`result.json` mencatat `trust.mode = "test_only"` dan `trust.attestation = "self_reported_no_independent_anchor"`.
`sha256(result.json) = 642decde0f4e488eabb83c54f4ffd8aaff5eb67f7cbb139f84e223d7f9e5e961`;
12 artefak diarsipkan, **12/12 hash cocok** dengan `result.json`.

---

## 5. Step 5 — Quality gates (output nyata)

| Gate | Perintah | Exit | Angka |
|---|---|---|---|
| Fokus keamanan + regresi routing/e2e | `pytest tests/test_capability_routing.py tests/test_capability_e2e_dispatcher.py -q` | 0 | 84 tes, 0 gagal |
| Regresi capability + evidence | `pytest tests -k "capability or evidence" -q` | 0 | 195 tes, 0 gagal |
| Suite penuh | `pytest tests skills integrations -q --junitxml=/tmp/final4.xml` | 0 | **1024 tes, 0 gagal, 0 error, 0 skip** (74,4 s) |
| Lint | `ruff check scripts/ tests/` | 0 | All checks passed |
| Gerbang repo | `make check` | 0 | `registry_lint: PASS`; drift **136/136**; hygiene **605 berkas** (0 FAIL, 3 WARN); pack PASS (9 berkas); `docs_lint: PASS` |

---

## 5b. Delta review D6/D8 (dua reviewer independen, `deleg_fbba49ab`)

D6 = engineering acceptance, D8 = adversarial security. Keduanya menilai snapshot sebelum koreksi ini.

| ID | Sev | Temuan | Tindakan (file) | Status |
|---|---|---|---|---|
| D6-B1 | BLOCKER | Angka tes di laporan tidak sama dengan eksekusi nyata | Semua angka diukur ulang dari JUnit XML: 84 fokus (68+16), 195 subset, 1024 suite penuh | **DITUTUP** |
| D6-B2 | BLOCKER | `registry/capability_execution_approvals.yaml` (record unsigned) masih tampak otoritatif di docs:104 | Header DEPRECATED di YAML; docs §"approval" ditulis ulang (approval tidak pernah dibaca dari repo); tes `test_committed_approval_store_is_not_an_authority` | **DITUTUP** |
| D8-H1 | HIGH | Trust anchor tidak di-pin → same-UID writer menukar `approval_pubkey.pem` lalu re-sign | `SDB_APPROVAL_PUBKEY_SHA256` kini **wajib** (`trust_anchor_missing` bila kosong, `trust_anchor_mismatch` bila beda) + `issuer_key_id` harus `sha256:<fingerprint>` (`approval_issuer_key_mismatch`); tes `test_t7_swapped_verification_key_is_rejected`, `test_unpinned_verification_key_fails_closed`, `test_record_bound_to_another_key_id_is_rejected` | **DITUTUP untuk ancaman penulis berkas**; residual: penyerang yang juga mengubah environment tetap bisa (lihat §7) |
| D8-M1 | MED | Bukti JUnit basi bisa dipakai ulang | `_clear_stale_junit()` menghapus laporan sebelum executor dijalankan; tes `test_stale_junit_report_cannot_become_evidence` | **DITUTUP** |
| D8-M2 | MED | State dir boleh berada di dalam working copy | `load_trusted_approval` menolak state dir di dalam repo (`trust_state_untrusted`); tes `test_trust_state_inside_the_working_copy_is_refused` | **DITUTUP** |
| D8-M3 | MED | TOCTOU: revisi repo bisa berubah antara pemeriksaan dan eksekusi | Ditunda — binding revisi tetap diperiksa sebelum `consume_approval`, jendela sempit; butuh lock/worktree terpisah | **DEFERRED** (bukan blocker TEST_ONLY) |
| D8-M4 | MED | Snapshot state dir menghidupkan ulang approval terpakai | Didokumentasikan di docs (limitations) + §7; butuh ledger bersama | **DEFERRED** |
| D8-M5 | MED | `instance.json` tanpa integritas | Didokumentasikan: memalsukan `instance.json` saja tidak cukup (approval mengikat instance ID dan ditandatangani) | **ACCEPTED (residual)** |
| D6-M1 | MED | Baca state via `lstat` lalu `read` (TOCTOU) | `_read_state_file()` membaca lewat `O_NOFOLLOW` + `fstat` satu deskriptor | **DITUTUP** |

Tidak ada HIGH/BLOCKER terbuka di dalam scope TEST_ONLY setelah koreksi di atas. HIGH D8-H1 hanya
tertutup terhadap ancaman *penulis berkas*; klaim "hanya owner yang bisa approve" **tidak** dibuat,
dan `PRODUCTION_TRUST` tetap **BLOCKED**.

---

## 6. Step 6 — Rekonsiliasi gap (4 MED/LOW sebelumnya vs daftar terbuka)

| Gap sebelumnya | Status sekarang | Klasifikasi |
|---|---|---|
| F3 — artefak `runs/*` gitignored, bukti tidak ikut PR | **masih** (`.gitignore:67 /runs/*`) | Deferred (bukan blocker keamanan; bukti reproducible via `smoke.py`) |
| F7 — `smoke.py` hidup di `runs/` yang gitignored | **masih** | Deferred (driver demonstrasi, bukan bagian produk) |
| Gap #2 — replay lintas-clone | **DITUTUP** (T3 + state dir di luar repo) | Closed |
| Gap #3 — HMAC key terlihat executor | **DIBATASI**: handshake tidak lagi diklaim sebagai bukti eksekusi; label & `attestation` eksplisit | Closed (klaim), residual: handshake tetap bukan attestation |
| Gap #4 — `passed: 1` sintetis | **DITUTUP** untuk jalur nyata (JUnit), residual schema BE-SP-12 untuk eksekusi tanpa tes | Closed (dengan laporan schema terpisah) |
| Gap #1 — jalur produksi belum pernah E2E | **masih** (by design) | Blocker untuk `PRODUCTION_TRUST`, bukan untuk scope TEST_ONLY |
| Gap #5 — kontrol positif lewat `main()` | **DITUTUP** (`01-positive` lewat `main()` + 15 tes e2e) | Closed |
| Gap #6 — 1 dari 26 kapabilitas | **masih** | Deferred (di luar C1-06) |
| Gap #7 — `runs/INDEX.md` jalur tulis | **masih** | Deferred |

Tidak ada temuan **HIGH/BLOCKER** terbuka di dalam kapabilitas yang diklaim siap untuk eksekusi
tepercaya — karena kapabilitas itu **tidak** diklaim siap; yang diklaim hanya scope TEST_ONLY.

---

## 7. Risiko sisa (jujur)

1. **Anchor masih same-UID.** Pin `SDB_APPROVAL_PUBKEY_SHA256` menutup ancaman penulis berkas, tetapi
   proses yang berjalan sebagai owner dapat mengganti kunci, re-sign record, dan mengubah environment
   sekaligus. Produksi butuh verifier milik root/HSM/KMS atau approval service terpisah.
2. **Attestation tetap self-reported.** JUnit ditulis oleh child yang dieksekusi; router hanya memeriksa
   konsistensi internal (PASS vs laporan). Executor yang berbahaya bisa menulis laporan hijau tanpa
   mengerjakan tugas. Diperlukan attestation independen (mis. verifier terpisah dengan kunci berbeda).
3. **State dir lokal.** Replay ledger bersifat per-mesin; host yang di-reimage, snapshot state dir yang
   dipulihkan, atau mesin kedua dengan state dir baru dapat memakai ulang approval yang sudah dipakai.
   Produksi butuh ledger append-only bersama antar-host.
4. **Kunci privat approval berada di mesin yang sama** (state dir 0700) untuk scope test. Produksi butuh
   HSM/KMS atau approval service; kunci privat tidak boleh dapat dibaca builder.
5. **Issuer adalah string allowlist** yang diikat ke fingerprint kunci, bukan identitas terautentikasi perangkat.
6. **TOCTOU revisi.** HEAD diperiksa sebelum eksekusi; repo yang berubah di antara pemeriksaan dan
   eksekusi tidak terdeteksi (jendela sempit, belum ada lock/worktree terpisah).
7. **Schema BE-SP-12** belum dapat merepresentasikan eksekusi tanpa tes secara jujur (lihat §3).

---

## 8. FINAL VERDICT

| Aspek | Verdict |
|---|---|
| `OFFLINE_DISPATCH` | **PASS** — task sintetis lewat `main()` nyata, offline, fail-closed |
| `REPLAY_PROTECTION_TEST_ONLY` | **PASS** — T1–T9 lulus dengan kunci sintetis di state dir terisolasi |
| `PRODUCTION_TRUST` | **BLOCKED** — tidak ada independent trust anchor / durable replay store; `PRODUCTION_TRUST_ENABLED=False` |
| `EVIDENCE_AUTHENTICITY` | **PASS (terbatas)** — angka nyata dari laporan eksekusi, PASS-vs-laporan diperiksa, `attestation=self_reported`; attestation independen belum ada |
| `MAKE_CHECK` | **PASS** |
| `LIVE_HERMES` | **NOT_STARTED** |

`SDB_DONE_POLICY=attested` · `SDB_EVIDENCE_MODE=legacy` · `release_authorization=NOT_AUTHORIZED` ·
`evidence_level=AGENT_REPORTED` · `review_status=NOT_REVIEWED`

Commit: satu commit lokal (test-only), **bukan** `INTEGRATED_VERIFIED`, **bukan** production-ready.
Tidak ada push, merge, atau deploy.
