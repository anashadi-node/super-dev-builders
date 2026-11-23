# SDB — C1-06 Trusted Runtime: Hasil Eksekusi & Verdict

**Tanggal:** 2026-11-21 (WIB) · **Branch:** `feat/c2b2g-ci-hardening` · **HEAD:** `c30a506` (tidak ada commit baru)
**Mode:** `CHANGE_ONLY` — delta kerja di working tree, belum di-commit, tidak di-push.
**Revisi laporan:** 2 — menutup temuan review independen D6/D8 post-fix (lihat §9).

---

## 1. Verdict

**PASS_WITH_GAPS (terkendali).** Satu task sintetis benar-benar dieksekusi lewat entrypoint dispatcher
`scripts/sdb_capability_router.py::main()` di repo git scratch, dengan sandbox `bwrap`, adapter executor
**stub terkontrol** (`_test_only=True`), dan artefak invocation + evidence BE-SP-12 yang divalidasi ulang
di tempat.

**Bukan** eksekusi Hermes/model live, **bukan** panggilan provider berbayar, **bukan** bukti produksi.
`release_authorization` evidence = `NOT_AUTHORIZED`, `evidence_level` = `AGENT_REPORTED`,
`review_status` = `NOT_REVIEWED`. Hasil ini tidak dapat dipakai sebagai otorisasi rilis.

Kriteria 1, 2, 4–11 punya bukti mesin lewat `main()`. **Kriteria 3 tetap LEMAH**: executor yang benar-benar
dijalankan adalah stub test-only; pin executor produksi hanya dibuktikan non-eksekusi (§6, §10 butir 1).

---

## 2. Ruang lingkup & batas yang dipatuhi

| Batas | Status | Bukti |
|---|---|---|
| Tanpa push / merge / deploy | Patuh | `git log -1` = `c30a506`; `git status` = 3 M + 3 ??; tanpa remote update |
| Tanpa panggilan provider live / LLM berbayar | Patuh | executor = stub lokal (`adapter._test_only is True`, `test:107`); binary Hermes asli tak pernah dieksekusi (`test:299-311`) |
| Tanpa rahasia terbaca/tertulis | Patuh (diuji, denylist) | probe kredensial `test:261-268` mencakup 6 nama kredensial + `config.yaml` + `sessions/`, `logs/`, `memories/`, `cache/`, `state/`; artefak hanya memuat digest nonce (`test:270-286`) |
| Tanpa perluasan scope di luar C1-06 | Patuh | 4 berkas kode/tes disentuh (§3) + 2 laporan |

---

## 3. Delta kode (post-fix)

| File | Perubahan | sha256 (16) |
|---|---|---|
| `scripts/sdb_capability_router.py` | +60/−6: blok `routing` non-secret; `--unshare-net` (test-only); `PROFILE_SECRET_FILES` + `PROFILE_PRIVATE_FILES`/`PROFILE_PRIVATE_DIRS` di-shadow/di-tmpfs; `_check_network_policy()` fail-closed (`routing_inconsistent`); `executor_kind`/`network_policy` **direkam** di `ExecutionResult` (tidak lagi diturunkan dari argv); `validate_payload` tanpa `head=`; `test_command` = label handshake eksplisit | `5e583202d5d9e32e` |
| `scripts/sdb_capability_trust.py` | +7/−1: `FORBIDDEN_ROOT_HEADS` = `scripts, registry, runs, tests, reports, agents, workflows, skills, platform, integrations, .github, Makefile, pyproject.toml, .gitleaks.toml` | `288fe907718ae1ef` |
| `tests/test_capability_routing.py` | +104/−4: nonce acak per approval (`uuid4`), loop denylist membaca `trust.FORBIDDEN_ROOT_HEADS`, 3 tes baru (sandbox produksi, `routing_inconsistent`, pin digest dua arah) | `8a332d30e796ce8a` |
| `tests/test_capability_e2e_dispatcher.py` (baru, 322 baris, **15 tes**) | Harness E2E lewat `main()`; probe kredensial + dir privat; assert `test_command` handshake | `13375c4907b2c1a2` |

