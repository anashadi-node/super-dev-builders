# Benchmark E1 — Pilot (2026-10-30)

Status: **PILOT** — bukan bukti kualitas skala produksi. Baca bagian batas di akhir.

## Pertanyaan yang diuji

Apakah jalur "spesifikasi clean-room (G1) → replika" mereproduksi perilaku target
lebih akurat daripada replika tanpa spesifikasi (tebakan REST generik)?

## Metode

- Target: `targets/e1-app/` — aplikasi HTTP milik sendiri (kelas A), 10 fitur,
  Gate #0 PASS (`reports/e1-app/gate0-verdict.json`).
- Zona A: `benchmarks/e1/probe.py` — 16 observasi buta, tanpa membaca source.
  Bukti: `evidence/e1-app/observations.json` (E1–E16).
- Zona D3: `reconstruction/e1-app/SPEC.md` (66 baris) + `features.csv`.
- Zona B: `reconstruction/e1-app/replica/serve_spec.py` — ditulis hanya dari SPEC
  (bukan dari source target).
- Kontrol: `reconstruction/e1-app/replica-naif/serve_naif.py` — tebakan REST wajar,
  sengaja tanpa SPEC: 200 untuk semua sukses, galat `message`, tanpa auth,
  tanpa validasi, tanpa paginasi/filter.
- Uji buta: `benchmarks/e1/checks.py` — 10 uji perilaku, dijalankan identik pada
  ketiga server. Tiap uji membersihkan item yang dibuatnya.
- Repetisi: 3 run berurutan per server.

## Hasil

| Server | Run 1 | Run 2 | Run 3 | Paritas |
|---|---|---|---|---|
| Target (acuan) | 10/10 | 10/10 | 10/10 | 100% |
| Replika dari SPEC | 10/10 | 10/10 | 10/10 | **100%** |
| Kontrol naif (tanpa SPEC) | 2/10 | 2/10 | 2/10 | **20%** |

Metrik:

| Metrik | Nilai |
|---|---|
| Recall replika (perilaku target direproduksi) | 1,00 (10/10) |
| Presisi spesifikasi (klaim SPEC yang benar) | 1,00 (10/10) |
| Delta paritas (SPEC − kontrol) | **+0,80 (80 poin persentase)** |
| Stabilitas antar-run | identik 3/3 (0 variasi) |
| Ukuran kode | target 152 baris; replika 141 baris (rasio 0,93) |

Butir yang GAGAL di kontrol: F03 (201 vs 200), F05 (PATCH tanpa token tidak 401),
F06 (204 vs 200), F07/F08 (galat `message` vs `error`, tanpa validasi 422),
F09 (tanpa paginasi), F10 (tanpa filter). F01/F04 lolos karena perilakunya umum.

## Tafsir jujur

**Yang dibuktikan:**
1. Mekanisme pipeline jalan ujung-ke-ujung: Gate #0 → observasi → SPEC → replika → uji
   buta → metrik.
2. Spesifikasi menutup celah yang paling sering salah pada tebakan: kode status,
   bentuk galat, otorisasi, validasi, paginasi/filter.
3. Hasil stabil 3/3 run — tidak ada fluktuasi karena state uji dibersihkan.

**Yang TIDAK dibuktikan (batas pilot):**
1. **n = 1 target, 10 fitur.** PRD menuntut ≥30 fitur & beberapa target sebelum klaim
   kualitas. 100% di mainan 10 fitur tidak dapat digeneralisasi ke SaaS 200 fitur.
2. **Penulis SPEC = penulis target = penulis replika.** Ini simulasi peran, bukan
   clean-room independen. Pengetahuan awal tentang target bisa bocor ke SPEC.
   Uji nyata butuh pembangun berbeda yang hanya melihat SPEC.
3. **Sirkularitas parsial:** uji diturunkan dari SPEC, jadi replika yang mengikuti SPEC
   secara struktural diuntungkan. Yang diukur adalah "apakah SPEC ditransfer benar",
   bukan "apakah pipeline mengalahkan engineer manusia".
4. **Kontrol ditulis oleh agen yang sama** yang tahu kontrol "seharusnya generik" —
   risiko bias ke arah perlakuan. Mitigasi: kontrol memakai pola REST yang lazim,
   bukan kesalahan yang dibuat-buat.
5. Tidak mengukur biaya waktu manusia, kualitas visual, aksesibilitas, atau performa.

## Rekomendasi falsifiable

- **H1:** pada 3 target baru ≥30 fitur dengan pembangun independen, paritas SPEC ≥ 0,90
  dan delta ≥ 0,30. Verifikasi: ulangi protokol ini; tolak H1 bila paritas < 0,90.
- **H2:** kesalahan tersering replika tanpa SPEC = kode status + bentuk galat.
  Verifikasi: kategorikan kegagalan kontrol pada 10 target; tolak bila < 60% kegagalan
  berasal dari dua kategori itu.

## Berkas

- `benchmarks/e1/{probe.py,checks.py,run_benchmark.py}`
- `benchmarks/e1/results/20261030-run{1,2,3}.json`
- `evidence/e1-app/{authorization.yaml,observations.json}`
- `reconstruction/e1-app/{SPEC.md,features.csv,replica/,replica-naif/}`
