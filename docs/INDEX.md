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

## Kebijakan & keamanan

| Dokumen | Isi |
|---|---|
| `SECURITY_PRIVACY_GATE_0.md` | gerbang otorisasi & privasi |
| `SECURITY_SUPPLY_CHAIN.md` | aturan tool pihak ketiga |
| `RECONSTRUCTION_POLICY.md` | batas rekonstruksi |
| `PERMISSION_MATRIX.md` | izin per peran |
| `THIRD_PARTY_SKILLS_DECISION_2026-10-05.md` | keputusan skill pihak ketiga |
| `TECHNOLOGY_GOVERNANCE.md` | pemilihan teknologi |

## Pipeline & bukti

| Dokumen | Isi |
|---|---|
| `WORKFLOW_GATES.md` | gerbang per workflow |
| `EVIDENCE_TAXONOMY.md` | label FACT/INFERRED/UNKNOWN |
| `EVIDENCE_SCHEMA.md` | bentuk evidence |
| `HANDOFF_CONTRACTS.md` | serah-terima antar divisi |
| `PIPELINE_E2E_EVIDENCE.md` | bukti pipeline ujung-ke-ujung |
| `../workflows/*.yaml` | definisi workflow |

## Operasi

| Dokumen | Isi |
|---|---|
| `runbooks/GIT_PURGE.md` | pembersihan artefak dari riwayat git (destruktif, wajib backup) |
| `runbooks/RELEASE.md` | cara menandai & rollback rilis |
| `INSTALLATION_PLAN.md` | instalasi |
| `ROLLBACK_PLAN.md` | rollback umum |
| `GETTING_STARTED.md` | orientasi cepat |
| `HERMES_VENV_HARDENING_2026-10-05.md` | pengerasan lingkungan |

## Integrasi

| Dokumen | Isi |
|---|---|
| `INTEGRASI_REA.md` | REA CLI terpin (audit + prosedur upgrade) |
| `INTEGRASI_REPLICA.md` | integrasi `replica-skill` (Zona B) + kebijakan clone |
| `RECON_FORGE.md` | orkestrator recon/paritas (`tools/recon-forge.py`): jalur web + native, akar izin, invarian bukti |
| `INTEGRASI_GITHUB_VERCEL_SUPABASE.md` | integrasi repo/deploy/DB |

## Laporan & audit

| Dokumen | Isi |
|---|---|
| `../reports/SDB_DOUBLE_AUDIT_20261026.md` | **audit ganda 2026-10-26** (struktur + keamanan + skala) |
| `../reports/REA_AUDIT_20261026.md` | audit REA sebelum integrasi |
| `../reports/human-approval-required.md` | daftar approval |
| `../reports/ronde-3-audit-sdb-20261011.md` | audit ronde 3 |

## Arsip

`archive/` berisi dokumen yang digantikan atau duplikat format (mis. `.html`/`.pdf` dari dokumen yang
sumbernya `.md`). Jangan menautkan arsip sebagai rujukan utama.

## Aturan menambah dokumen

1. Satu dokumen = satu tujuan. Kalau judulnya "dan", pecah.
2. Kebijakan → `docs/`; keputusan → `docs/adr/`; prosedur insiden → `docs/runbooks/`; temuan → `reports/`.
3. Perbarui indeks ini di commit yang sama. Dokumen tanpa indeks dianggap draf.
4. Format: `.md` adalah sumber; `.html`/`.pdf` hanya hasil generate, tidak disimpan di repo (ADR-0002).

## Kontrak & kode Fase 2

| Berkas | Isi |
|---|---|
| `sdb_platform/control_plane/README.md` | rute API, batas yang ditegakkan, yang belum ada |
| `platform/schemas/*.schema.json` | kontrak tenant/job/artifact |
| `platform/packs/*.json` | manifest skill per divisi (hash + lisensi) |
| `THIRD_PARTY_NOTICES.md` | lisensi pihak ketiga + aturan pemisahan CC-BY-SA |
