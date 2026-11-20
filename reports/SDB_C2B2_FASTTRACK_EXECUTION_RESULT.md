# SDB_C2B2_FASTTRACK_EXECUTION_RESULT

**Baseline:** `71aa30b4c014f96ff432f7aa7bea1ed6f2ef0618` (branch `master`)
**Branch kerja:** `feat/c2b2g-ci-hardening` — **lokal, belum di-push**
**Tanggal eksekusi:** 2026-11-20 (WIB)
**Kebijakan tetap:** `SDB_DONE_POLICY=attested`, `SDB_EVIDENCE_MODE=legacy`

Status ringkas (label dipakai ketat):

| Item | Status |
|---|---|
| C2-B2G — CI hardening (kode + tes) | `PASS_VERIFIED` (lokal) |
| C2-B2G — berjalan di runner GitHub | `NOT_STARTED` (push belum diizinkan) |
| C2-B2G-B — penegakan CODEOWNERS | `BLOCKED` (tidak ada reviewer independen) |
| C2-B2M — execution pack restricted builder | `PASS_DOCUMENT` + preflight `PASS_VERIFIED`; apply `NOT_STARTED` |
| C1 — BE-SP-12 implementation pack | `PASS_DOCUMENT`; implementasi `NOT_STARTED` (sesuai D4) |
| Push / PR / branch protection | `NOT_STARTED` (dilarang pada sesi ini) |

## 1. Baseline dan commit

| SHA | Isi |
|---|---|
| `71aa30b` | baseline bersih saat mulai (working tree bersih) |
| `e033702` | `chore(ci): CODEOWNERS untuk jalur keamanan kritis` |
| `0654937` | `ci(secret-gate): gitleaks fail-closed + baseline ratchet + artefak JUnit per SHA` |
| `e920c92` | `docs(c2b2): execution pack restricted builder + kontrak bukti BE-SP-12` |
| *(commit ini)* | laporan hasil |

Tiga commit lokal, satu scope per commit, tanpa push/PR/merge. Baseline sesuai
direktif: `git merge-base --is-ancestor 71aa30b HEAD` = **OK**. Posisi terhadap remote:
`origin/master` = `6f1cfc2`; directive baseline `71aa30b` adalah **8 commit lokal yang
belum di-push**, sehingga `git rev-list --count origin/master..HEAD` = **11** (8 lama + 3
commit sesi ini). Tidak ada perubahan apa pun pada `origin/master`.

## 2. Hasil CI hardening lokal

| Kebutuhan direktif §4 | Implementasi | Bukti |
|---|---|---|
| A. Scanner rahasia terverifikasi & dipin | gitleaks 8.28.0; sha256 tarball **tertanam** (`a65b5253…a840eb`) | `sha256sum` tarball rilis = konstanta; tes `test_checksum_scanner_tertanam_bukan_diunduh` |
| A. Scanner absen = FAIL | blok `run` dieksekusi dengan `PATH` tanpa gitleaks | exit `1`, `FAIL gitleaks tidak tersedia di runner` |
| A. `make secrets` tidak dipakai apa adanya | target itu `exit 0` saat gitleaks absen (hijau palsu) | `test_gerbang_rahasia_tidak_memakai_make_secrets` |
| A. Laporan tak menampilkan nilai rahasia | `--redact` + JSON | `reports/ci/gitleaks.json` berisi `"Secret": "REDACTED"` |
| A. Canary negatif | PAT sintetis dibangkitkan saat runtime di klon `--shared` | exit `1`, laporan klon = `canary_kebocoran.txt` |
| B. CODEOWNERS | `.github/`, `CODEOWNERS`, `.gitleaks.toml`, inti bukti, kontrak proses | `test_codeowners_valid_dan_mencakup_jalur_kritis` |
| B. Reviewer memenuhi syarat | **tidak ada** reviewer kedua | `gh api repos/anashadi-node/super-dev-builders/collaborators` → 1 akun: `anashadi-node admin=true push=true` → **BLOCKED** |
| C. Artefak per SHA | `ci-evidence-<sha>`: JUnit + gitleaks.json + meta.json, retensi 14 hari | simulasi lokal: JUnit 860 tes ditulis dari satu eksekusi suite |
| D. `permissions: contents: read` | dipertahankan, tanpa permission tingkat job | `test_permission_token_minimal` |
| D. Tanpa trigger berprivilege | hanya `push`, `pull_request`, `workflow_dispatch` | `test_boundary_runner_dan_tidak_ada_trigger_berprivilege` |
| D. Action dipin | `upload-artifact@ea165f8…` (40 hex) | `test_semua_action_dipin_sha` |
| D. Status check tidak berubah diam-diam | job `check` + name `check (lint + registry + test + drift)` dikunci tes | `test_nama_job_dan_status_check_tidak_berubah` |
| D. Dapat di-rollback | semua perubahan ada di 3 commit lokal, tanpa push | `git log 71aa30b..HEAD` |

