---
name: did-handoff
description: "Paket serah terima DID ke divisi Builders"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux, macos]
metadata:
  hermes:
    tags: [handoff, spec, builders, contract]
    divisions: [D1, D3]
    related_skills: [did-evidence-ledger, did-benchmark, reconstruction-spec]
---

# DID Handoff — Engineering Intelligence Package

Tujuan divisi Investigasi bukan "laporan tebal", tetapi **paket yang membuat Builders bisa membangun tanpa bertanya ulang**. Paket itu satu berkas: `runs/<target>/did/handoff.json`, dengan spesifikasi manusiawi diturunkan darinya (`SPEC_DID.md`).

## Kontrak minimal
```json
{
  "schema": "sdb.did.handoff/1",
  "target": {"slug": "...", "name": "...", "type": "web|api|mobile|desktop|binary|game|source",
             "authorization": {"gate0_verdict": "PASS", "manifest": "evidence/<t>/authorization.yaml"}},
  "scope": {"depth": "L1|L2|L3|L4", "profile": "<type>", "in_scope": [], "out_of_scope": []},
  "evidence_manifest": [{"id": "E-001", "path": "...", "sha256": "...", "captured_at": "...", "status": "OBSERVED"}],
  "findings": [{"id": "F-001", "status": "OBSERVED|INFERRED|UNKNOWN|OUT_OF_SCOPE", "claim": "...", "locator": "...", "evidence": ["E-001"]}],
  "unknowns": [{"id": "U-001", "question": "...", "impact": "blocking|non-blocking", "probe": "..."}],
  "coverage": [{"category": "routes", "status": "COVERED|PARTIAL|MISSING", "found": 12, "evidence": ["E-002"]}],
  "features": [{"id": "FT-01", "name": "...", "priority": "must|should|could", "status": "OBSERVED|INFERRED",
                "findings": ["F-001"], "acceptance_tests": [{"given": "...", "when": "...", "then": "..."}]}],
  "build_seeds": {"entities": [], "api": [], "states": [], "design_tokens": {}, "non_functional": []},
  "handoff": {"builders_ready": true, "blocking_unknowns": 0, "summary": "...", "next_actions": []},
  "budget": {"used": {"tool_calls": 0, "minutes": 0, "evidence_bytes": 0}},
  "discipline": {"replica_skill_used": false, "wrote_code": false, "mcp_registered": false, "redaction_applied": true}
}
```

## Tujuh bagian yang menentukan mutu
1. **Ringkasan yang bisa dipakai rapat** — 3–5 kalimat: apa produknya, siapa penggunanya, alur inti, batasan terbesar, kesiapan build.
2. **Fitur berprioritas** — `must` hanya yang tanpanya produk tidak berfungsi. Setiap `must` punya ≥1 temuan OBSERVED dan ≥1 tes terima `given/when/then`.
3. **Kontrak API** — metode, path, bentuk request/response, kode error, status OBSERVED/INFERRED. Yang INFERRED wajib punya `probe`.
4. **Model data** — entitas, field yang terlihat, relasi yang terbukti. Jangan mengarang skema database.
5. **State & edge case** — empty/loading/error/success, batas input, perilaku saat gagal. Ini yang paling sering hilang dan paling mahal di build.
6. **Token desain** — warna/ukuran/jarak hasil komputasi CSS, bukan perkiraan mata.
7. **Unknown yang jujur** — dengan probe dan dampak. `blocking` > 0 berarti `builders_ready: false`.

## Aturan kesiapan
- `builders_ready: true` hanya bila: tidak ada unknown `blocking`, semua kategori wajib profil berstatus COVERED (atau PARTIAL dengan alasan), dan setiap `must` punya tes terima.
- Bila `builders_ready: false`, tulis `next_actions` — siapa mengerjakan apa, dengan alat apa.
- Handoff tidak boleh memuat kode yang ditulis DID, tidak boleh memakai Replica Skill, tidak boleh mendaftarkan MCP.

## Cara menerbitkan
```bash
python3 scripts/provider_snapshot.py                     # bukti kapabilitas alat
python3 scripts/did_validate.py validate --target <t> --render
python3 scripts/did_validate.py bench --handoff runs/<t>/did/handoff.json --truth benchmarks/<t>/ground_truth.json
```
`--render` menulis `runs/<t>/did/SPEC_DID.md` (untuk manusia) dan `reports/<t>/did-validation.json` (untuk mesin/gate).

## Anti-pola
- Spesifikasi 40 halaman tanpa `handoff.json` → tidak bisa digerbang, tidak bisa dibenchmark.
- Menandai `builders_ready: true` sambil menyimpan `blocking` unknown.
- Menyalin teks marketing target ke `summary`.
- Menyerahkan `must` yang bersandar pada INFERRED 55.