Bukti run terekam (gitignored, `/runs/*`): `runs/capability/c1-06/{smoke.py,result.json,artifacts/}`.

---

## 4. Jalur yang dibuktikan (bukan disimulasikan)

```
task.json → main() → TaskPack.from_mapping (validasi) → load_routing_registry (kapabilitas)
→ load_trusted_approval + consume_approval (single-use) → _verify_executor (pin + mode)
→ _sandbox_argv (bwrap: unshare-all, ro repo, rw hanya allowed_write_roots, unshare-net)
→ _check_network_policy (argv vs mode adapter, fail-closed)
→ adapter.production() → stub child → exit code nyata → verifikasi kontrak hasil
→ revision binding → evidence BE-SP-12 → validate_payload (HEAD di-resolve sendiri) → verdict
```

---

## 5. Bukti eksekusi terekam (`result.json`, generated 2026-11-21T15:26:22Z)

| Kasus | exit dispatcher | verdict (`stdout`) | validator (`execution_status` / `acceptance_status`) | artefak |
|---|---|---|---|---|
| `01-positive` | 0 | `INTEGRATION_TESTED_NONPRODUCTION` | `PASS` / `INFORMATIONAL_ONLY` | 2 |
| `02-forged-result` | 1 | `FAIL` | `FAIL` / `NOT_ACCEPTED` | 2 |
| `03-untrusted-approval` | 2 | — | — | **0** |
| `04-nonzero-exit` | 1 | `FAIL` | `FAIL` / `NOT_ACCEPTED` | 2 |
| `05-credential-network-probe` | 0 | `INTEGRATION_TESTED_NONPRODUCTION` | `PASS` / `INFORMATIONAL_ONLY` | 2 |

Total artefak: **4 kasus × 2 berkas = 8 berkas** (kasus `03` nol artefak — penolakan terjadi sebelum
penulisan; bukan "5/5").

| Berkas (relatif `runs/capability/c1-06/`) | sha256 (12) | bytes |
|---|---|---|
| `artifacts/01-positive/…30a2da711ff1.evidence.json` | `3d1408f39b9b` | 812 |
| `artifacts/01-positive/…a01f37e54b76.invocation.json` | `0c3fee0d4ff8` | 2426 |
| `artifacts/02-forged-result/…0bdf146a83fd.evidence.json` | `6d43c14818d6` | 812 |
| `artifacts/02-forged-result/…4129cb7189a5.invocation.json` | `2057eceab110` | 2409 |
| `artifacts/04-nonzero-exit/…0389dec9627a.evidence.json` | `91ad1460e6cd` | 812 |
| `artifacts/04-nonzero-exit/…46b0f98a3371.invocation.json` | `e8b6c580d808` | 2401 |
| `artifacts/05-credential-network-probe/…f8049a10a631.evidence.json` | `8eaceea48d9f` | 812 |
| `artifacts/05-credential-network-probe/…bc5592f50cad.invocation.json` | `6e15a410e7dd` | 2426 |

`result.json` sha256 `4033c1c00eceb12b…` · `smoke.py` sha256 `8c5515f6e198d9ff…`.

Catatan pembacaan: `invocation.exit_code` = kode proses (0/7), verdict ada di `status`; evidence tidak
memuat `execution_status`/`acceptance_status` (itu keluaran validator, bukan field payload). Kasus `04`
memuat `exit_code: 7` di invocation **dan** evidence.

---

## 6. Matriks 14 kriteria penerimaan

