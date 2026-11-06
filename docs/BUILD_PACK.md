# Build Pack — dari handoff DID ke backlog Builders

Dokumen ini menetapkan kontrak `scripts/did_build_pack.py`. Tujuannya satu: mengubah
"kelihatannya sudah siap" menjadi "terbukti siap dibangun", dengan exit code.

## Mengapa bukan sekadar `builders_ready`

`handoff.json` punya bendera `handoff.builders_ready`. Bendera bisa diisi `true` tanpa
diperiksa, jadi bendera saja tidak membuktikan apa pun. Build pack menurunkan kesiapan
menjadi enam aturan yang dieksekusi; bila satu gagal, alat keluar dengan kode **1** dan
**tidak menulis** pack (kecuali `--allow-not-ready`, yang menandai hasilnya "PASS (paksa)").

| Kode | Aturan | Gagal bila |
|---|---|---|
| B01 | Fitur `must` punya acceptance test | ada fitur must tanpa `acceptance_tests` |
| B02 | Rujukan temuan valid | fitur merujuk id temuan yang tidak ada |
| B03 | Temuan punya alamat bukti | ada temuan tanpa `evidence` |
| B04 | Alamat bukti terdaftar | id bukti tidak ada di `evidence_manifest` |
| B05 | `build_seeds` terisi | `entities`, `api`, atau `states` kosong |
| B06 | Bendera kesiapan konsisten | `builders_ready=false` atau `blocking_unknowns>0` |

## Keluaran

```
runs/<slug>/did/BUILD_PACK.md     # untuk manusia: gerbang + tiket + tugas
runs/<slug>/did/build-pack.json   # untuk mesin/CI
```

`tiket_perbaikan` hanya dibuat dari temuan berstatus `OBSERVED` dengan severity
`critical|high|medium|low`, dipetakan ke P0/P1/P2 dan diurutkan. Temuan `INFERRED`
tidak menjadi tiket: dugaan bukan pekerjaan sampai ada bukti.

`tugas_build` memuat setiap fitur yang punya acceptance test beserta temuan terkait,
sehingga Builders bisa menutup bug dan membangun fitur dari satu daftar.

## Pemakaian

```bash
make did-pack TARGET=rt-rw-portal
# atau langsung
python3 scripts/did_build_pack.py --handoff runs/rt-rw-portal/did/handoff.json \
    --out-dir runs/rt-rw-portal/did
```

## Batas yang disengaja

- Pack **tidak** menjalankan tes penerimaan; ia memastikan tes itu ada dan terikat bukti.
  Eksekusi tetap tugas Builders (`tests/`) dan gerbang rilis.
- Pack **tidak** menilai kualitas klaim. Itu tugas `did_validate.py` (kontrak handoff)
  dan `did_validate.py bench` (presisi/recall terhadap label independen).
- Urutan P0/P1/P2 berasal dari severity temuan, bukan dari tebakan dampak bisnis.

## Hasil ukur (7 Nov 2026)

`make did-suite` — preset beku di `benchmarks/<target>/handoff.json`, label di `ground_truth.json`:

| Target | P | R | F1 | Halusinasi |
|---|---|---|---|---|
| android-mini | 1.000 | 1.000 | 1.000 | 0 |
| desktop-mini | 1.000 | 1.000 | 1.000 | 0 |
| e1-app | 0.909 | 1.000 | 0.952 | 0 |
| elf-demo | 1.000 | 1.000 | 1.000 | 0 |
| rt-rw-portal | 1.000 | 1.000 | 1.000 | 0 |

Catatan kejujuran pengukuran pada `rt-rw-portal`:

- Label diturunkan dari nama uji dan label modul milik target (33 berkas uji), **bukan**
  dari nama fitur handoff.
- Label sempat ditambah **satu kali** (Beranda, State kosong/izin/404) setelah SPEC
  memecah "Pengaduan & surat" serta "Masuk & peran" menjadi fitur terpisah. Penambahan
  itu menaikkan recall — karenanya angka 1.000 di baris ini **bukan** bukti label bebas
  dari SPEC; anggap sebagai batas atas, bukan hasil buta.
- Pencocokan label juga diperbaiki: sebelumnya "yang pertama cocok" membuat fitur
  beranda mencuri label kas (fitur kas lalu tercatat ekstra). Sekarang label jatuh ke
  fitur paling spesifik dengan skor; regresinya diuji di `tests/test_did_contract.py`.

