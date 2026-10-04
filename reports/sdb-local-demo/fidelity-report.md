# Reconstruction Fidelity — sdb-local-demo

Dibuat: 2026-10-04T08:55:35+0700

Tidak ada skor tunggal. Skor tinggi dengan coverage rendah = laporan menyesatkan.

| Dimensi | Status | Coverage | Evidence | Catatan |
|---|---|---|---|---|
| visual | ok | 0.99 | verification/sdb-local-demo/diffs/visual-index.png | pixel diff (perbedaan gaya sengaja diubah -> coverage < 1 adalah wajar) |
| navigation | ok | 1.00 | normalized/sdb-local-demo/screens.json | Jaccard tautan (original=2, rebuild=2) |
| interaction | ok | 1.00 | evidence/sdb-local-demo/capture/capture.json#interaction | klik #btn-load -> teks status berpola '<state> @ <ts>' |
| responsive | ok | 0.96 | verification/sdb-local-demo/diffs/visual-mobile.png | pixel diff pada viewport 390x844 |
| functional | ok | 1.00 | normalized/sdb-local-demo/inventory.json | status HTTP per halaman sama |
| accessibility | ok | 1.00 | normalized/sdb-local-demo/components.json | h1 + role=status + aria-label hadir di kedua versi |
| performance | ok | 1.00 | evidence/sdb-local-demo/capture/capture.json#pages[].load_ms | load original 902 ms vs rebuild 896 ms (coverage=rasio dibatasi 1.0) |
| api_contract | ok | 1.00 | normalized/sdb-local-demo/network.json | GET /api/status -> 200, kunci JSON sama (state, ts) |

## Aturan pelaporan
- Wajib menyertakan coverage; tanpa coverage laporan tidak diterima.
- Perbedaan yang disengaja (lisensi aset, keputusan desain) dicatat sebagai intentionally_changed.
- Dilarang mengklaim 'identik'.
