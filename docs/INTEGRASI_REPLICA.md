# Integrasi Replica Skills × REA — Laporan Riset & Keputusan Arsitektur

Tanggal: 30 Oktober 2026
Acuan utama (keduanya dari Owner):
1. `PRD_Super_Dev_Builders.html` — pipeline F0–F8, gerbang G0–G3, kelas otorisasi A–D, eksperimen E1–E7.
2. `Super_Dev_Builders_REA_Replica_Master_PRD.html` — gate G0–G4, threat model, benchmark A/B/C.

Status: **TERINTEGRASI TERBATAS** — helper statis aktif, kemampuan runtime tetap terkunci.
Tidak ada klaim "100% aman" atau "paritas sempurna" di dokumen ini.

---

## 1. Ringkasan eksekutif

REA sudah terintegrasi sejak 26 Okt 2026 (v6.8.0, CLI-first, terpin di luar repo).
Lubang utamanya: **Zona B kosong** — tidak ada jalur pembangunan clean-room yang
terikat aturan. Integrasi ini mengisi lubang itu dengan:

| Komponen | Sebelum | Sesudah |
|---|---|---|
| REA (Zona A) | Terintegrasi, terpin | Tidak berubah + rujukan PRD + klon-policy |
| Replica Skills (Zona B) | Tidak ada | Vendor terpin `integrations/replica-skill/` (52 file) |
| Skill jembatan | Tidak ada | `skills/replica-skill-pipeline` (ditulis SDB, bukan salinan upstream) |
| Kebijakan mengikat | Tersebar | `governance/policies/clone-policy.md` |
| Gate rilis | Manual | Prosedur tetap (pemindai otomatis: utang, lihat §5) |
| Bukti integritas | — | `PINNED.md` + `replica-skill-baseline.json` + 4 test regresi |

## 2. Audit sumber (G0 + G1) — apa yang BENAR-BENAR diperiksa

Diperiksa langsung di host ini, bukan dari ringkasan dokumen:

| Pemeriksaan | Metode | Hasil |
|---|---|---|
| Provenance | `git clone` + `git rev-parse HEAD` | `77c9436fb3d18c3d58169efb8caf4fe906b0dc51`, 2026-10-03 — **sama persis** dengan commit yang disebut PRD Lampiran B |
| Enumerasi file | `find -type f` | 52 file: 11 skill dir + tests + LICENSE + README + `.claude-plugin` |
| Hash tree | `sha256sum` seluruh file | `2d82e189...f36278` (tercatat di PINNED.md) |
| Test upstream | `pytest tests/` | **57 passed** |
| Network sink | grep import socket/urllib/requests/http + `subprocess`/`os.system`/`eval`/`exec` | **0 temuan** (semua helper stdlib: argparse, csv, json, math, struct, zlib, re, unicodedata) |
| Install hook | scan `.claude-plugin/*.json`, `.gitignore` | **0** postinstall/preinstall |
| Prompt injection di SKILL.md | scan pola override/exfiltrasi/credential | **0 temuan** |
| ruff keamanan (S/BLE/E9) pada kode vendor | `ruff check --isolated` | **0 temuan** |
| ruff gaya pada kode vendor | `ruff check` (repo rules) | 10 temuan GAYA (RUF046/RUF015/I001) — **tidak diperbaiki** karena akan merusak hash pin |

**Yang TIDAK diperiksa (jujur):**
- G2 penuh (VM terisolasi, egress deny, snapshot rollback) — tidak dijalankan. Uji 57 test
  berjalan di host ini, bukan sandbox. Risiko dinilai rendah karena helper tidak punya
  network/subprocess, tetapi ini **bukan** audit sandbox.
- Red-team prompt injection 50 payload (E2) — belum dijalankan.
- Uji canary rahasia (E3) — belum dijalankan.
- Kualitas keluaran pada target nyata (E1) — belum diukur. Inilah satu-satunya klaim
  "super berkualitas" yang SAH diverifikasi lewat benchmark, bukan lewat dokumen.

**Konvergensi bukti**: hasil audit lokal konsisten dengan Lampiran B PRD (57 test lulus,
0 socket, 0 proses anak, commit 77c9436). Dua sumber independen → tingkat keyakinan tinggi
untuk klaim statis; rendah untuk klaim runtime.

## 3. Keputusan arsitektur (dan yang DITOLAK)

