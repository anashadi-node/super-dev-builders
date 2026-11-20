# SDB — C2-B2G Release Candidate & C1 Readiness (hasil eksekusi)

**Tanggal eksekusi:** 2026-11-20 (WIB) · **Mode:** `BROWNFIELD_RECOVERY → CHANGE_ONLY`
**Env kebijakan:** `SDB_DONE_POLICY=attested`, `SDB_EVIDENCE_MODE=legacy`
**Owner authorization yang berlaku:** `PUSH_APPROVED=NO`, `MERGE_APPROVED=NO`,
`DEPLOY_APPROVED=NO`, `OS_CHANGES_APPROVED=NO`, `ACCESS_CHANGES_APPROVED=NO`

Label bukti: **[V]** perintah dijalankan pada revisi yang disebut · **[H]** hasil dilaporkan
sesi sebelumnya (revisi lain) · **[P]** usulan · **[U]** tidak diketahui · **[B]** terblokir.

---

## 1. HEAD dan branch saat ini

| Butir | Nilai | Bukti |
|---|---|---|
| Branch aktual | `feat/c2b2g-ci-hardening` | `git rev-parse --abbrev-ref HEAD` |
| HEAD penuh | `89fbe62bc48348c92a25ee143c90fbd9efb3ba1d` | `git rev-parse HEAD` |
| HEAD yang dilaporkan direktif | `7bca894` | **cocok** sebagai leluhur: `7bca894` → `02322c3` → `89fbe62` |
| Working tree | bersih sebelum commit laporan ini | `git status --porcelain` = kosong |
| `origin/master` | `6f1cfc2`, tidak berubah | `git rev-parse --short origin/master` |
| Branch `feat/c2b1-trusted-verification-foundation` | **tidak ada** secara lokal | `git rev-parse --verify` gagal |

**Evaluasi perbedaan nama branch:** direktif menyebut `feat/c2b1-...`; branch itu tidak pernah
dibuat dengan nama tersebut setelah C2-B2G dimulai — riwayatnya sama dan linear
(`23065a9` → … → `71aa30b` → `e033702` → `0654937` → `e920c92` → `7bca894` → `02322c3`
→ `89fbe62`). Tidak ada commit yang hilang atau dobel; hanya nama branch yang berbeda.
Tidak ada reset/checkout paksa yang dilakukan.

---

## 2. Jumlah commit yang akan keluar bila di-push

`git rev-list --count origin/master..HEAD` = **17** pada HEAD final laporan ini.
Komposisi: 8 commit lokal lama (`23065a9` … `71aa30b`) + 5 commit kerja sesi ini
(`e033702`, `0654937`, `e920c92`, `02322c3`, `89fbe62`) + 4 commit laporan
(`7bca894`, `6334bf8`, `ea5753b`, dan commit terakhir yang memuat angka ini).
Angka ini bertambah satu setiap laporan diperbarui — itulah sebabnya disebut sebagai
rentang, bukan angka tetap. Ringkasan diff terhadap `origin/master` sebelum laporan ini:

```
21 files changed, 4949 insertions(+), 48 deletions(-)
```

---

## 3. Verifikasi pemindaian riwayat / CI

### 3.1 Temuan utama [V]

`actions/checkout` sebelumnya **tanpa** `fetch-depth` → default **1 commit**, sedangkan gerbang
menjalankan `gitleaks detect --log-opts="--all"`. Reproduksi terkendali oleh tes
`test_hazard_checkout_dangkal_melewatkan_kebocoran` (repo uji 3 commit: c1 bersih, c2 berisi
kebocoran sintetis, c3 menghapus berkas itu sehingga nilainya **hanya** tersisa di riwayat):

| Skenario | Commit terlihat di klon | Exit | Temuan |
|---|---|---|---|
| klon `--depth 1` (setara checkout default) | 1 | **0** | **0** → kebocoran LEWAT (hijau palsu) |
| klon penuh (setara `fetch-depth: 0`) | 3 | **1** | 1, `File == "bocor.txt"` |

