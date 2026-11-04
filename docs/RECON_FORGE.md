# recon-forge — orkestrator copy-cloning SDB (REA + SDB + Craft Anything)

Tanggal: 4 November 2026 · Status: **aktif, teruji** (`tests/test_recon_forge.py`, 21 uji)

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
python3 tools/recon-forge.py recon  --target <t> --kind native --path targets/<t>/native/app
python3 tools/recon-forge.py recon  --target <t> --kind native --path targets/<t>/native/app \
        --decompile --decompile-limit 50             # perlu provider (Ghidra + JDK 21)
python3 tools/recon-forge.py parity --target <t> --original-url ... --rebuilt-url ...
python3 tools/recon-forge.py report --target <t>
python3 tools/recon-forge.py build  --target <t> --engine replica   # G1 wajib PASS
python3 tools/recon-forge.py build  --target <t> --engine craft     # hanya bila biner terpin
python3 tools/recon-forge.py chain  --target <t> --original-url ... --rebuilt-url ...
```

Jalur `--kind native` hanya menerima path di dalam akar izin: `targets/<t>` dan
path yang dideklarasikan di `evidence/<t>/authorization.yaml` (`repos`, `apps`,
`apk_ipa_binaries`). Path di luar itu ditolak sebelum REA dipanggil (exit 2).

Artefak yang dihasilkan:

```
evidence/<t>/rea/manifest.json          # daftar artefak + sha256 + engine + waktu
evidence/<t>/rea/<stamp>-web-bundle.json
evidence/<t>/rea/<stamp>-screenshot.json
evidence/<t>/rea/<stamp>-inspect.json          # jalur native
evidence/<t>/rea/<stamp>-decompiled/           # jalur native, sha256 = digest pohon
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
8. `recon --kind native` menolak path di luar akar izin (`targets/<t>` + deklarasi
   `authorization.yaml`) — exit 2, REA tidak pernah dipanggil.
9. Provider biner gagal (mis. Ghidra tanpa JDK yang bisa dipakai) → **exit 5**,
   `unknowns` berisi penyebab, pesan menyatakan "Bukti tidak dikarang". Tidak ada
   manifest yang mengklaim `verified: true`.
10. Artefak direktori di-hash sebagai **digest pohon** (`relpath` + isi tiap berkas,
    urut nama) sehingga tidak pernah tercatat `sha256: null` / `bytes: 0`.

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

Jalur biner diuji pada target yang sama dengan subjek milik sendiri
(`targets/forge-demo/native/hello-elf`, 26.936 B, ELF 64-bit PIE x86-64, `stripped`).
Subjek itu **tidak di-commit**: isinya identik dengan `/usr/bin/true` host (GNU coreutils,
GPLv3) — menaruhnya di repo BUSL-1.1 mencampur lisensi tanpa keputusan Owner, dan
`targets/` memang dijadwalkan keluar dari git. Reproduksi lokal:

```bash
mkdir -p targets/forge-demo/native
cp /usr/bin/true targets/forge-demo/native/hello-elf   # sha256 8a63c983…
```

| Tahap | Hasil |
|---|---|
| `recon --kind native` (REA `inspect`, provider Ghidra 12.1.4) | 1 artefak, `20261104T223334-inspect.json` 8.424 B, sha256 `82387f2f…` |
| `--decompile --decompile-limit 10` | `20261104T223334-decompiled/` **46.191 B / 12 berkas**, digest pohon `3a5fb8ad…` (diverifikasi ulang lewat `sha256sum` shell, cocok) |
| Identitas subjek | sha256 `8a63c983…`, BuildID `ea23a64e…` |
| Pemeriksaan kebocoran | `strings` untuk `anashadi`, `/home/`, `password`, `token`, `@`, `secret` → **tidak ada** |

Syarat jalur native di host ini: Ghidra 12.1.x + **JDK 21 yang utuh**. JDK hasil
`dpkg-deb -x` tidak otomatis portabel — `conf/security/*` menunjuk ke
`/etc/java-21-openjdk/*` yang tidak ada tanpa paket sistem, dan Ghidra gagal dengan
`Error loading java.security file` walau `java -version` normal. Karena itu
`jdk_ok()` memeriksa isi (`bin/java` tidak kosong + `JAVA_VERSION=` di `release`),
dan `doctor` menampilkan `native_ready` hanya bila tidak ada penghambat
(`ghidra`, `ghidra-java`, `ghidra-headless`, `java`, `node`).

Catatan jujur: `rea doctor` di host ini masih melaporkan `healthy=false`, tetapi bukan
karena Node/Ghidra/Java — ketiganya sehat (Node 26.13.0, Ghidra 12.1.4, JDK 21.0.12.1).
Yang gagal hanya komponen opsional/registrasi: `ida-registration`, `jadx`,
`kuna-installation`, `skill:identity`, dan `registration:*`. `doctor` alat ini
menampilkan fakta itu apa adanya, tidak menyembunyikannya dan tidak menjadikannya
penghambat jalur yang benar-benar dipakai.

## 6. Batas yang diketahui

- Jalur `recon` mendukung **web** (CDP) dan **native** (`--kind native --path ...`,
  lewat `rea inspect` / `decompile-all`). Jalur native butuh provider decompiler;
  tanpa provider hasilnya exit 5 + penyebab, bukan manifest palsu.
- Paritas baru bisa diukur setelah ada hasil bangun. Tanpa rebuild, `parity` = `UNPROVEN`.
- `craft-anything` **belum terpasang** — pilot wajib dari rilis resmi v0.3.0 + checksum,
  dijalankan di direktori terpisah, `clean-room` saja.
- `--decompile` menghasilkan digest pohon direktori; verifikasi ulang butuh
  algoritma yang sama (relpath + isi berkas terurut), bukan `sha256sum` satu berkas.
- Skor `mean_coverage` adalah rata-rata dimensi terukur; dimensi yang tidak terukur tidak
  dihitung nol (itu akan menyesatkan), tetapi juga tidak dianggap lulus.

## 7. Rujukan

- `docs/INTEGRASI_REA.md` — integrasi REA (Zona A) dan keputusan CLI-first.
- `docs/INTEGRASI_REPLICA.md` — integrasi `replica-skill` (Zona B) dan kebijakan clone.
- `governance/policies/clone-policy.md` — aturan mengikat.
- `tools/recon-forge.py` — kode; `tests/test_recon_forge.py` — 21 uji.
