# SDB — NEW SESSION CONTINUATION RESULT

**Tanggal eksekusi:** 2026-11-20 (WIB)  
**Mode:** BROWNFIELD_RECOVERY → CHANGE_ONLY  
**Sesi:** NEW (reconciliation, bukan audit ulang)  
**Policies dipertahankan:** `SDB_DONE_POLICY=attested`, `SDB_EVIDENCE_MODE=legacy`  
**Otorisasi aktif:** PUSH=NO · MERGE=NO · DEPLOY=NO · OS_CHANGES=NO · ACCESS_CHANGES=NO · BE_SP12_IMPLEMENTATION=NO

Legenda bukti: **VERIFIED_PRIMARY** (dibaca langsung dari git/GitHub/berkas hari ini) · **HERMES_REPORTED** (laporan sesi sebelumnya, revision-bound) · **PROPOSED** · **UNKNOWN** · **BLOCKED**.

---

## 1. HEAD dan branch aktual — VERIFIED_PRIMARY

| Item | Nilai terukur | Perintah |
|---|---|---|
| Branch | `feat/c2b2g-ci-hardening` | `git rev-parse --abbrev-ref HEAD` |
| HEAD penuh | `cc6a5735…` (`cc6a573`) | `git rev-parse HEAD` |
| Remote master | `6f1cfc28…` (`6f1cfc2`) — sama dengan `origin/master` lokal | `gh api .../commits/master` |
| Commit keluar | **17** (`origin/master..HEAD`) | `git rev-list --count origin/master..HEAD` |
| Leluhur | `89fbe62` dan `7bca894` keduanya ancestor HEAD | `git merge-base --is-ancestor` |
| Upstream branch | **tidak ada** (branch belum pernah di-push) | `git rev-parse @{u}` → fatal |
| Working tree | bersih saat reconciliation (`git status --porcelain` kosong) | — |
| SSH auth | OK, read-only (`git ls-remote --heads origin` → 3 branch remote) | — |

Kecocokan nilai rujukan direktif: `cc6a573` **cocok persis**; `89fbe62` **cocok** sebagai leluhur; `6f1cfc2` **cocok** dengan master GitHub saat ini.

Selisih yang perlu dicatat (bukan konflik): laporan lama menyebut `190 commits scanned` pada pemindaian rahasia. Hari ini `--all` memindai **192 commit** — tepat +2 karena dua commit dokumen (`ea5753b`, `cc6a573`) dibuat setelah titik eksekusi laporan itu. Konsisten, bukan drift.

## 2. Baseline reconciliation — **BASELINE_CONSISTENT**

Tidak ada konflik materiil: HEAD sama dengan yang dilaporkan, branch sama, tree bersih, ancestry utuh, tidak ada commit hilang/dobel, tidak ada perubahan liar.

Satu hal yang berubah **setelah** reconciliation: berkas laporan ini sendiri ditulis di `reports/SDB_NEW_SESSION_CONTINUATION_RESULT.md` (untracked). Jadi status tree sekarang = 1 berkas untracked, HEAD tetap `cc6a573`. Push apa pun nanti akan mengirim `cc6a573` **tanpa** berkas ini kecuali Owner memutuskan untuk meng-commit-nya.

## 3. GitHub publication readiness — **PUSH_READY** (push) / **MERGE BLOCKED**

| Aspek | Status | Bukti |
|---|---|---|
| Push branch (create remote branch) | **SIAP** — tidak ada penolakan teknis | SSH auth OK; nama branch belum ada di remote |
| PR creation | Siap bila diotorisasi | `origin` = `git@github.com:anashadi-node/super-dev-builders.git` |
| Merge ke master | **BLOCKED** oleh 2 aturan proteksi | lihat di bawah |
| Klaim "GitHub CI passed" | **UNKNOWN** — tidak boleh diklaim dari tes lokal | tidak ada run untuk SHA ini |

Dua blocker merge yang **baru terukur sesi ini** (tidak tercatat di laporan C2-B2G):

1. **`required_signatures.enabled = true`**, dan `enforce_admins.enabled = true` → semua 17 commit keluar **TIDAK ditandatangani**: `git log --format='%G?' origin/master..HEAD | sort | uniq -c` → `17 N`. Dengan proteksi ini, merge ditolak GitHub.
2. **`required_approving_review_count = 1`** pada repo yang hanya punya **1 collaborator** (`anashadi-node`, admin). `enforce_admins=true` → admin tidak bisa bypass, dan penulis tidak boleh menyetujui PR-nya sendiri.