Catatan pengukuran: pada uji manual terpisah dengan repo 6 commit, gitleaks melaporkan
`5 commits scanned` pada klon penuh — jumlah yang dicetak gitleaks tidak sama dengan
`git rev-list --count`, jadi yang dipakai sebagai bukti adalah **perbandingan exit code**
(0 vs non-0) dan isi laporan, bukan angka "commits scanned".

Perbaikan (`02322c3`): `fetch-depth: 0` + `persist-credentials: false`, dan blok gerbang
memvalidasi bahwa laporan benar-benar ada, JSON valid, serta tidak memuat nilai tak ter-redact.

### 3.2 Sepuluh pemeriksaan wajib

| # | Pemeriksaan | Hasil | Bukti |
|---|---|---|---|
| 1 | Scanner menerima riwayat yang dimaksud | **LULUS** | blok nyata dijalankan lokal: `190 commits scanned` (187 pada eksekusi sebelum commit laporan) |
| 2 | Riwayat hilang tidak boleh PASS | **LULUS** | `test_hazard_checkout_dangkal_melewatkan_kebocoran` (klon dangkal = exit 0 **hanya** di klon dangkal; asersi memaksa keduanya diuji) |
| 3 | Scanner absen tidak boleh PASS | **LULUS** [H] | `command -v gitleaks \|\| exit 1`; diuji dengan `PATH` tanpa scanner (exit 1) |
| 4 | Checksum artefak = rilis resmi | **LULUS** | unduh `gitleaks_8.28.0_linux_x64.tar.gz` hari ini → `a65b5253807a68ac0cafa4414031fd740aeb55f54fb7e55f386acb52e6a840eb` = `GITLEAKS_SHA256` di `ci.yml` |
| 5 | Baseline ratchet tidak bisa diperluas | **LULUS** | `test_baseline_hanya_berisi_temuan_teraudit` (maks 10 entri, commit dikunci, `Secret == "REDACTED"`) |
| 6 | Canary sintetis → FAIL | **LULUS** | klon penuh pada repo uji = exit 1, laporan hanya `bocor.txt`; canary dibangkitkan runtime |
| 7 | Laporan tidak mengekspos nilai rahasia | **LULUS** [V] | `--redact` + blok memverifikasi `Secret ∈ {None, "", "REDACTED"}`; laporan nyata: `entri=0` |
| 8 | Hasil scanner tidak diabaikan | **LULUS** | `test_gerbang_gagal_bila_laporan_tidak_dihasilkan` (shim exit 0 tanpa laporan → FAIL) |
| 9 | Artefak JUnit bebas kredensial/data pribadi | **LULUS** | `test_junit_tidak_memuat_data_pribadi_atau_kredensial` (tanpa `/home/`, email, `ghp_`, `AKIA`, blok kunci privat) |
| 10 | Izin CI least-privilege | **LULUS** | `permissions: contents: read` (job tunggal) + `persist-credentials: false` |

### 3.3 Pemindaian lokal vs ref pull-request di GitHub

| Konteks | Riwayat yang tersedia | Cakupan nyata |
|---|---|---|
| Lokal (`gitleaks --all`) | seluruh ref lokal | 190 commit, 0 kebocoran |
| CI `push`/`workflow_dispatch` dengan `fetch-depth: 0` | semua branch + tag yang di-fetch | seluruh riwayat yang dijangkau ref yang di-checkout |
| CI `pull_request` | merge commit `refs/pull/N/merge` + riwayat penuh ref tersebut | kebocoran yang ADA di riwayat PR tertangkap; branch lain yang tidak di-fetch tidak dipindai |

**Batasan yang dicatat jujur:** PR dari fork tetap dipindai riwayatnya (karena di-fetch), tetapi
*branch lain di repo* yang tidak terkait PR tidak dipindai pada event `pull_request`. Mitigasi
yang belum dibuat (di luar scope izin ini): jadwal harian pemindaian penuh. Ini **bukan** klaim
bahwa seluruh repo selalu bersih — hanya bahwa setiap commit yang dipindai menghasilkan verdict
yang bisa diaudit.

