# recon-forge — orkestrator copy-cloning SDB (REA + SDB + Craft Anything)

Tanggal: 4 November 2026 · Status: **aktif, teruji** (`tests/test_recon_forge.py`, 13 uji)

## 1. Masalah yang diselesaikan

Sebelum alat ini, jawaban atas pertanyaan "apakah SDB punya tool yang memakai REA untuk
copy-cloning?" adalah **tidak**. Yang ada hanya bahan dan panduan:

| Sudah ada | Tetapi |
|---|---|
| REA 6.8.0 (terpin, MIT) | Hanya dipanggil agen secara manual; **nol skrip** di `scripts/` menyentuh REA |
| `skills/replica-skill-pipeline` (Zona B) | Berupa instruksi untuk agen, bukan perintah yang bisa dijalankan/diulang |
| `scripts/capture_web.py` + `fidelity_compare.py` | Kuat, tapi terpisah; tidak terhubung ke REA maupun ke gate |
| Tahap `01B RECON/EVIDENCE PACKAGE` | Hanya memeriksa **keberadaan berkas** (`evidence/{t}/**/*.json`), bukan apakah bukti itu dipanen dengan alat dan lolos verifikasi |

Akibatnya "recon selesai" bisa berarti "ada satu berkas JSON di folder". Itu bukan bukti.

`tools/recon-forge.py` menutup tiga lubang sekaligus: **eksekusi** (REA benar-benar
dipanggil), **ketertelusuran** (sha256 per artefak), dan **gerbang** (tidak ada langkah
yang jalan tanpa Gate #0 PASS).

## 2. Pembagian peran — kenapa kombinasi, bukan pilih salah satu

| Lapis | Alat | Kenapa alat itu |
|---|---|---|
| Izin | `scripts/gate_check.py` | Kelas A/B/C/D, manifest `authorization.yaml`; satu-satunya sumber "boleh/tidak" |
| Bukti (Zona A) | **REA 6.8.0** | 41 jenis target, provider Ghidra/IDA/Hopper/JEB, deklarasi *effect* per operasi, keluaran Evidence + daftar *unknown* |
| Tangkapan | `scripts/capture_web.py` | Playwright terpin, hanya host di `allowed_targets`, rate-limit, tanpa login |
| Hakim paritas | `scripts/fidelity_compare.py` | 9 dimensi terukur (visual, navigasi, interaksi, API, fungsional, aksesibilitas, responsif, performa, dependensi eksternal) — angka, bukan opini |
| Pembangun (Zona B) | `replica-skill` (agen) **atau** `craft-anything` | Rebuild + loop perbaikan; **tidak membaca `evidence/`** |

Yang **tidak** dilakukan alat ini: membangun UI, mengarang skor, atau menyatakan rilis siap.
`release_ready` selalu `false` — rilis butuh G3 + approval manusia.

## 3. Perintah

```bash
python3 tools/recon-forge.py doctor                      # mesin apa yang benar-benar ada
python3 tools/recon-forge.py plan   --target <t> --kind web
python3 tools/recon-forge.py recon  --target <t> --url http://127.0.0.1:8201/
python3 tools/recon-forge.py parity --target <t> --original-url ... --rebuilt-url ...
python3 tools/recon-forge.py report --target <t>
python3 tools/recon-forge.py build  --target <t> --engine replica   # G1 wajib PASS
python3 tools/recon-forge.py build  --target <t> --engine craft     # hanya bila biner terpin
python3 tools/recon-forge.py chain  --target <t> --original-url ... --rebuilt-url ...
```

Artefak yang dihasilkan:

```
evidence/<t>/rea/manifest.json          # daftar artefak + sha256 + engine + waktu
evidence/<t>/rea/<stamp>-web-bundle.json
evidence/<t>/rea/<stamp>-screenshot.json
evidence/<t>/capture/{original,rebuilt}/capture.json
reports/<t>/parity-summary.json         # engines, dimensi terukur, mean_coverage
reports/<t>/recon-forge-report.{json,md}
runs/<t>/recon-plan.json                # rencana + aturan (tanpa eksekusi)
audit/audit-log.jsonl                   # rantai hash setiap aksi
```

## 4. Invarian keamanan (diuji, bukan dijanjikan)

1. Tanpa `reports/<t>/gate0-verdict.json` ber-verdict `PASS` → **exit 2**, tidak ada aksi.
2. Verdict milik target lain → ditolak.
3. URL di luar `allowed_targets` → ditolak.
4. `build --engine replica` tanpa `SPEC.md` → ditolak (G1 belum ada).
5. `build --engine craft` tanpa biner terpin → **exit 3** + instruksi rilis resmi (bukan `cargo install` HEAD).
6. Setiap tahap menulis entri `audit/audit-log.jsonl`; gagal mencatat = gagal jalan.
7. Laporan hanya menyebut berkas yang ada; yang tidak terukur ditulis `UNPROVEN`/`MISSING`.

## 5. Bukti uji nyata (4 November 2026, target `forge-demo`)

Target demo milik sendiri (`targets/forge-demo/`, dua halaman identik dengan 2 perubahan
warna/ukuran yang disengaja), Gate #0 PASS, dua server lokal.

| Tahap | Hasil |
|---|---|
| `recon` (REA 6.8.0 + Chromium CDP) | 2/2 artefak, `analyze-web-bundle` 4.559 B + screenshot 33.691 B, sha256 tercatat |
| `parity` (capture_web + fidelity_compare) | **5 dari 9 dimensi terukur**, `mean_coverage = 0,9951` |
| Visual | 0,9755 (selisih = warna & ukuran heading yang memang diubah) |
| Navigasi / fungsional / aksesibilitas / performa | 1,0 / 1,0 / 1,0 / 1,0 |
| Tidak terukur | interaksi, API, responsif (mobile), dependensi eksternal — dinyatakan `NOT_MEASURED`, bukan diklaim setara |
| `report` | 4 tahap: PASS, VERIFIED, PRESENT, MEASURED; tangga `release_ready=false` |

Catatan jujur: `rea doctor` di host ini melaporkan `healthy=false` karena Node 26.7.0 <
26.12.1 yang diminta. Operasi web tetap berjalan; `doctor` alat ini menampilkan fakta itu
apa adanya, tidak menyembunyikannya.

## 6. Batas yang diketahui

- Jalur `recon` saat ini **web-only** (CDP). Biner/firmware memakai `rea analyze` langsung;
  jalur non-web belum dibungkus di sini.
- `craft-anything` **belum terpasang** — pilot wajib dari rilis resmi v0.3.0 + checksum,
  dijalankan di direktori terpisah, `clean-room` saja.
- Paritas baru bisa diukur setelah ada hasil bangun. Tanpa rebuild, `parity` = `UNPROVEN`.
- Skor `mean_coverage` adalah rata-rata dimensi terukur; dimensi yang tidak terukur tidak
  dihitung nol (itu akan menyesatkan), tetapi juga tidak dianggap lulus.

## 7. Rujukan

- `docs/INTEGRASI_REA.md` — integrasi REA (Zona A) dan keputusan CLI-first.
- `docs/INTEGRASI_REPLICA.md` — integrasi `replica-skill` (Zona B) dan kebijakan clone.
- `governance/policies/clone-policy.md` — aturan mengikat.
- `tools/recon-forge.py` — kode; `tests/test_recon_forge.py` — 13 uji.