| Keputusan | Alasan | Alternatif yang ditolak |
|---|---|---|
| **Vendor terpin di `integrations/`, bukan install ke Hermes global** | PRD §12 Phase 1–2; isolasi + rollback git; REA memakai pola sama | Install 11 skill ke `~/.hermes/skills/` (tidak bisa di-pin, campur dengan profil lain) |
| **Skill jembatan ditulis SDB, bukan salinan upstream** | Preseden REA: instruksi upstream tidak tahu gate SDB; salinan mentah = dua sumber kebenaran | Salin 11 SKILL.md apa adanya (melanggar aturan registry: skill pihak ketiga butuh pipeline + approval) |
| **CLI, bukan MCP** | REA MCP = 229 tool / 3,79 MB skema; PRD #2 juga memilih CLI/stdio terbatas | Daftarkan MCP penuh (konteks boros, permukaan serangan lebar) |
| **Pack: architect + reviewer, BUKAN builder** | ADR-0003 membatasi 25 skill/peran; sdb-builder sudah 25. Kurasi skill lain butuh keputusan Owner | Naikkan batas ADR-0003 (melanggar keputusan arsitektur yang sudah disetujui) |
| **Exclude `integrations/` dari ruff GAYA saja** | Kode vendor tidak boleh diubah (hash pin); ruff-inti tetap memindai dan hasilnya 0 | Perbaiki 10 temuan gaya (merusak pin) |
| **Gate rilis: prosedur tetap, pemindai otomatis menyusul** | Mengklaim "0 aset sama" tanpa alat = klaim palsu. Lebih jujur menyatakan utang | Menulis pemindai setengah jadi lalu menyebutnya selesai |

## 4. Pemetaan divisi SDB ↔ peran PRD

| Peran PRD | Divisi SDB | Akses |
|---|---|---|
| Intake & Authorization | D1 recon + `reconstruction-scope-gate` | tulis `authorization.yaml`, gate0 |
| Target Classifier & Evidence Planner | D1 | tulis `evidence/` |
| REA Investigator | D1/D3 | Zona A; tier T0–T3 |
| Clean-Room Spec Reviewer | D3 | verifikasi SPEC lolos G1 |
| Recon & Product Spec | D1/D3 | `reconstruction-spec` |
| Parity / Visual Diff Evaluator | D7 | `replica-skill-pipeline` (parity/imgdiff/contrast) |
| IP / License / Privacy Reviewer | D8 security | G3 |
| Builder | D4/D5 | hanya SPEC; aturan via `clone-policy.md` |

## 5. Utang yang diakui (tidak disembunyikan)

1. Pemindai G1 otomatis (spesifikasi teks-only) — belum ada; saat ini review manusia.
2. Pemindai G3 otomatis (hash aset, string ≥40 char, rahasia) — belum ada.
3. `audit-log.jsonl` append-only per panggilan tool — belum ada.
4. Uji canary Zona A tiap sesi — belum ada.
5. Benchmark E1–E7 + A/B/C — belum dijalankan. **Tanpa ini, klaim "sangat super
   berkualitas" belum punya bukti empiris.** Rencana: fixture milik sendiri
   (web CRUD kecil, SaaS ber-auth, game kecil), ≥3 run, metrik recall/presisi/paritas.
6. G2 sandbox penuh untuk vendor.

Aturan: utang 1–4 WAJIB ditutup sebelum target pihak ketiga kelas B/C. Untuk target
kelas A milik sendiri, pipeline boleh dipakai sekarang dengan review manusia.

## 6. Cara memakai (jalur bahagia)

```bash
# 0. Gate #0 — target harus punya izin
python3 scripts/gate_check.py --target <slug>

# 1. Zona A: analisis (REA) → bukti di evidence/<slug>/
# 2. Spesifikasi lolos G1
#    reconstruction/<slug>/SPEC.md + FEATURE_MATRIX.md  (skill reconstruction-spec)
# 3. Zona B: bangun dari SPEC saja
# 4. Verifikasi (D7)
python3 integrations/replica-skill/replica-diff/parity.py \
    reconstruction/<slug>/features.csv --json
# 5. G3 rilis: checklist clone-policy.md §6 + approval manusia
```

## 7. Rujukan

- `integrations/replica-skill/PINNED.md` — provenance, hash, hasil audit
- `integrations/rea/PINNED.md` — REA 6.8.0
- `governance/policies/clone-policy.md` — kebijakan mengikat
- `tests/test_replica_integration.py` — 4 test regresi integritas
- `reports/REA_AUDIT_20261026.md` — audit REA
