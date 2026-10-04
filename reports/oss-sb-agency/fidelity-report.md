# Reconstruction Fidelity — oss-sb-agency

Dibuat: 2026-10-04T15:13:40+0700

Tidak ada skor tunggal. Skor tinggi dengan coverage rendah = laporan menyesatkan.

| Dimensi | Status | Coverage | Evidence | Catatan |
|---|---|---|---|---|
| visual | ok | 0.66 | verification/oss-sb-agency/diffs/visual-index.png | pixel diff full-page /index.html (coverage = 1 - rasio piksel berbeda; selisih gaya disengaja dilaporkan apa adanya) |
| navigation | ok | 1.00 | normalized/oss-sb-agency/screens.json | Jaccard tautan (original=14, rebuild=14) |
| interaction | ok | 1.00 | capture.json#pages[].interaction.effect | selector sama=True; dialog original/rebuild=1/1; aria-expanded=None/None; dom_delta=186/-10 |
| responsive | ok | 0.57 | verification/oss-sb-agency/diffs/visual-mobile.png | pixel diff pada viewport mobile (dari capture --viewport yang dipakai) |
| functional | ok | 1.00 | normalized/oss-sb-agency/inventory.json | status HTTP per halaman sama |
| accessibility | ok | 1.00 | normalized/<target>/components.json | fitur original terpenuhi 6/6 |
| performance | ok | 1.00 | capture.json#pages[].load_ms | load original 3428 ms vs rebuild 1583 ms (coverage=rasio dibatasi 1.0) |
| api_contract | NOT_OBSERVED | - | normalized/<target>/network.json | tidak ada panggilan API yang diobservasi — tidak diklaim setara, tidak dikarang |

Dimensi tambahan: external_dependency

## Aturan pelaporan
- Wajib menyertakan coverage; tanpa coverage laporan tidak diterima.
- Perbedaan yang disengaja (lisensi aset, keputusan desain) dicatat sebagai intentionally_changed.
- Dilarang mengklaim 'identik'.