---

## 4. Verdict keamanan pra-publikasi

**`PUSH_READY`** (dengan tiga catatan di bawah). Dasar:

| Pemeriksaan | Hasil |
|---|---|
| Pola kredensial pada rentang commit yang keluar | 0 kredensial nyata; `ghp_`/`AKIA` hanya muncul sebagai **literal pola regex** di tes (`tests/test_ci_workflow_policy.py`) |
| Pemindaian gitleaks pada seluruh riwayat lokal | 190 commit, **0 kebocoran** |
| Canary sintetis tertinggal di commit yang keluar | **tidak ada** (`git log -p origin/master..HEAD \| grep -c 'ghp_[A-Za-z0-9]{20,}'` = 0) |
| Objek commit percobaan `9af4f37` | masih ada sebagai objek **tak terjangkau** (tidak ada ref yang memuatnya, `git for-each-ref --contains` kosong) → **tidak akan terkirim** oleh push biasa |
| Berkas baru tak terlacak yang ikut terbawa | tidak ada (`git status --porcelain -uall` kosong) |
| Identitas pribadi pada laporan/dokumen baru | path `/home/anashadi` dan nama user muncul, **tetapi sudah publik**: `git grep -o "/home/anashadi" origin/master` = **1103 kemunculan** |
| Email/telepon/IP pada diff keluar | 0 (hanya dekorator Python seperti `@pytest.fixture` yang tertangkap regex email) |
| Data Chromium di riwayat | sudah publik di `origin/master` + 3 branch remote; isi non-kredensial (`gaia_id` kosong, tanpa `os_crypt.encrypted_key`, 0 email/telepon) |

Catatan: (1) scanner exit 0 **tidak** saya perlakukan sebagai bukti tunggal — audit konteks
manual dilakukan pada setiap pola yang tertangkap. (2) Bila Owner ingin menghapus objek
`9af4f37` dari disk lokal, `git gc --prune=now` cukup; itu **tidak** dijalankan karena bersifat
destruktif dan tidak diperlukan untuk push. (3) Username pada path lokal adalah temuan
**pra-eksisting**, bukan pengenalan baru; parameterisasi path tetap disarankan jangka panjang.

---

## 5. Hasil tes CI lokal

| Command | Exit | Hasil |
|---|---|---|
| `pytest tests skills integrations --junitxml=…` | **0** | `tests=866 failures=0 errors=0 skipped=0 time=61.0s` |
| `pytest tests/test_ci_workflow_policy.py` | **0** | **23 passed in 3.7s** |
| Blok `Pindai rahasia` asli (diekstrak dari YAML, dijalankan `bash -c`) | **0** | `190 commits scanned`, `no leaks found`, `laporan_rahasia=OK entri=0` (dijalankan ulang pada HEAD `6334bf8`) |
| `bash -n docs/c2b2m/*.sh` | 0 | empat skrip lolos sintaks |
| `docs/c2b2m/apply.sh` tanpa dua kunci | **2** | menolak (guard) |
| `docs/c2b2m/rollback.sh` tanpa dua kunci | **2** | menolak (guard) |
| `docs/c2b2m/preflight.sh` (read-only) | **0** | `HASIL: PASS` |
| `make check` (lint, docs-lint, drift, registry, packs, hygiene, tes) | **0** | drift `136/136`, hygiene `PASS (0 FAIL, 3 WARN)`, packs `9/9` |

Tes negatif baru yang menyertai koreksi: hazard checkout dangkal, laporan hilang, laporan tak
ter-redact, JUnit bebas PII, `fetch-depth: 0`, `persist-credentials: false`.

---

## 6. Status push / PR

