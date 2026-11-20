# C1 — BE-SP-12 Implementation Pack & Evidence Contract

**Status:** `NOT_STARTED` (nol baris kode produk ditulis untuk pilot ini).
Dokumen ini adalah *pack*: batas eksekusi, kontrak data, dan allowlist berkas yang
boleh disentuh saat izin implementasi diberikan.
**Keputusan Owner:** D4 — mulai dari BE-SP-12 sebagai vertical slice pertama; 26
proses implementasi tidak dibuka sekaligus; 12 FE + 14 BE tetap dalam 4+4 kelompok.

## 1. Temuan prasyarat (yang mengubah desain)

Katalog 26 specialist capability **belum ada sebagai data mesin** di repo ini:
`grep -rn "BE-SP-" --include=*.md --include=*.yaml --include=*.json` = **0 hasil**.
Karena direktif melarang membuat ulang blueprint 26 capability, pack ini **tidak**
membuat katalog 26 entri. Yang dibuat hanya registri pilot satu entri
(`capability_pilot.yaml`, belum ada — dibuat saat implementasi) dengan namespace yang sudah siap menampung 26
entri nanti tanpa migrasi format.

## 2. Kontrak evidence (9 field wajib)

| Field | Tipe | Aturan |
|---|---|---|
| `capability_id` | string | pola `^(FE|BE)-SP-\d{2}$`, harus terdaftar di `capability_pilot.yaml` (belum ada — dibuat saat implementasi) |
| `revision` | string | 40 hex commit SHA — bukan "HEAD", bukan nama branch |
| `test_command` | string | perintah yang benar-benar dijalankan; tanpa shell-meta `&&`, `;`, `\|` ganda |
| `exit_code` | integer | `0` = PASS; selain 0 = FAIL (tidak boleh dinormalisasi) |
| `test_results` | object | `{total, passed, failed, skipped, duration_s}`; `passed+failed+skipped == total` |
| `artifact_refs` | array | ≥1 entri `{path, sha256, bytes}`; berkas harus ada saat divalidasi |
| `evidence_level` | enum | `AGENT_REPORTED` < `CI_ATTESTED` < `INDEPENDENT_REVIEW` |
| `verification_timestamp` | string | RFC 3339 UTC; tidak boleh di masa depan |
| `review_status` | enum | `pending` \| `changes_requested` \| `approved` \| `rejected` |

File: `capability_evidence.schema.json` (belum ada — dibuat saat implementasi) (JSON Schema 2020-12, `additionalProperties: false`).

### Aturan turunan yang menutup celah "PASS dari teks agent"

- `evidence_level: AGENT_REPORTED` **tidak pernah** menghasilkan status PASS; ia
  hanya boleh muncul dengan `review_status: pending`.
- PASS hanya sah bila `exit_code == 0` **dan** `failed == 0` **dan**
  `evidence_level >= CI_ATTESTED` (artinya ada artefak mesin yang hash-nya cocok).
- `revision` harus sama dengan commit yang menghasilkan artefak; ketidakcocokan =
  evidence ditolak, bukan diperbaiki otomatis.
- Evidence yang field-nya kurang, artefak hilang, atau hash berbeda = **REJECTED**
  (bukan "dianggap lulus").

## 3. Allowlist berkas (batas eksekusi BE-SP-12)

Boleh dibuat/diubah — dan **hanya** ini:

```text
scripts/sdb_capability_evidence.py          # validator + perekam (CLI: validate, record)
registry/capability_evidence.schema.json    # skema 9 field
registry/capability_pilot.yaml              # 1 entri: BE-SP-12
tests/test_capability_evidence.py           # tes kontrak (termasuk negative)
reports/capability/<capability_id>/<sha>.json   # keluaran runtime, bukan source
```

Dilarang disentuh: `workflows/stages.yaml` (19 tahap tetap), `agents/*.yaml`,
`registry/skills.yaml`, `platform/did_profiles.json`, `scripts/release_check.py`,
`Makefile` (kecuali target baru yang aditif dan disetujui terpisah), dan seluruh
kode divisi lain.

## 4. Rencana tes (dijalankan saat implementasi, bukan sekarang)

| # | Tes | Harapan |
|---|---|---|
| T1 | evidence valid lengkap | diterima, status PASS |
| T2 | `exit_code: 1` | status FAIL, apa pun isi teks |
| T3 | field `review_status` hilang | REJECTED + pesan menyebut field |
| T4 | `artifact_refs[0].sha256` salah | REJECTED (hash mismatch) |
| T5 | `revision` ≠ `git rev-parse HEAD` | REJECTED |
| T6 | `evidence_level: AGENT_REPORTED` | maksimum `pending`, tidak pernah PASS |
| T7 | `capability_id` tidak terdaftar | REJECTED |
| T8 | `passed+failed+skipped != total` | REJECTED |
| T9 | 859 tes existing | tetap lulus (tanpa perubahan perilaku) |
| T10 | `workflows/stages.yaml` | hash tidak berubah |

Integrasi divisi: **D6/D7** membaca evidence sebagai masukan review;
**D8** menolak memulai security gate bila `evidence_level < CI_ATTESTED`.
Tidak ada agent instance baru — capability tetap dijalankan oleh divisi yang sudah ada.

## 5. Yang harus diputuskan Owner sebelum coding dimulai

1. Apakah `reports/capability/` boleh ditambahkan ke repo (atau cukup `runs/`)?
2. Apakah `capability_pilot.yaml` (belum ada — dibuat saat implementasi) menjadi sumber tunggal katalog 26 nanti,
   atau katalog tetap di dokumen eksternal dan repo hanya menyimpan ID?
3. Apakah status PASS boleh dipakai untuk merge gate, atau hanya informatif sampai
   ada reviewer independen (lihat §4B laporan: belum ada reviewer kedua)?