Proteksi lain yang terukur (jangan diubah): `strict=true`, required status check `check (lint + registry + test + drift)` (app 15368), `required_linear_history=true`, `allow_force_pushes=false`, `allow_deletions=false`, `required_conversation_resolution=true`, `require_code_owner_reviews=false`.

## 4. CI security gate status — 8 butir

| # | Butir | Status | Bukti (VERIFIED_PRIMARY kecuali ditandai) |
|---|---|---|---|
| 1 | Pemindaian full-history punya riwayat git | **PASS** | `ci.yml:47` `fetch-depth: 0`; `persist-credentials: false`; uji `test_checkout_mengambil_seluruh_riwayat` lulus |
| 2 | Secret scanner fail-closed | **PASS** | `ci.yml:83-84` gagal bila gitleaks tidak ada / versi ≠ 8.28.0; `make secrets` sengaja tidak dipakai (uji `test_gerbang_rahasia_tidak_memakai_make_secrets`) |
| 3 | Laporan hilang/invalid ditolak | **PASS** | `ci.yml:92` (`test -s`), `:100-104` (harus array JSON + semua `Secret` ter-redact); uji `test_gerbang_gagal_bila_laporan_tidak_dihasilkan`, `..._memuat_nilai_tidak_ter_redact` lulus |
| 4 | Nilai rahasia tidak bocor via artefak CI | **PASS** | `--redact` pada `ci.yml:86`; artefak hanya `junit.xml`, `gitleaks.json`, `meta.json` (`ci.yml:205-208`); uji `test_junit_tidak_memuat_data_pribadi_atau_kredensial` lulus |
| 5 | Checksum scanner = sumber terpercaya | **PASS** | Pin `a65b5253…a840eb` (`ci.yml:69`) **identik** dengan `gitleaks_8.28.0_checksums.txt` resmi yang saya unduh hari ini dari `github.com/gitleaks/gitleaks/releases/download/v8.28.0` |
| 6 | Tidak ada eskalasi izin | **PASS** | `permissions: contents: read` (`ci.yml:27-28`); uji `test_permission_token_minimal`, `test_boundary_runner_dan_tidak_ada_trigger_berprivilege` |
| 7 | Required status check tidak berubah | **PASS** | Nama job `check` + `name: check (lint + registry + test + drift)` (`ci.yml:35-36`) = context wajib di proteksi master |
| 8 | Tidak ada rahasia/data privat baru dari commit keluar | **PASS** | `gitleaks detect --log-opts=origin/master..HEAD` → `17 commits scanned`, `no leaks found`, exit 0, laporan JSON `[]` (3 byte, non-kosong → `test -s` lolos) |

Uji kebijakan CI dijalankan ulang segar hari ini: `.venv/bin/python -m pytest tests/test_ci_workflow_policy.py -q` → **exit 0, 23 tes lulus**.

**Pemindaian rahasia tambahan (VERIFIED_PRIMARY, hari ini):** `gitleaks detect --config .gitleaks.toml --redact --baseline-path .github/gitleaks-baseline.json --log-opts="--all"` → **192 commit, 11,38 MB, `no leaks found`, exit 0**. Catatan kejujuran: hasil ini memakai **baseline 10 temuan teraudit** dan allowlist path di `.gitleaks.toml` (1 artefak pihak ketiga + 3 berkas fixture uji sintetis); berkas yang di-allowlist **tidak dipindai** — kompensasinya tetap `make secrets-raw`.

Reuse bukti regresi (diizinkan, sumber tidak berubah): laporan C2-B2G mencatat `866 passed, 0 failed` (HERMES_REPORTED). Validitasnya untuk HEAD sekarang dapat dipertahankan karena `git diff --name-only 89fbe62..HEAD` → **hanya** `reports/SDB_C2B2G_RELEASE_CANDIDATE_RESULT.md`. Nol berkas kode/tes/CI berubah setelah titik eksekusi itu, sehingga tidak ada alasan menjalankan ulang suite penuh. Ini **bukan** bukti bahwa GitHub CI lulus.

Hash berkas kebijakan yang dinilai (untuk rujukan beku):