**Tidak ada push, tidak ada PR** — `PUSH_APPROVED=NO`. Status: `PUSH_READY` dengan prasyarat
yang sudah dipenuhi (baseline konsisten, tree bersih, 866 tes lulus, gerbang pra-publikasi lulus).
Yang belum ada bukti: perilaku runner GitHub (lihat §7).

---

## 7. Hasil runner GitHub

**`NOT_STARTED`** — tidak ada run CI nyata. Semua bukti CI berasal dari eksekusi lokal atas blok
`run:` asli hasil ekstraksi YAML, ditambah validasi skema YAML via PyYAML. `actionlint` tidak
terpasang di host ini, sehingga tidak ada lint khusus workflow. Klaim "CI hijau di GitHub"
**tidak** dibuat.

---

## 8. CODEOWNERS: blocker dan paket tata kelola

**Status: `BLOCKED`** — `gh api repos/anashadi-node/super-dev-builders/collaborators` → 1 akun
(`anashadi-node`, `admin=true`, `push=true`). "Require review from Code Owners" tidak dapat
dipenuhi tanpa reviewer kedua. Branch protection **tidak** diubah, CODEOWNERS **tidak** diklaim aktif.

| Butir | Isi |
|---|---|
| Peran reviewer | Collaborator dengan akses **Write** (minimum agar review dihitung sebagai code-owner review); idealnya akun terpisah dari akun pemilik |
| Berkas yang wajib di-review | `/.github/` (termasuk `CODEOWNERS` sendiri), `.github/workflows/`, `.github/gitleaks-baseline.json`, `.gitleaks.toml`, `docs/c2b2m/`, `scripts/release_check.py`, `tests/test_ci_workflow_policy.py` |
| Bootstrap | (1) undang reviewer dengan Write → (2) buka PR yang menyentuh `.github/` dan lihat apakah review diminta otomatis → (3) setelah terbukti, aktifkan "Require review from Code Owners" + "Dismiss stale approvals" → (4) uji PR negatif |
| Uji penegakan | PR yang mengubah `ci.yml` tanpa approval code owner harus **tidak** bisa merge (`gh pr view --json reviewDecision` = `REVIEW_REQUIRED`) |
| Deteksi bypass | `gh api repos/.../branches/master/protection` (required reviews + bypass actors), audit log organisasi untuk `protected_branch.policy_override`, dan alert bila PR `.github/` merge tanpa review |
| Rollback | Matikan rule "Require review from Code Owners" (bukan menghapus CODEOWNERS), atau revert commit `e033702` |

---

## 9. Kesiapan restricted builder

**Status: `READY_FOR_OWNER_APPROVAL`** — pack lengkap dan dapat dieksekusi apa adanya setelah
approval; **belum ada** perubahan OS. Dua keputusan Owner tersisa (§9.3).

| Bukti | Hasil |
|---|---|
| `bash -n` pada `preflight/apply/verify/rollback` | OK |
| `preflight.sh` dijalankan (read-only) | exit 0, `HASIL: PASS` |
| `apply.sh`/`rollback.sh` tanpa dua kunci | exit 2 (menolak) |
| Uji akses di `verify.sh` | **16 uji** (12 lama + 4 baru: skills salinan, workspace proyek lain, `/etc/systemd/system`, proses pekerja mewarisi UID) |
| Pemetaan 11 butir direktif §7 | tabel di `docs/RESTRICTED_BUILDER_C2B2M.md` §3b |
| Celah yang ditutup pada sesi ini | skills builder kini **salinan** `/srv/sdb-workspace/skills` (bukan akses `~/.hermes`), venv sendiri `/srv/sdb-workspace/venv` |

### 9.3 Keputusan Owner yang masih terbuka

1. **Kebijakan skills builder:** salinan manual (dipilih default; tidak otomatis terbarui) vs
   symlink baca-saja (memperluas permukaan baca ke pohon profil Owner — ditolak default).
2. **Cara menjalankan proses builder:** `sudo -u sdbbuild` manual (dipilih default) vs unit
   systemd `sdbbuild.service` vs supervisor Hermes. Belum dibuat.