| # | Kriteria | Bukti (file:baris) | Status |
|---|---|---|---|
| 1 | Task Pack tervalidasi | `test_capability_e2e_dispatcher.py:99-105` (positif) + `:206-215` (goal 5000 char → exit 2, `task_goal_too_long`, nol artefak) | TERBUKTI |
| 2 | Kapabilitas terdaftar terpilih | `:218-228` (`BE-SP-99` → `task_route_invalid`, approval sengaja dibuat cocok agar penolak hanya registri) | TERBUKTI |
| 3 | Executor + profil terotorisasi | profil: `:273-285` (`routing.profile == cc-builder`, dari `load_routing_registry`); pin: `test_capability_routing.py:776-793` (digest cocok → fd diterima; digest salah → `digest differs`), sandbox produksi `:742-752`; **tetapi** executor yang dieksekusi E2E = stub `_test_only` | **LEMAH** |
| 4 | Controlled adapter dipanggil | `:106` (`calls["production"] == 1`) + `:112-116` (tepat 1 invocation, `exit_code 0`, `PASS_VERIFIED_SUBSCOPE`, `verified_result True`) | TERBUKTI |
| 5 | Batas sandbox ditegakkan | `:244-258` (tulis ke `repo/scripts/c1-06-escape.txt` gagal, file tak ada di host) + `:261-268` (kredensial/dir privat buta + TCP 1.1.1.1:443 gagal) + `test_capability_routing.py:333-375` (argv & kontrol positif) | TERBUKTI |
| 6 | Exit code aktual tertangkap | `:231-241` (`invocation.exit_code == 7`, `status FAIL`, `payload.exit_code == 7`, exit dispatcher 1) | TERBUKTI |
| 7 | Artefak eksekusi dihasilkan | `:112-121` (1 invocation + `evidence_path` ada, schema `sdb.capability.evidence/1`) | TERBUKTI |
| 8 | Evidence BE-SP-12 tervalidasi | `:122-132` (`validate_payload(payload, repo=repo)` tanpa `head=` → HEAD di-resolve independen) + router kini juga tanpa `head=` (`_write_evidence`) | TERBUKTI |
| 9 | Eksekusi gagal tak boleh PASS | `:140-155` (`execution_status FAIL`, `acceptance_status != PASS`, `failed: 1`) | TERBUKTI |
| 10 | Tanpa perluasan izin | `:165-174` (`approval_scope_mismatch`) + `:176-184` (replay → exit 2) + `test_capability_routing.py:663-681` (semua `FORBIDDEN_ROOT_HEADS` ditolak, `execute()` re-cek) | TERBUKTI |
| 11 | Diagnosis routing dari metadata non-secret | `:273-285` (`profile`, `executor_kind`, `network_policy`, digest nonce 64 hex; nonce mentah & `challenge_nonce` absen) + blok `routing` di 4/4 invocation, digest **berbeda per kasus** | TERBUKTI (batas: `provider`/`model` tak ada) |
| 12 | Review delta D6/D8 + `make check` | D6 `PASS_WITH_GAPS`, D8 `SECURE_WITH_GAPS` (post-fix); `make check` exit 0 (§7) | TERBUKTI dengan sisa gap §10 |
| 13 | Laporan hasil ditulis | berkas ini | ADA |
| 14 | Tanpa push/merge/deploy/provider live | §2 | TERBUKTI |

---

## 7. Gerbang (dijalankan ulang di HEAD kerja, bukan hasil lama)

| Gate | Hasil |
|---|---|
| `make check` | **exit 0** — `lint: All checks passed!`, `registry_lint: PASS`, `skill drift: 136/136 OK`, `hygiene: PASS (0 FAIL, 3 WARN / 604 berkas)`, `pack: PASS`, `docs_lint: PASS` |
| `pytest tests skills integrations` | **1002 tes, 0 gagal, 0 error, 0 skip** (`--junitxml`, otoritatif) |
| `pytest tests/test_capability_routing.py` | 47 passed |
| `pytest tests/test_capability_e2e_dispatcher.py` | 15 passed |
| `pytest tests/test_capability_evidence.py` | 57 passed |
| `ruff check` (4 berkas tersentuh) | All checks passed |
| `runs/capability/c1-06/smoke.py` | exit 0, 5 kasus sesuai harapan |