```
3c065bd0e93d8109179e0bbb07e27ab423e878f9d7331072e8eeeb251cb9b75c  .github/workflows/ci.yml
b479b11f7e95339c0c2085df9109c12dcbdaa4ccd21364d0a7208728ff7f5b80  .github/CODEOWNERS
19550f366d817d372e72a0f6af50c98231540b4ed306135fc6b8c35d533b3abf  .github/gitleaks-baseline.json
a0f0ab82d52f7c0e4dae635c620bb99c173bae94719c939a7b8a36b777e1a27b  tests/test_ci_workflow_policy.py
5915d7158630eb15e40421d7fcaa9df73e77ecf64e5af3433d87be7cac3a719f  .gitleaks.toml
f42dd6936d0d81c4b45187eaf59d84023a1d49cf3c50e185fd48e7fe780841fa  docs/BE_SP12_EVIDENCE_CONTRACT.md
932eaf750eb929b2af65705715609af05213396a4c6e9182654444566ed434da  docs/RESTRICTED_BUILDER_C2B2M.md
```

### Temuan keamanan baru (perlu keputusan, bukan tindakan)

- **Repo GitHub berstatus PUBLIC** (`gh repo view … --json isPrivate,visibility` → `false`, `PUBLIC`). Catatan memori internal menyatakan repo ini PRIVATE. Perbedaan ini materiil: kebocoran historis yang dulu "terbatas" kini terbaca publik, dan `ROTASI_KREDENSIAL` menjadi lebih mendesak. Saya **tidak** mengubah visibilitas (ACCESS_CHANGES_APPROVED=NO).
- `.gitleaks.toml` memuat opsi yang **belum diambil**: menimpa aturan `sourcegraph-access-token` agar alternatif `[a-fA-F0-9]{40}` dibuang, sehingga allowlist path bisa dihapus. Ini mengubah kemampuan deteksi → butuh keputusan Owner.

## 5. CODEOWNERS governance — **BLOCKED**

- `gh api repos/.../collaborators?affiliation=all` → **tepat 1 akun**: `anashadi-node` (admin/maintain/push/triage). **VERIFIED_PRIMARY**
- `.github/CODEOWNERS` valid dan mencakup jalur kritis (`/.github/`, `.gitleaks.toml`, `scripts/sdb_*.py`, `scripts/release_check.py`, `scripts/did_validate.py`, `workflows/stages.yaml`, `registry/`, `platform/did_profiles.json`), dengan penjaga uji `test_codeowners_valid_dan_mencakup_jalur_kritis` → lulus.
- `require_code_owner_reviews=false` → berkas ini saat ini **belum menahan apa pun**, dan bahkan setelah di-merge ia hanya berlaku pada base branch.

**Prosedur bootstrap paling kecil dan aman (PROPOSED, butuh ACCESS_CHANGES_APPROVED):**

1. Undang **satu** akun kedua sebagai collaborator role **Write** (bukan admin, bukan maintain). Tanpa ini, semua langkah lain tidak bisa memenuhi syarat proteksi.
2. Merge CODEOWNERS ke master (butuh PR + approval — lihat blocker §3).
3. Baru aktifkan `require_code_owner_reviews=true`. Jangan ubah `strict`, required check, `required_linear_history`, atau `enforce_admins`.
4. Verifikasi dengan **PR negatif**: PR yang menyentuh `scripts/sdb_evidence.py` harus **tidak bisa** merge tanpa approval owner; PR yang hanya menyentuh `docs/*.md` tetap bisa dinilai normal. Gagal uji negatif → rollback flag.
5. Alternatif bila akun kedua tidak tersedia: **jangan** turunkan `required_approving_review_count` ke 0 (itu melemahkan gerbang, bukan bootstrap). Biarkan `require_code_owner_reviews=false` apa adanya dan catat sebagai risiko residual.

Catatan: mengaktifkan CODEOWNERS **sebelum** ada reviewer kedua akan membuat setiap PR — termasuk PR owner — tidak pernah mencapai status approved.

## 6. Restricted builder (A″) — **PACK READY, EKSEKUSI TIDAK DIIZINKAN**

| Item | Status |
|---|---|
| Pack dokumen + 4 skrip (`preflight/apply/verify/rollback.sh`) | ADA di repo (`docs/c2b2m/`, +`docs/RESTRICTED_BUILDER_C2B2M.md`, sha256 di §4) |
| `apply.sh`/`verify.sh`/`rollback.sh` pernah dijalankan | **TIDAK** — user sasaran belum ada: `id sdbbuild` → no such user |
| Perubahan OS/user/group/ACL/systemd | **TIDAK ADA** (dan tidak akan dilakukan sesi ini) |
| Dua kunci penolakan default | Ada: `SDB_B2M_APPLY=1` + `SDB_B2M_CONFIRM` (tanpa keduanya exit 2) |

