# Reconstruction Fidelity — sdb-local-demo

Dibuat: 2026-10-05T20:38:25+0700

Tidak ada skor tunggal. Skor tinggi dengan coverage rendah = laporan menyesatkan.

| Dimensi | Status | Coverage | Evidence | Catatan |
|---|---|---|---|---|
| visual | match | 1.00 | verification/sdb-local-demo/diffs/visual-index.png | pixel diff full-page / (coverage = 1 - rasio piksel berbeda; selisih gaya disengaja dilaporkan apa adanya) |
| navigation | ok | 1.00 | normalized/sdb-local-demo/screens.json | Jaccard tautan (original=2, rebuild=2) |
| interaction | ok | 1.00 | capture.json#pages[].interaction.effect | selector sama=True; dialog original/rebuild=0/0; aria-expanded=None/None; dom_delta=3/3; status_text=True/True |
| responsive | NOT_MEASURED | - | - | capture mobile tidak dijalankan |
| functional | ok | 1.00 | normalized/sdb-local-demo/inventory.json | status HTTP per halaman sama |
| accessibility | ok | 1.00 | normalized/<target>/components.json | fitur original terpenuhi 6/6 |
| performance | ok | 1.00 | capture.json#pages[].load_ms | load original 914 ms vs rebuild 926 ms (coverage=rasio dibatasi 1.0) |
| api_contract | ok | 1.00 | capture.json#interaction.api_calls | 1 endpoint dibandingkan; status+kunci JSON sama=True |

Dimensi tambahan: external_dependency

## Aturan pelaporan
- Wajib menyertakan coverage; tanpa coverage laporan tidak diterima.
- Perbedaan yang disengaja (lisensi aset, keputusan desain) dicatat sebagai intentionally_changed.
- Dilarang mengklaim 'identik'.
