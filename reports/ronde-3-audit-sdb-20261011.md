# Ronde-3 — Code Review, QA, Keamanan, Audit Assurance (seluruh ekosistem SDB)

Tanggal: 2026-10-11. Status: **INTERIM — LULUS BERSYARAT** (bukan "100% bersih"; lihat Batas Cakupan).

## Bukti segar
| Pemeriksaan | Hasil |
|---|---|
| pytest tests skills | 219 passed (166 -> 188 -> 219), tes baru gagal tanpa perbaikan |
| make check (lint, registry, test, drift) | exit 0 |
| CI GitHub (`fix(sdb): tutup 9 temuan ...`) | success |
| gitleaks (riwayat git + pohon berkas) | tidak ada rahasia terlacak |
| ruff S,B,BLE,E9,F | bersih setelah perbaikan |
| semgrep p/default | 4 temuan ditelaah; 5 aturan timeout (celah cakupan) |
| Reviewer independen (subagent) | passed=true, 0 Kritis/Tinggi, 10 temuan |

## Temuan dan status
| ID | Sev | Ringkas | Status |
|---|---|---|---|
| D-1 | Sedang | whoami memberi PIN ke `Host: evil.test` (DNS-rebinding) | DITAMBAL + tes |
| D-2 | Sedang | id proyek dari klien tanpa validasi (path traversal) | DITAMBAL + tes |
| D-3 | Sedang | `/server.py`, `/ws_api.py` disajikan HTTP 200 | DITAMBAL + tes |
| D-4 | Rendah | token non-ASCII -> TypeError; Content-Length negatif; token 0664 sesaat | DITAMBAL + tes |
| D-5 | Sedang | `REPO` hard-coded -> CI merah (404) | DITAMBAL |
| T-3 | Sedang | parser YAML fallback tanpa block scalar (ronde sebelumnya) | DITAMBAL |
| F-01 | Sedang | allowlist Gate #0 `capture_web` pakai startswith (`example.com.evil.test` lolos) | DITAMBAL + 25 tes |
| F-02,F-03,F-06,F-07,F-08,F-10 | Rendah | token kosong fail-open + race, rerun tahap 01/timpa, config non-dict 500, race approve, network.json 0644, path hard-coded | DITAMBAL |
| F-04 | Rendah | tahap 08-16 tak bisa dari web (desain: exec = brief) | pesan error diperjelas, perilaku sengaja |
| F-05 | Rendah | `--host 0.0.0.0`: HTTP tanpa TLS, `/api/state` tanpa PIN | peringatan startup; RISIKO DITERIMA |
| F-09 | Rendah | checksum bootstrap satu sumber dengan aset | trap EXIT ditambah; pin/cosign = RISIKO TERBUKA |

## Batas cakupan (jujur)
- Semgrep: 5 aturan timeout; temuan SRI `index.html` (aset lokal) dan karakter bidi di JSON pihak ketiga belum dibuktikan tidak berbahaya secara formal.
- Front-end `ws/*.js`, `*.html`: sink XSS dipindai pola, tidak dibaca baris demi baris.
- `skills/**`: 9 skrip utama dibaca penuh; sisanya hanya grep pola berisiko.
- `shellcheck` tidak terpasang. Scanner `dashboard` dijalankan atas persetujuan Owner 11 Okt.
- Tier tertinggi (tahap 11) wajib diulang; ronde ini tidak menggantikannya.