**Prasyarat keamanan yang masih belum tertutup (BLOCKED sampai diputuskan):**

1. Keputusan Owner soal home workspace `/srv/sdb-workspace` — siapa pemilik direktori induk dan bagaimana builder mendapat akses tanpa menyentuh `/home/anashadi`.
2. Cara menjalankan `scripts/sdb_build_worker.py` sebagai `sdbbuild` (systemd unit vs `sudo -u` per proses). `verify.sh` 16 hanya membuktikan proses anak mewarisi UID, bukan bahwa worker bisa berjalan tanpa akses kredensial.
3. Ketiadaan kredensial: builder tidak boleh bisa membaca `~/.hermes` atau venv Owner — perlu bukti uji negatif nyata (`cat`/`stat` ditolak), bukan narasi.
4. Rollback belum pernah diuji terhadap sistem nyata (hanya idempoten secara desain).

## 7. BE-SP-12 — keputusan yang diusulkan (semua **PROPOSED**)

Kontrak yang diminta sudah ada seluruhnya di `docs/BE_SP12_EVIDENCE_CONTRACT.md` §2: `capability_id`, `revision`, `test_command`, `exit_code`, `test_results`, `artifact_refs`, `evidence_level`, `verification_timestamp`, `review_status` — plus aturan turunan yang mencegah "PASS dari teks agent" (`AGENT_REPORTED` tidak pernah PASS; `revision` wajib SHA 40 hex; artefak hilang/hash beda = REJECTED).

Status katalog: **BE-SP-12 tidak ada sebagai data mesin** hari ini (`grep -rn "BE-SP-" --include=*.yaml --include=*.json` → 0 hasil di luar dokumentasi). `registry/capability_pilot.yaml` dan `runs/capability/` **belum ada**. Sesuai direktif, blueprint 26 capability **tidak** dibuat ulang.

| ID | Usulan | Catatan penting |
|---|---|---|
| D-BE1 | Bukti runtime di `runs/capability/` | **KONFLIK dengan kontrak**: dokumen §3 menulis `reports/capability/<capability_id>/<sha>.json`. Dan `.gitignore:67 /runs/*` membuat `runs/` **tidak masuk git**, sedangkan `reports/capability/` **masuk git**. Pilihan menentukan apakah bukti bisa diaudit dari repo atau hanya dari mesin/artefak CI. Rekomendasi saya: `runs/capability/` untuk runtime (tidak di-commit) + unggah sebagai CI artifact `capability-evidence-<sha>`; jangan commit keluaran mesin ke repo. Butuh keputusan Owner. |
| D-BE2 | `registry/capability_pilot.yaml` sebagai registry pilot machine-readable, namespace siap 26 entri, ID lama tidak ditimpa | Sesuai kontrak §1/§3. Boleh dibuat saat implementasi. |
| D-BE3 | PASS bersifat informatif sampai ada acceptance independen | Sesuai kontrak §5.3. Konsekuensi: PASS **tidak boleh** dipakai sebagai merge gate sampai ada reviewer independen (dan saat ini reviewer kedua **tidak ada**). |

Pemisahan level yang wajib dijaga (jangan dipromosikan otomatis): **test execution** (`exit_code`, `test_results`) ≠ **capability acceptance** (`review_status`) ≠ **independent verification** (`evidence_level: INDEPENDENT_REVIEW`) ≠ **release authorization** (tetap keputusan Owner).

## 8. Paket implementasi terbatas berikutnya (PROPOSED, belum dijalankan)

**Sasaran 1 kalimat:** "BE-SP-12 selesai bila `sdb_capability_evidence.py` dapat memvalidasi 1 evidence BE-SP-12 nyata dan menolak 6 bentuk evidence cacat, tanpa mengubah 19 tahap workflow."