Angka tes diambil dari XML junit, bukan dari hitungan titik output `-q` (metrik itu menyesatkan).

---

## 8. Diagnosis routing model (metadata non-secret saja)

Dipersist mesin per eksekusi (4/4 artefak invocation yang ada):

```json
{"approval_nonce_sha256": "148a6098…", "executor_kind": "test_only",
 "network_policy": "isolated", "profile": "cc-builder"}
```

Digest per kasus: `148a6098` (01), `93760f65` (02), `789c5834` (04), `10d60bff` (05) — **berbeda**, karena
nonce kini diacak per approval (sebelumnya konstanta fixture `c103-test-nonce-0001` → digest identik).

Yang terbukti dari metadata ini: profil `cc-builder`, executor test-only (bukan produksi), jaringan
terisolasi, dan satu approval dapat dibedakan dari approval lain. `provider`/`model` **tidak** muncul
karena adapter test-only tidak memanggil model — fakta, bukan kekurangan bukti.

`executor_kind`/`network_policy` kini **direkam** saat konstruksi `ExecutionResult` dan diverifikasi
terhadap argv sandbox (`_check_network_policy` → `routing_inconsistent`), bukan lagi disimpulkan dari
keberadaan flag yang sama yang seharusnya diawasi.

Berkas `runs/capability/c1-06/model-routing-diagnosis.json` tetap **ONE_OFF_MANUAL**: tidak ada generator
di repo, tidak reproducible, tidak terikat run ini.

---

## 9. Review independen D6 & D8 (post-fix) — temuan → status

| Temuan | Tingkat | Status |
|---|---|---|
| D6 #1 `router.py:522` masih menyerahkan `head=` (validasi tautologis) | MED | **TERTUTUP** — `head=` dibuang, HEAD di-resolve validator |
| D6 #2 kriteria 3 hanya diuji negatif | MED | **TERTUTUP** — `test_verify_executor_pins_digest_in_both_directions` (positif + negatif) |
| D6 #3 tak ada kontrol positif sandbox lewat `main()` | MED | **TERBUKA** (§10 butir 5) |
| D6 #4 seam test-only tak dijaga `main()` | MED | **TERBUKA** (§10 butir 5) |
| D6 #5 `approval_nonce_sha256` = digest konstanta | MED | **TERTUTUP** — nonce `uuid4` per approval; 4 digest berbeda |
| D6 #6 `executor_kind`/`network_policy` diderivasi dari argv | MED | **TERTUTUP** — direkam + dicek fail-closed |
| D6 #7 arsip tak tervalidasi independen | MED | **SEBAGIAN** — revalidasi arsip bersifat hash-level; `revision` tidak bisa dicocokkan ulang ke HEAD repo asal |
| D6 #8 probe menyamakan "absen" vs "ter-shadow kosong" | LOW | **TERTUTUP sebagian** — stub kini juga menandai direktori non-kosong; belum ada canary berisi |
| D6 #9 tes "tak menyentuh binary Hermes" hanya banding path | LOW | **TERTUTUP** — `test:299-311` membandingkan `sandbox_argv`/fd stub |
| D6 #10 angka `make check` tak terverifikasi reviewer | LOW | **TERTUTUP** — angka §7 dapat direproduksi dari perintah yang sama |
| D6 overclaim "5/5 artefak" | — | **DIPERBAIKI** — §5 menyatakan 4 kasus × 2 berkas |
| D6 overclaim "hanya 3 file" | — | **DIPERBAIKI** — §3 mendaftar 4 berkas |
| D8 #1 cabang produksi nol eksekusi test | MED | **SEBAGIAN** — `_sandbox_base(production=True)` + pin digest dua arah kini diuji; `main()` produksi tetap tak dieksekusi (§10 butir 1) |
| D8 #2 evidence mengklaim test yang tak jalan | MED | **SEBAGIAN** — `test_command` = `handshake:hmac-sha256(handshake_value) [no task-effect verification]`; masih `passed: 1` (skema BE-SP-12 mewajibkan `total > 0`) |
| D8 #3 PASS bisa dipalsukan executor (kunci HMAC di prompt) | MED | **TERBUKA** (§10 butir 3) |
| D8 #4 replay lintas klon (ledger `.git/…`) | MED | **TERBUKA** (§10 butir 2) |
| D8 #5 `config.yaml`, `sessions/`, `logs/`, `memories/` terbaca | MED | **TERTUTUP** — `PROFILE_PRIVATE_FILES`/`PROFILE_PRIVATE_DIRS` di-shadow `/dev/null` & tmpfs; probe diperluas; docstring dikoreksi |
| D8 #6 denylist write-root enumeratif & sempit | MED | **TERTUTUP sebagian** — 14 head termasuk `.github`, `Makefile`, `pyproject.toml`, `.gitleaks.toml`; masih enumeratif (allowlist per-task belum) |
| D8 #7 `network_policy` self-derived | LOW-MED | **TERTUTUP** — rekaman keputusan + `routing_inconsistent` |
| D8 #8 F3: artefak gitignored | LOW | **TERBUKA** (§10 butir 6) |
| D8 #9 F7: `smoke.py` hidup di `runs/` | LOW | **TERBUKA** (§10 butir 7) |
| D8 #10 `runs/INDEX.md` trackable | LOW | **DITERIMA** — tidak ada jalur yang menulis ke sana |

