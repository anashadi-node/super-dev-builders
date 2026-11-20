# SDB C1-02 — HASIL BE-SP-03 API CONTRACT ENGINEERING

**Tanggal:** 2026-11-20 · **Mode:** BROWNFIELD_RECOVERY → CHANGE_ONLY
**Status akhir scope:** `PASS_VERIFIED_SUBSCOPE` (final local commit SHA dilaporkan dalam respons Hermes, sesuai §10.8)

## 1. Baseline

- Baseline SHA: `abc0cc3fb5a52fb2eed44e238e2425f19a6ce980` (commit C1-01 BE-SP-12, ancestor terverifikasi via `git merge-base --is-ancestor` exit 0).
- Branch: `feat/c2b2g-ci-hardening`. Working tree awal: bersih kecuali file terlindungi `reports/SDB_NEW_SESSION_CONTINUATION_RESULT.md` (tidak disentuh, tidak di-stage).

## 2. File yang berubah (semua dalam allowlist §3)

| File | Sifat | Ukuran |
|---|---|---|
| `fixtures/contracts/control_plane_v1.json` | BARU — kontrak mesin | 8.956 B |
| `tests/test_be_sp03_contract.py` | BARU — T1–T10 | 28.172 B |
| `registry/capability_pilot.yaml` | EDIT — entri BE-SP-03 (+15 baris) | — |
| `docs/BE_SP03_API_CONTRACT.md` | BARU — ringkasan manusia (opsional §3.4) | — |
| `docs/INDEX.md` | EDIT — +1 baris entri indeks untuk dokumen di atas (efek mekanis wajib `make docs-lint`; pola sama dipakai BE-SP-12, baris 138) | — |
| `reports/SDB_C1_BE_SP03_RESULT.md` | BARU — laporan ini | — |

File produksi `sdb_platform/control_plane/app.py` + `store.py`: **READ-ONLY, nol byte berubah** (bukti: `git diff --stat` hanya registry, `git status --porcelain` hanya 5 file di atas). Tidak ada defect produksi yang ditemukan sehingga tidak ada change request ke source.

## 3. Kontrak API yang dibuat

Dua keluarga endpoint (divalidasi keberadaannya lebih dulu via pembacaan source + eksperimen loopback):

- `POST /v1/jobs` — 5 field wajib bertype; sukses 201 baru / 200 replay idempotent; 9 kode error teruji satu per satu (tabel error dieksekusi, bukan sekadar dibaca).
- `GET /v1/jobs/:id` — sukses 200; 401 unauthorized; 404 job_not_found.
- `POST /v1/jobs/:id/finish` dicatat sebagai endpoint dicabut (410 endpoint_removed, tanpa auth check).
- Kontrak mendefinisikan: method/route, request fields+tipe, response fields+tipe (job_object 15 field), error/status, auth (X-API-Key, SHA-256, compare_digest), authz (admin key ditolak di rute tenant; tenant suspended 403), isolasi tenant (404 masking), versi API (v1), producer/consumer, provenance source, dan aturan kompatibilitas (breaking vs additive).

## 4. Hasil pengujian (exit code nyata)

| Pengujian | Perintah | Hasil | Exit |
|---|---|---|---|
| Focused T1–T10 | `.venv/bin/python -m pytest tests/test_be_sp03_contract.py -q -o addopts=""` | **11 passed** in 0.60s | **0** |
| Regression API/security/BE-SP-12 | `pytest tests/test_admin_status.py tests/test_audit_regressions.py tests/test_capability_evidence.py -q -o addopts=""` | **101 passed** in 14.33s | **0** |
| Hygiene | `make hygiene` | PASS (0 FAIL, 3 WARN pre-existing file vendor/laporan lama >512KB) | **0** |
| Full gate | `make check` | lihat §9 (dijalankan setelah laporan ini ditulis, hasil dalam respons Hermes) | — |

Rincian T: T1 valid 201/200/GET+replay; T2 5 field wajib masing-masing ditolak sesuai kontrak; T3 11 kasus payload tidak sah; T4 tanpa/salah/admin-key/suspended → 401/403; T5 lintas-tenant 404 masking + idempotency per-tenant; T6 envelope + header + Content-Length cacat + >256KB; T7 tabel error dieksekusi penuh (14 kode POST + 2 kode GET, assertion set-equality kontrak↔trigger); T8 tanpa kebocoran (key tidak di-echo, tanpa stack trace/tenant-id tenant lain); T9 mutasi; T10 invarian.