| Komponen | Isi |
|---|---|
| Berkas baru (hanya ini) | `scripts/sdb_capability_evidence.py` (CLI `validate`, `record`), `registry/capability_evidence.schema.json` (JSON Schema 2020-12, `additionalProperties:false`), `registry/capability_pilot.yaml` (1 entri: `BE-SP-12`), `tests/test_capability_evidence.py` |
| Berkas terlarang | `workflows/stages.yaml` (19 tahap, terverifikasi hari ini), `agents/*.yaml`, `registry/skills.yaml`, `platform/did_profiles.json`, `scripts/release_check.py`, `Makefile` |
| Tes minimum | T1 evidence valid → PASS · T2 `exit_code:1` → FAIL · T3 `review_status` hilang → REJECTED · T4 sha256 artefak salah → REJECTED · T5 `revision` ≠ HEAD → REJECTED · T6 `AGENT_REPORTED` → tidak pernah PASS · T7 `capability_id` tak terdaftar → REJECTED · T8 `passed+failed+skipped != total` → REJECTED · T9 suite existing tetap lulus · T10 hash `workflows/stages.yaml` tidak berubah |
| Gerbang penerimaan | T1–T10 hijau + `make lint` + `pytest tests/test_capability_evidence.py` (log nyata) + hash `stages.yaml` identik sebelum/sesudah |
| Estimasi | 1 sesi terbatas (≈3–4 jam kerja), tanpa perubahan OS, tanpa agent baru |
| Yang **tidak** termasuk | Promosi PASS jadi merge gate, pembuatan katalog 26 entri, integrasi `release_check.py`, perubahan Makefile |

## 9. Approval Owner yang dibutuhkan (persis)

| # | Keputusan | Untuk apa | Efek bila tidak diberikan |
|---|---|---|---|
| A1 | `PUSH_APPROVED=YES` untuk SHA `cc6a5735…` (17 commit) | buat branch remote + 1 Draft PR | tetap lokal, PUSH_READY |
| A2 | Strategi tanda tangan commit: (a) setup SSH signing lalu re-sign 17 commit lokal (menulis ulang riwayat branch), atau (b) **squash merge** via GitHub UI (commit squash ditandatangani GitHub, tanpa rewrite) | memenuhi `required_signatures` | merge ditolak GitHub |
| A3 | `ACCESS_CHANGES_APPROVED=YES` + identitas akun kedua (Write) | memenuhi `required_approving_review_count=1` dan mengaktifkan CODEOWNERS | PR tidak bisa merge; CODEOWNERS tetap dekoratif |
| A4 | Keputusan D-BE1: `runs/capability/` (tidak di-commit) vs `reports/capability/` (masuk git) | paket BE-SP-12 | implementasi tidak boleh mulai |
| A5 | `BE_SP12_IMPLEMENTATION_APPROVED=YES` untuk allowlist §3 | mulai coding BE-SP-12 | status tetap NOT_STARTED |
| A6 | Visibilitas repo: tetap PUBLIC atau dikembalikan PRIVATE, dan prioritas rotasi kredensial | risiko paparan historis | risiko diterima tanpa keputusan tercatat |
| A7 | `OS_CHANGES_APPROVED=YES` bila A″ akan dieksekusi (butuh user `sdbbuild`, workspace, keputusan systemd) | restricted builder | pack tetap READY_FOR_OWNER_APPROVAL |

## 10. Ringkasan status dan batasan

| Butir | Hasil |
|---|---|
| Baseline | **BASELINE_CONSISTENT** |
| Push | **PUSH_READY** (17 commit, tree bersih sebelum laporan ini ditulis) |
| Merge | **BLOCKED** — commit tak bertanda tangan + reviewer kedua tidak ada |
| GitHub CI | **UNKNOWN** — belum pernah jalan untuk `cc6a573`; jangan diklaim lulus |
| Gerbang rahasia | PASS (gitleaks 8.28.0, checksum cocok sumber resmi, 192 commit, 0 temuan, laporan ter-redact) |
| CODEOWNERS | **BLOCKED** (1 collaborator) — prosedur bootstrap disiapkan |
| Restricted builder | Pack siap, **BLOCKED** (tanpa izin OS; 4 prasyarat terbuka) |
| BE-SP-12 | **NOT_STARTED**; kontrak siap; 3 keputusan usulan + 1 konflik path |
| Telemetri token/biaya | **NOT_MEASURED** (tidak ada telemetri pemakaian di sesi ini) |

Yang **tidak** dilakukan sesi ini (sesuai direktif): tidak ada push, tidak ada PR, tidak ada merge, tidak ada force-push, tidak ada perubahan branch protection, tidak ada perubahan user/grup/ACL/systemd, tidak ada `apply.sh`, tidak ada implementasi BE-SP-12, tidak ada penghapusan data, tidak ada `verified` activation.

**FINAL STATUS: `PUSH_READY`** — dengan `MERGE_BLOCKED` (A2/A3) dan `NEEDS_DECISION` (A4/A5/A6).
