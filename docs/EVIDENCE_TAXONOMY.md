# Evidence Taxonomy — Anti-Halusinasi

Sumber: blueprint §4.6 (taxonomy) dan §4.7 (fidelity per dimensi).

## 1. Empat status wajib
| Status | Makna | Aturan |
|---|---|---|
| **FACT / OBSERVED** | didukung screenshot, DOM, trace, file, source, atau runtime evidence | boleh menjadi requirement fidelity |
| **INFERRED** | kesimpulan teknis dari beberapa evidence, tidak terlihat langsung | wajib `confidence` 0-100 + alasan; tidak boleh jadi dasar tunggal keputusan besar |
| **UNKNOWN** | tidak dapat ditentukan dari scope/evidence | **dilarang diisi tebakan**; architect mendesain implementasi baru yang sesuai requirement |
| **OUT OF SCOPE** | butuh akses/tindakan yang tidak diotorisasi | STOP; minta otorisasi/artefak dari Owner bila memang diperlukan |

Setiap record evidence wajib membawa: `provenance`, `captured_at`, `redaction_status`, `status`, `confidence` (bila INFERRED).

## 2. Reconstruction Fidelity — per dimensi, tanpa angka tunggal
| Dimensi | Evidence yang harus ada |
|---|---|
| Visual | screenshot diff pada viewport yang ditentukan |
| Navigation | route/screen graph + tested journeys |
| Interaction | form, dialog, state, keyboard/mouse/touch |
| Responsive | matriks breakpoint/device |
| Functional coverage | feature matrix: observed / reproduced / intentionally changed / unknown |
| Accessibility | axe + pemeriksaan manual untuk area yang automation tidak bisa pastikan |
| Performance | Lighthouse/runtime measurement + catatan environment |
| API contract | contract test observed/authorized (implementasi internal tidak perlu identik) |

Wajib melaporkan **coverage** (berapa persen area target yang benar-benar diperiksa) bersama skor per dimensi.
Skor tinggi dengan coverage rendah = laporan menyesatkan.

## 3. Anti-halusinasi operasional
1. Tidak ada klaim parity tanpa artefak pembanding.
2. Automated check (axe/lighthouse) tidak dianggap coverage 100%; area inconclusive wajib manual review.
3. Fingerprint teknologi = INFERRED dengan confidence, bukan bukti arsitektur source.
4. Hasil decompiler (JADX/Apktool/Ghidra) = evidence, bukan source asli; bedakan dengan tegas.
