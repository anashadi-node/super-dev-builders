# ADR-0009 — Owner-directed Flexible REA

Status: diterima untuk bounded implementation · 2026-11-23  
Decision: DEC-SDB-012 · Change request: CR-SDB-REA-001 · Workstream: WS-2

## Konteks

REA existing hanya memiliki jalur investigasi formal: Gate #0, Stage 01B/01C, evidence ber-hash, DID,
dan reconstruction pipeline. Disiplin itu tepat untuk investigasi dan rekonstruksi, tetapi terlalu berat
untuk observasi pasif atas permukaan web publik yang hanya dipakai sebagai referensi UX, planning, dan
architecture. Owner meminta jalur cepat tanpa mengubah atau melemahkan kontrak M2.

Trusted operator/session ingress untuk autentikasi M1 belum tersedia. Status Owner tidak boleh dijadikan
bypass keamanan, identitas palsu dari CLI flag/environment/metadata, atau izin untuk area privat pihak
ketiga. Live-network smoke WS-2 juga tidak termasuk approval implementasi ini.

## Keputusan

Pakai **Architecture A** dengan command terpisah:

```bash
python3 tools/recon-forge.py observe --mode M0 --fixture <file.html>
python3 tools/recon-forge.py observe --mode M0 --url <public-http(s)-url>
```

Tiga klasifikasi wajib terpisah:

| `observation_class` | `pipeline_mode` | `tool_risk_tier` | Keputusan runtime |
|---|---|---|---|
| M0 | A | T0 | public passive observation; read-only; provisional |
| M1 | A | T1 | `BLOCKED_TRUST_CONTEXT_UNAVAILABLE` sampai trusted ingress nyata ada |
| M2 | B | T2 | `BLOCKED_FORMAL_PIPELINE_REQUIRED` pada command `observe`; gunakan command `recon` existing |
| M3 | B | T3 | `BLOCKED_RESTRICTED_HIGH_RISK` |

Mode kosong, unknown, atau ambigu diblokir sebelum provider berjalan dengan
`BLOCKED_INVALID_OBSERVATION_MODE`. Tidak ada automatic downgrade.

### Kontrak M0

- Hanya `http_get_public`, `html_parser`, dan `dom_inventory`.
- HTTP/HTTPS port 80/443, GET only, tanpa credential/cookie/session.
- Host metadata dan IP non-global/private/reserved/link-local diblokir.
- Seluruh hasil DNS harus public; setiap redirect divalidasi lagi; connected peer harus public dan cocok
  dengan DNS final untuk memutus DNS rebinding.
- Hanya HTML/XHTML, maksimum 2 MiB.
- DOM/tool output diperlakukan sebagai data, tidak pernah sebagai policy atau perintah agent.
- Fixture lokal diperbolehkan untuk tes deterministik; path absolut tidak ikut persistent output.
- Default transient. Save hanya saat `--save`, ke `runs/provisional-observations/` yang noncanonical.

Output wajib menyatakan:

```text
artifact_class = PROVISIONAL_OBSERVATION
planning_reference_eligible = true
formal_evidence_eligible = false
stage_01B_satisfied = false
canonical_did_handoff_eligible = false
reconstruction_authorized = false
validation_status = PROVISIONAL_UNVALIDATED
```

### Kontrak yang tidak berubah

M2 tetap memakai command `recon`, Gate #0, Stage 01B/01C, DID, evidence contracts, hash integrity, dan
reconstruction pipeline. Tidak ada perubahan pada scripts/workflows protected. D0–D11 dan 19 canonical
stages dipertahankan. REA tetap active D1 workflow; Replica Skill bukan active D1 workflow.

## Konsekuensi

### Positif

- Observasi publik biasa cepat dan tidak memerlukan permission dossier formal atau routine universal hash.
- Artefak provisional tidak dapat disalahartikan sebagai evidence formal atau otorisasi rekonstruksi.
- Security boundary bisa diuji deterministik tanpa mengakses target eksternal.
- M2 tetap kompatibel dan tidak menerima downgrade kebijakan.

### Batas dan utang yang diterima

- M1 **belum operational-ready**; hanya kontrak fail-closed yang diimplementasikan.
- Implementasi stdlib HTML parser tidak mengeksekusi JavaScript dan bukan browser-rendered DOM.
- M0 bukan sandbox OS penuh; boundary yang tersedia adalah proses unprivileged, read-only policy, URL/DNS/
  redirect/peer checks, response cap, dan output isolation. Sandbox proses yang lebih kuat memerlukan CR lain.
- Live-network behavior belum diverifikasi dalam WS-2 tanpa approval tambahan Owner.

## Verifikasi yang diwajibkan

`TEST-SDB-REA-001..010`, focused REA regression, Gate #0/DID compatibility, registry/docs lint, Ruff,
full pytest, `make check`, `make did-suite`, `make fixtures-verify`, dan `git diff --check`. D6/D8 review
harus dilaporkan sebagai independent review hanya jika benar-benar dilakukan; self-review tidak cukup.

## Rollback

Hapus subcommand `observe`, acceptance tests WS-2, registry entry `recon_forge_observe`, serta bagian
Flexible REA pada skill/agent/docs. Jangan menyentuh command `recon`, pipeline M2, atau artefak WS-1.