**Yang belum dibuktikan:** workflow belum pernah dijalankan GitHub Actions (push
dilarang), jadi belum ada bukti runner nyata. Yang terbukti adalah blok `run`
gerbang benar-benar dieksekusi lokal, bukan hanya dibaca.

## 3. Berkas yang berubah

| Berkas | Perubahan | Baris |
|---|---|---|
| `.github/workflows/ci.yml` | +4 langkah (pasang scanner, pindai rahasia, metadata, unggah artefak), +env JUnit di langkah tes | 19 langkah total; 15 langkah lama utuh (dikunci `test_langkah_lama_tidak_dihapus`) |
| `.github/CODEOWNERS` | baru: proteksi jalur kritis, tanpa pola global `*` | 38 baris |
| `.github/gitleaks-baseline.json` | baru: 10 temuan teraudit, semua `Secret: REDACTED` | 10 entri |
| `tests/test_ci_workflow_policy.py` | baru: 17 tes kontrak CI | 310 baris |
| `docs/RESTRICTED_BUILDER_C2B2M.md` | baru: spec + matriks uji + rollback | 97 baris |
| `docs/c2b2m/{preflight,apply,verify,rollback}.sh` | baru: skrip paket, belum dieksekusi | 4 berkas |
| `docs/BE_SP12_EVIDENCE_CONTRACT.md` | baru: kontrak 9 field + allowlist | 86 baris |
| `docs/INDEX.md` | +2 entri indeks | 2 baris |

Tidak ada perubahan pada: `Makefile`, `workflows/stages.yaml`, `agents/*.yaml`,
`registry/skills.yaml`, `platform/did_profiles.json`, `scripts/*`, `.gitleaks.toml`,
`runs/`, dan konfigurasi produksi.

## 4. Command, exit code, dan hasil aktual

| # | Command | Exit | Hasil |
|---|---|---|---|
| 1 | `make lint` | 0 | ruff bersih (termasuk berkas tes baru) |
| 2 | `.venv/bin/python -m pytest tests skills integrations -q --junitxml=…` | 0 | **860 tes, 0 gagal, 0 error, 0 skip**, 69,8 s |
| 3 | `.venv/bin/python -m pytest tests/test_ci_workflow_policy.py -o addopts=""` | 0 | 17 tes kontrak CI |
| 4 | `gitleaks detect … --baseline-path .github/gitleaks-baseline.json --log-opts=--all` | 0 | 184 commit dipindai, **0 temuan baru** |
| 5 | Blok gerbang dengan `PATH` tanpa gitleaks | 1 | FAIL (fail-closed terbukti) |
| 6 | `test_gerbang_rahasia_menolak_versi_berbeda` (shim `8.27.0`) | 0 sebagai tes | tes lulus = gerbang menolak versi berbeda; pin ditegakkan |
| 7 | Canary sintetis di klon `--shared` | 1 | laporan klon = `canary_kebocoran.txt` (ratchet presisi) |
| 8 | `make check` | 0 | lint, registry, 860 tes, drift **136/136**, hygiene **PASS (0 FAIL, 3 WARN)**, packs **9/9**, docs-lint **PASS** |
| 9 | `bash -n docs/c2b2m/*.sh` | 0 | 4 skrip lolos sintaks |
| 10 | `docs/c2b2m/preflight.sh` | 0 | `HASIL: PASS` — read-only, tidak ada perubahan |
| 11 | `docs/c2b2m/apply.sh` tanpa approval | 2 | `DITOLAK` (guard bekerja) |
| 12 | `docs/c2b2m/rollback.sh` tanpa approval | 2 | `DITOLAK` (guard bekerja) |

Angka 840 tes pada laporan sebelumnya **tidak diklaim** sebagai hasil hari ini.
Baseline tes yang terukur sekarang 843 tes sebelum berkas tes baru (860 − 17).