## 5. Mutation testing (T9, pada salinan scratch — bukan file repo)

| Mutan | Baseline sehat | Mutan | Terdeteksi |
|---|---|---|---|
| Guard auth `tid = self._tenant(h)` dihapus di salinan `app.py` blok `POST /v1/jobs` | `RESULT 401 unauthorized` | `RESULT 404 tenant_not_found` | ✅ contract test T4 membunuh mutan |
| Validasi field wajib `type` dihapus di salinan `store.py` (`create_job`) | `RESULT 400 invalid_type` | `RESULT 201` | ✅ contract test T2 membunuh mutan |

Kedua salinan dibuat via `shutil.copyfile` ke `tmp_path` pytest; file repo tidak tersentuh.

## 6. Evidence BE-SP-12

- Capability ID: `BE-SP-03`; level `AGENT_REPORTED` (klaim `INDEPENDENT_REVIEW` tidak dibuat).
- Direkam dengan CLI `scripts/sdb_capability_evidence.py record` SETELAH commit final, terikat pada revision commit final (sesuai §6: evidence baru setelah commit agar sesuai revision terbaru).
- Path: `runs/capability/BE-SP-03/<revision-40hex>.json` — **di luar Git** (`/runs/*` di .gitignore, terverifikasi baris 67).
- Artifact hash + hasil tes aktual (11 passed) dimuat dalam evidence; divalidasi dengan `sdb_capability_evidence.py validate --expect-revision <final> --repo .` (exit code dilaporkan dalam respons Hermes).

## 7. Temuan D6 (code review) / D8 (security review) — delta

- **HIGH/BLOCKER baru: tidak ada.**
- D6: delta hanya menambah fixture+test+entri registry; tidak ada perubahan source produksi; test memakai pola loopback+`:memory:` yang sudah ada di repo; tidak ada pengelemahan tes/security.
- D6 catatan: server uji menaikkan default rate (`SDB_RATE_PER_MIN=60000`) hanya dalam fixture pytest supaya ~40 request lintas-test tidak memicu 429 palsu (kapasitas default 600/min ≈ 20 token). Mekanisme limiter TETAP diverifikasi penuh via tenant khusus `rate_per_min=1` (T7: burst 8 → 429 + `Retry-After`, dan tenant lain tetap terlayani). Env di-restore setelah `serve()`.
- D8: keys dalam test adalah data sintetis (izin §1); tidak ada secrets; tidak ada akses pihak ketiga (semua loopback); T8 memperkuat klaim no-leak (key tidak di-echo, tidak ada stack trace, header nosniff/no-store).

## 8. Final local commit

SATU commit lokal berisi tepat 5 file allowlist (§2). Full SHA dilaporkan dalam
respons Hermes (§10.8). Tidak ada push/PR/merge (larangan §1 dipatuhi).

## 9. Remaining risks

1. **Kontrak hanya 2 keluarga endpoint** — rute lain (`/v1/usage`, `/v1/artifacts`, `/v1/tenants`, worker endpoints) belum berkontrak; perilaku mereka belum terikat tes kontrak.
2. **Anchor mutasi T9 rawan drift**: mutasi berbasis teks eksak (`tid = self._tenant(h)` di blok POST /v1/jobs; baris `_require(... type in JOB_TYPES ...)`) — refactor penamaan di source akan membuat tes gagal di `_mutate` assertion (gagal keras/aman, bukan silent pass), tapi perlu pembaruan anchor.
3. **Batas kewenangan**: status hanya sampai `PILOT_VERIFIED_SUBSCOPE`; dispatcher SDB belum memanggil capability ini secara nyata — `INTEGRATED_VERIFIED` tidak diklaim.
4. `quota_jobs_exceeded` diuji via override `limits.jobs_per_month=2` (bukan nilai starter asli 50) untuk menjaga determinisme & kecepatan; jalur kode yang dilalui identik.

## 10. Rekomendasi capability berikutnya

`BE-SP-04` (jika Owner menyetujui): perluas kontrak ke keluarga endpoint kedua
yang paling berisiko secara operasional — `/v1/usage` + `/v1/artifacts`
(melengkapi siklus hidup job), memakai pola fixture kontrak + trigger map +
mutasi terarah yang sama sehingga biayanya rendah. Alternatif: integrasi
dispatcher yang benar-benar memanggil BE-SP-03 untuk mengangkat status ke
`INTEGRATED_VERIFIED`.