Tidak ada `useradd`, `groupadd`, `chown`, `chmod`, `setfacl`, atau perubahan systemd yang
dijalankan sesi ini. `verify.sh`/`rollback.sh` belum dieksekusi terhadap sistem nyata.

---

## 10. Tiga keputusan BE-SP-12 (pertanyaan persis dari §5 kontrak)

Sumber: `docs/BE_SP12_EVIDENCE_CONTRACT.md:81-87`. Tidak ada approval yang saya karang:
ketiganya tetap **PROPOSED**.

### D-BE1 — lokasi evidence

> "Apakah `reports/capability/` boleh ditambahkan ke repo (atau cukup `runs/`)?"

- **Opsi A (rekomendasi, default aman):** `runs/capability/<id>/<sha>.json` — `runs/` sudah
  ada, sudah dipakai untuk artefak, tidak menambah pohon baru; konsekuensi: evidence tidak
  ikut version control sehingga tidak bisa dipakai sebagai bukti publik tanpa unggahan.
- **Opsi B:** `reports/capability/` di repo — evidence bisa direview di PR, tetapi menambah
  ~1 berkas per (capability × commit) ke repo publik; risiko PII/artefak besar naik.
- **Dampak:** A = nol perubahan `.gitignore`/higiene; B = perlu aturan higiene baru + review isi.
- **Rekomendasi:** **A** untuk pilot; putuskan B hanya bila evidence harus terlihat di PR.

### D-BE2 — sumber kebenaran katalog

> "Apakah `capability_pilot.yaml` menjadi sumber tunggal katalog 26 nanti, atau katalog tetap di dokumen eksternal dan repo hanya menyimpan ID?"

- **Opsi A (rekomendasi):** `registry/capability_pilot.yaml` menjadi sumber tunggal yang tumbuh
  dari 1 → 26 entri; format sudah siap, tanpa migrasi.
- **Opsi B:** katalog di dokumen eksternal; repo hanya menyimpan `capability_id` (tanpa validasi
  bahwa ID terdaftar) — melemahkan aturan T7.
- **Dampak:** A = satu berkas registry baru + tes registri; B = validasi ID jadi mustahil.
- **Rekomendasi:** **A**, karena aturan "capability_id harus terdaftar" hanya bisa ditegakkan
  bila registri ada di repo.

### D-BE3 — wewenang status PASS

> "Apakah status PASS boleh dipakai untuk merge gate, atau hanya informatif sampai ada reviewer independen?"

- **Opsi A (rekomendasi):** PASS **informatif** sampai ada reviewer independen; merge gate tetap
  `make check` + review manual. Alasan: `evidence_level: CI_ATTESTED` membuktikan *tes dijalankan*,
  bukan *capability diterima* — dan repo ini belum punya reviewer kedua (§8).
- **Opsi B:** PASS menjadi merge gate → risiko: satu akun tunggal dapat menghasilkan evidence dan
  merge-nya sendiri (self-attestation), persis yang dilarang direktif.
- **Dampak:** A = tidak ada perubahan pada branch protection; B = butuh CODEOWNERS aktif dulu.
- **Rekomendasi:** **A** sampai §8 tuntas.

### Empat tingkat bukti yang tidak boleh saling menyiratkan

`test_execution` (tes jalan) ⇏ `capability_acceptance` (perilaku diterima) ⇏
`independent_verification` (pihak lain memeriksa) ⇏ `release_authorization` (izin rilis).
Pemetaan ke field kontrak: `test_execution` ← `exit_code`+`test_results`+`artifact_refs`;
`capability_acceptance` ← `review_status`; `independent_verification` ← `evidence_level:
INDEPENDENT_REVIEW` **dan** reviewer ≠ pembuat; `release_authorization` ← tidak ada di kontrak
evidence, tetap keputusan Owner (tidak boleh disimpulkan dari PASS).

---

## 11. Pack implementasi BE-SP-12 terkecil (belum dieksekusi)