## 5. Temuan review D6 (independent review) dan D8 (security gate)

### D6 — reviewer

| ID | Temuan | Tindakan |
|---|---|---|
| D6-F1 | Baseline ratchet bisa dipakai mematikan gerbang: tambahkan fingerprint kebocoran sendiri ke baseline | `test_baseline_hanya_berisi_temuan_teraudit` mengunci himpunan commit & maksimum 10 entri & `RuleID` |
| D6-F2 | `if-no-files-found: warn` lebih lunak dari `error` pada unggahan artefak | Sengaja: `error` akan menutupi kegagalan tes yang sesungguhnya. `meta.json` selalu dibuat sehingga minimal satu berkas ada |
| D6-F3 | Checksum scanner diunduh dari origin yang sama → tidak melindungi dari origin tersusupi | **Diperbaiki:** sha256 tarball ditanam di workflow, diverifikasi lokal terhadap tarball rilis |
| D6-F4 | Nama/klaim job bisa berubah dan memutus branch protection tanpa error | Dikunci tes (`test_nama_job_dan_status_check_tidak_berubah`) |
| D6-F5 | Canary dalam bentuk token literal di source akan ditangkap scanner | **Benar dan terbukti:** gerbang menangkap canary tes sendiri; canary kini dibangkitkan runtime (seed tetap → deterministik) |
| D6-F6 | Limpahan `.github/gitleaks-baseline.json` di luar daftar berkas yang diizinkan §4 | Dilaporkan terbuka: berkas ini diperlukan agar gerbang tidak memblokir riwayat lama; diproteksi CODEOWNERS |

### D8 — keamanan

| ID | Temuan | Bukti |
|---|---|---|
| D8-S1 | `anashadi` ada di grup `sudo`, `docker`, `lxd` → akun Owner setara root; isolasi builder hanya bermakna bila builder di luar ketiga grup | `getent group sudo docker lxd` |
| D8-S2 | `~/super-dev-builders` mode `0775` (grup bisa tulis) → builder **tidak boleh** masuk grup `anashadi` | `stat -c %A` |
| D8-S3 | Profil Chromium di riwayat **sudah publik**: `git merge-base --is-ancestor 72eec21b origin/master` = ya, juga di `origin/did/bench-provenance`, `origin/did/rt-rw-portal-l2`, `origin/did/villa-agency-os-fixnums` | **Tidak ada kredensial:** `gaia_id` kosong, tak ada `os_crypt.encrypted_key`, 0 email, 0 telepon; 9 temuan = kunci publik ekstensi + MAC preferensi + kunci publik OHTTP. Karena sudah di remote, rewrite riwayat **tidak** dianjurkan (§9 butir 4) |
| D8-S4 | Temuan rahasia dilebur ke baseline tanpa jejak audit | Audit tertulis di pesan commit `0654937` + §5 di atas + baseline hanya `Secret: REDACTED` |
| D8-S5 | Token CI berpotensi lebih luas dari yang perlu | `permissions: contents: read`, tanpa permission job-level, diuji |

## 6. Kesiapan restricted builder (C2-B2M)

- **Spec siap eksekusi**, belum dieksekusi. Fakta host terukur: `/home/anashadi`
  `0750`, `~/.hermes` dan `~/.ssh` `0700` → **tidak perlu ACL rekursif**; karena itu
  rancangan memakai workspace terpisah `/srv/sdb-workspace` (bukan ACL ke home/repo).
- 12 uji akses dengan **canary sintetis** (bukan rahasia asli) sudah didefinisikan di
  `verify.sh`, termasuk subprocess identity (`os.getuid()` sama dengan UID builder).
- `preflight.sh` dijalankan hari ini: **PASS** (user/workspace/canary belum ada,
  ruang `/srv` 71 GB, `python3`/`git`/`bash`/`sudo` tersedia).
- Satu penghalang operasional: `sudo` non-interaktif tidak tersedia di sesi ini →
  `verify.sh` harus dijalankan dalam sesi sudo aktif (dicatat di preflight output).

## 7. Risk register

