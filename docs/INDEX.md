# Indeks Dokumen SDB

Satu tempat untuk menemukan dokumen yang benar. Kalau ada dua dokumen yang bertentangan, yang lebih baru
tanggalnya menang — dan yang kalah **harus** dipindahkan ke `docs/archive/`, bukan dibiarkan.

## Mulai di sini

| Dokumen | Untuk apa |
|---|---|
| `../README.md` | gambaran ekosistem, prinsip, quickstart |
| `ARCHITECTURE.md` | arsitektur hari ini (divisi, pipeline, gate) |
| `PETA_STRUKTUR.md` | peta direktori sekarang vs target + aturan penempatan |
| `DIVISIONS.md` | peran 12 divisi (D0–D11) |

## Produk & skala

| Dokumen | Isi |
|---|---|
| `ARSITEKTUR_SAAS.md` | rancangan tenancy, control plane, biaya, SLO, fase migrasi — **dokumen kunci untuk dijual** |
| `TOKEN_RESOURCE_POLICY.md` | batas konsumsi token |
| `MODEL_ROUTING_MATRIX.md` | model per peran |
| `CAPABILITY_REPLACEMENT_MATRIX.md` | pengganti tool komersial |

## Keputusan arsitektur (ADR)

| ADR | Keputusan |
|---|---|
| `adr/0001-model-tenancy.md` | pool + namespace default; silo hanya Enterprise |
| `adr/0002-artefak-di-object-store.md` | artefak keluar dari git |
| `adr/0003-distribusi-skill-lewat-pack.md` | pack manifest, bukan salin-per-profil |
| `adr/0004-kode-produk-di-sdb-platform.md` | kode produk di `sdb_platform/`, kontrak di `platform/` |
| `adr/0005-billing-prabayar-ber-rantai-hash.md` | uang integer μUSD, hold/charge/release, ledger ber-rantai |
| `adr/0006-worker-lease-dan-idempotensi.md` | klaim atomik, lease, penyelesaian tepat sekali |
| `adr/0007-pengetatan-pasca-audit.md` | siapa boleh menutup job, batal ditagih pemakaian, invoice admin, hash v2 |
| `adr/0008-html-dokumen-dilacak-dan-gerbang-docs-lint.md` | HTML dokumen berdaftar boleh dilacak; `make docs-lint` menegakkan indeks, PDF, dan klaim angka |

## Kebijakan & keamanan

| Dokumen | Isi |
|---|---|
| `SECURITY_PRIVACY_GATE_0.md` | gerbang otorisasi & privasi |
| `SECURITY_SUPPLY_CHAIN.md` | aturan tool pihak ketiga |
| `RECONSTRUCTION_POLICY.md` | batas rekonstruksi |
| `PERMISSION_MATRIX.md` | izin per peran |
| `THIRD_PARTY_SKILLS_DECISION_2026-10-05.md` | keputusan skill pihak ketiga |
| `SECURITY_GATE_10.md` | gerbang keamanan lapis 10: apa yang diperiksa sebelum klaim "aman" |
| `TECHNOLOGY_GOVERNANCE.md` | pemilihan teknologi |

## Pipeline & bukti

| Dokumen | Isi |
|---|---|
| `WORKFLOW_GATES.md` | gerbang per workflow |
| `EVIDENCE_TAXONOMY.md` | label FACT/INFERRED/UNKNOWN |
| `EVIDENCE_SCHEMA.md` | bentuk evidence |
| `HANDOFF_CONTRACTS.md` | serah-terima antar divisi |
| `BUILD_PACK.md` | handoff DID → backlog Builders + gerbang B01..B06 |
| `STATE_PROBES.md` | rekam state terautentikasi (loopback, tanpa rahasia di bukti) |
| `PIPELINE_E2E_EVIDENCE.md` | bukti pipeline ujung-ke-ujung |
| `WORKFLOW_SKENARIO.md` | alur kerja per skenario (web, mobile, desktop, backend, audit) beserta gate-nya |
| `RECON_NATIVE.md` | jalur biner (ELF/PE/Mach-O/APK/firmware): dua saklar izin, contoh terbukti, jebakan |
| `DID_FIXTURE_MOBILE_DESKTOP.md` | fixture profil mobile & desktop: artefak, batas, angka benchmark 4 target |
| `RELEASE_REHEARSAL.md` | rehearsal gerbang rilis: artefak dari alat nyata, uji PASS + uji negatif |
| `../workflows/*.yaml` | definisi workflow |

## Operasi