Vertical slice satu capability, tanpa agent baru dan tanpa menyentuh 19 tahap workflow:

| Berkas | Isi | Ukuran target |
|---|---|---|
| `registry/capability_pilot.yaml` | 1 entri: `BE-SP-12`, `owner_divisi: D5`, `acceptance_ref`, `evidence_dir` | ≤ 20 baris |
| `registry/capability_evidence.schema.json` | 9 field, `additionalProperties: false` | ≤ 80 baris |
| `scripts/sdb_capability_evidence.py` | CLI `validate` + `record`; menolak hash mismatch, `revision` ≠ HEAD, level `AGENT_REPORTED` untuk PASS | ≤ 200 baris |
| `tests/test_capability_evidence.py` | T1–T8 dari §4 kontrak + T10 hash `workflows/stages.yaml` | ≤ 250 baris |
| `runs/capability/BE-SP-12/<sha>.json` | keluaran runtime | 1 berkas |

Aturan paket: tidak mengubah `Makefile` (target baru hanya bila disetujui terpisah), tidak
menyentuh `workflows/stages.yaml`, `agents/*.yaml`, `registry/skills.yaml`,
`platform/did_profiles.json`, `docs/c2b2m/*`. Estimasi: 1 sesi implementasi + 1 siklus review.
**Nol baris kode BE-SP-12 ditulis pada fase ini.**

---

## 12. Risiko yang masih terbuka

| # | Risiko | Tingkat | Mitigasi saat ini |
|---|---|---|---|
| R1 | Perilaku runner GitHub belum terbukti (langkah gitleaks/JUnit/metadata) | Sedang | blok `run:` diuji lokal + kontrak tes; bukti menyusul setelah push diizinkan |
| R2 | CODEOWNERS tidak bisa ditegakkan (satu akun) | Tinggi untuk tata kelola | paket bootstrap §8; branch protection tidak dilemahkan |
| R3 | Pemindaian PR tidak mencakup branch lain yang tidak di-fetch | Rendah | dicatat §3.3; usul jadwal harian (belum dibuat) |
| R4 | Evidence BE-SP-12 bisa jadi self-attestation | Sedang | D-BE3 direkomendasikan "informatif"; 4 tingkat bukti dipisah |
| R5 | Builder bukan sandbox (eskalasi kernel/`.so` lokal di luar cakupan) | Sedang | dicatat sebagai batas identitas, bukan sandbox |
| R6 | Skills builder berupa salinan → bisa basi | Rendah | keputusan §9.3 butir 1 |
| R7 | Artefak `9af4f37` (canary) masih di disk lokal | Rendah | tidak terjangkau ref → tidak terkirim; `git gc --prune=now` bila Owner mau |
| R8 | Klaim "enterprise-ready"/"semua bug hilang" | — | **tidak dibuat**; 866 tes lulus = bukti untuk subsistem yang diuji saja |

---

## 13. Approval berikutnya yang dibutuhkan Owner

1. **`PUSH_APPROVED`** untuk 17 commit pada `feat/c2b2g-ci-hardening` + Draft PR ke `master`
   (tanpa merge, tanpa force-push, tanpa ubah branch protection) — ini satu-satunya cara
   mendapatkan bukti runner nyata (R1).
2. **Reviewer kedua / arrangement review** untuk menuntaskan R2 (CODEOWNERS).
3. **`OS_CHANGES_APPROVED`** untuk `apply.sh` C2-B2M **setelah** §9.3 dijawab.
4. **Jawaban D-BE1/D-BE2/D-BE3** agar implementasi BE-SP-12 bisa dimulai.

**FINAL GATE: `PUSH_READY`** — pekerjaan lokal hijau dan gerbang pra-publikasi lulus; tidak ada
push/merge/deploy/perubahan OS yang dilakukan. Butir `NEEDS_DECISION` (§9.3, §10) tidak
menghalangi push, tetapi menghalangi langkah berikutnya.