| # | Risiko | Level | Mitigasi sekarang | Sisa risiko |
|---|---|---|---|---|
| R1 | Gerbang rahasia gagal total bila unggahan rilis gitleaks berubah | rendah | sha256 tertanam → perubahan biner = FAIL, bukan lolos | perlu update konstanta saat upgrade |
| R2 | Baseline dipakai menyembunyikan kebocoran baru | sedang | himpunan commit dikunci tes; maksimum 10 entri | butuh review manusia saat baseline diubah |
| R3 | CODEOWNERS belum menegakkan apa pun (baru berlaku setelah masuk base branch + branch protection) | **tinggi** | laporan `BLOCKED`; branch protection **tidak** diubah | butuh reviewer kedua + approval Owner |
| R4 | Builder masih bisa lolos lewat vektor kernel/`.so` lokal | sedang | pembatasan identitas + filesystem | bukan sandbox; dicatat sebagai batas |
| R5 | Channel CI belum pernah dibuktikan di runner | sedang | blok `run` dieksekusi nyata lokal | harus dibuktikan setelah push |
| R6 | Riwayat repo publik memuat artefak profil Chromium (non-kredensial) | rendah | audit nilai; tidak ada secret/PII | pembersihan riwayat = destruktif → keputusan Owner |

## 8. BE-SP-12 implementation pack

Ringkas (detail: `docs/BE_SP12_EVIDENCE_CONTRACT.md`):

- Kontrak 9 field: `capability_id`, `revision`, `test_command`, `exit_code`,
  `test_results`, `artifact_refs`, `evidence_level`, `verification_timestamp`,
  `review_status`.
- Gerbang anti-"PASS dari teks agent": PASS sah hanya bila `exit_code == 0` **dan**
  `failed == 0` **dan** `evidence_level >= CI_ATTESTED`; `AGENT_REPORTED` maksimum
  `pending`.
- Allowlist 5 berkas (validator, skema, registri pilot 1 entri, tes, keluaran
  runtime). `workflows/stages.yaml` (19 tahap) dan 26 agent instance tidak disentuh.
- Temuan prasyarat: katalog 26 capability **belum ada sebagai data mesin** di repo
  (`grep "BE-SP-"` = 0 hasil) → pack sengaja tidak membuat ulang blueprint.
- Status implementasi: `NOT_STARTED` — belum ada satu baris kode BE-SP-12.

## 9. Keputusan Owner yang diperlukan

1. **Push 3 commit lokal** ke `anashadi-node/super-dev-builders` + buka PR? (tanpa ini
   CI tidak pernah berjalan di runner dan tidak ada bukti runner nyata.)
2. **Reviewer independen**: tambahkan akun kedua dengan akses tulis, lalu aktifkan
   "Require review from Code Owners"? Tanpa ini CODEOWNERS hanya dokumentasi
   (`BLOCKED`, branch protection tidak dilemahkan).
3. **Migrasi OS (A″)**: izinkan `apply.sh` dijalankan (`useradd`, workspace
   `/srv/sdb-workspace`, canary sintetis)? Semua langkah punya rollback idempoten.
4. **Riwayat Chromium (R6)**: biarkan (non-kredensial), atau jadwalkan pembersihan
   riwayat + rotasi bila ada keraguan? Pembersihan = `filter-repo` + force-push →
   butuh approval eksplisit dan tidak dilakukan di sesi ini.
5. **BE-SP-12**: 3 pertanyaan terbuka di §5 dokumen kontrak (lokasi `reports/capability/`,
   sumber tunggal katalog 26, apakah PASS boleh jadi merge gate).

## 10. Fase berikutnya yang paling bernilai

**Buka PR `feat/c2b2g-ci-hardening` → jalankan CI di runner sungguhan.** Sampai itu
terjadi, seluruh hasil §2–§4 tetap `PASS_VERIFIED (lokal)` dan tidak boleh disebut
"CI sudah aman". Urutan setelah push: verifikasi artefak `ci-evidence-<sha>` muncul,
lalu PR negatif untuk menguji B (canary di PR harus FAIL), baru tutup R3.

## FINAL GATE

**`PASS_VERIFIED_SUBSCOPE`** — CI hardening lokal terverifikasi dengan eksekusi nyata
(860 tes, 0 gagal; gerbang dieksekusi, bukan dibaca), dengan dua butir terbuka yang
dinyatakan terang: **BLOCKED** untuk penegakan CODEOWNERS (tak ada reviewer kedua) dan
**NOT_STARTED** untuk eksekusi runner GitHub, migrasi OS builder, serta implementasi
BE-SP-12 — semuanya menunggu keputusan Owner di §9.