---

## 10. Gap residual (jujur — belum tertutup)

1. **Jalur produksi tidak pernah dieksekusi E2E.** Pin uid/mode/digest kini diuji dua arah dan sandbox
   produksi dibangun di tes, tetapi eksekusi nyata dengan binary Hermes asli tetap belum ada. Estimasi
   0,5 hari + otorisasi.
2. **Replay ledger per-clone.** Marker single-use di `.git/sdb-capability-approval-replay/` tidak ikut
   `git clone`; nonce approval committed plaintext. Estimasi 2–3 jam (ledger ke `$XDG_STATE_HOME` atau
   `git notes` + `consumed_at`).
3. **PASS = handshake HMAC**, bukan efek task: kunci ada di prompt, jadi executor adversarial bisa
   mencetak PASS. Label sudah eksplisit, mekanisme belum diperbaiki. Estimasi 2 jam.
4. **`passed: 1` masih disintesis** karena skema BE-SP-12 mewajibkan `total > 0`; label
   `handshake_only` ada di `test_command`, bukan field terstruktur. Estimasi 1 jam (tambah field
   `verification_kind` di skema + migrasi validator).
5. **Kontrol positif lewat `main()` belum ada** (`roots=()` di semua kasus E2E); seam adapter test-only
   belum dijaga di `main()` (butuh switch nonproduksi eksplisit). Estimasi 3–4 jam.
6. **Artefak bukti gitignored** (`/runs/*`) → PR hanya membawa klaim + hash. Estimasi 1 jam (manifest
   hash teredaksi di `reports/`).
7. **`smoke.py` hidup di direktori data** (`runs/…`, gitignored) dan menduplikasi harness tes. Estimasi
   1 jam (pindah ke `scripts/capability_smoke.py`).
8. **Cakupan 1 dari 26 kapabilitas**, 1 profil (`cc-builder`). Estimasi 1 hari untuk smoke matriks.

---

## 11. Satu langkah berikutnya (paling bernilai)

Tutup **§10 butir 2** (replay lintas-clone) karena itu satu-satunya gap yang membuat klaim keamanan
berhenti di batas satu clone. Setelah itu butir 5 (kontrol positif + penjaga seam di `main()`), baru
layak mengusulkan commit C1-06 — tetap tanpa push, menunggu approval Mas Anas.