| Dokumen | Isi |
|---|---|
| `runbooks/GIT_PURGE.md` | pembersihan artefak dari riwayat git (destruktif, wajib backup) |
| `runbooks/RELEASE.md` | cara menandai & rollback rilis |
| `runbooks/ROTASI_KREDENSIAL.md` | rotasi `SDB_ADMIN_KEY`/`SDB_WORKER_KEY`: prosedur, bukti 401, rollback |
| `INSTALLATION_PLAN.md` | instalasi |
| `ROLLBACK_PLAN.md` | rollback umum |
| `GETTING_STARTED.md` | orientasi cepat |
| `HERMES_VENV_HARDENING_2026-10-05.md` | pengerasan lingkungan |
| `DECK_INTAKE.md` | kanal input per skenario: apa yang dikirim, ke mana, jadi job apa |
| `TELEGRAM_SDB.md` | kanal operasional Telegram: report 4 jam, tanya-jawab, perintah build |

## Integrasi

| Dokumen | Isi |
|---|---|
| `INTEGRASI_REA.md` | REA CLI terpin (audit + prosedur upgrade) |
| `INTEGRASI_REPLICA.md` | integrasi `replica-skill` (Zona B) + kebijakan clone |
| `RECON_FORGE.md` | orkestrator recon/paritas (`tools/recon-forge.py`): jalur web + native, akar izin, invarian bukti |
| `INTEGRASI_GITHUB_VERCEL_SUPABASE.md` | integrasi repo/deploy/DB |

## Tutorial

| Berkas | Untuk apa |
|---|---|
| `TUTORIAL_PENGGUNAAN.md` | panduan pakai SDB dari nol: alur, perintah, jebakan |
| `TUTORIAL_PRIBADI.md` | panduan kerja di PC ini dan lewat Telegram |

## Laporan & audit

| Dokumen | Isi |
|---|---|
| `../reports/SDB_DOUBLE_AUDIT_20261026.md` | **audit ganda 2026-10-26** (struktur + keamanan + skala) |
| `../reports/REA_AUDIT_20261026.md` | audit REA sebelum integrasi |
| `../reports/human-approval-required.md` | daftar approval |
| `../reports/ronde-3-audit-sdb-20261011.md` | audit ronde 3 |
| `SDB_LENGKAP_A_Z_20261105.md` | **dokumen A–Z terlengkap** (26 bab + 5 lampiran, semua angka terverifikasi 2026-11-05) |
| `DID_DIVISI_INVESTIGASI.md` | **Divisi Investigasi (DID) v1**: desain 1 agent + 1 pack, tahap `01C`, kedalaman L1–L4, validator handoff (`did_validate.py`), batas jujur per jenis target |
| `BRANCH_PROTECTION.md` | aturan proteksi `master`: akar masalah merge macet, tabel setelan sebelum/sesudah, kapan `enforce_admins` boleh dinyalakan lagi |
| `AUDIT_VALIDASI_SDB_20261105.md` | **laporan audit, validasi & remediasi 2026-11-05**: 18 temuan, angka sebelum/sesudah, uji mutasi 50%→100%, sisa risiko |
| `PAKET_UPDATE_SDB_20261104.md` | paket update menyeluruh 2026-11-04 (keadaan, bukti, rencana) |
| `REA_VS_CRAFT_ANYTHING_20261104.md` | riset perbandingan REA vs Craft Anything (dasar keputusan tool) |
| `CRAFT_ANYTHING_PILOT_0.3.0.md` | uji coba terisolasi Craft Anything v0.3.0: checksum, isi paket, batas pemakaian |
| `RESEARCH_REPLACEMENT_2026-10-04.md` | riset & eksekusi pengganti skill komersial |
| `UPGRADE_REPORT.md` | catatan upgrade Copy Cloning V1 → SDB V2.2 |

## Arsip

`archive/` berisi dokumen yang digantikan atau duplikat format (mis. `.html`/`.pdf` dari dokumen yang
sumbernya `.md`). Jangan menautkan arsip sebagai rujukan utama.

## Aturan menambah dokumen

1. Satu dokumen = satu tujuan. Kalau judulnya "dan", pecah.
2. Kebijakan → `docs/`; keputusan → `docs/adr/`; prosedur insiden → `docs/runbooks/`; temuan → `reports/`.
3. Perbarui indeks ini di commit yang sama. Dokumen tanpa indeks **menggagalkan `make check`**
   (`scripts/docs_lint.py`), bukan sekadar dianggap draf.
4. Format: `.md` adalah sumber. `.pdf` tidak pernah disimpan di repo. `.html` hasil generate hanya boleh
   dilacak bila terdaftar di `platform/docs-html-allowlist.json` dengan alasan tertulis (ADR-0008).
5. Rujukan di tabel ini wajib menunjuk berkas yang benar-benar ada — tautan mati ikut menggagalkan gerbang.

## Kontrak & kode Fase 2

| Berkas | Isi |
|---|---|
| `sdb_platform/control_plane/README.md` | rute API, batas yang ditegakkan, yang belum ada |
| `platform/schemas/*.schema.json` | kontrak tenant/job/artifact |
| `platform/packs/*.json` | manifest skill per divisi (hash + lisensi) |
| `THIRD_PARTY_NOTICES.md` | lisensi pihak ketiga + aturan pemisahan CC-BY-SA |
