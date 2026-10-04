# CodeQL + Syft — bukti uji nyata (2026-10-04)

## Instalasi (pin + verifikasi checksum)
| Tool | Versi | Sumber | Verifikasi | Jalur |
|---|---|---|---|---|
| CodeQL CLI | 2.27.1 | `github/codeql-cli-binaries` rilis resmi | `codeql-linux64.zip.checksum.txt` → `sha256sum -c` = **OK** | `~/.local/bin/codeql` → `~/.local/share/codeql-v2.27.1/` |
| Syft | 1.54.0 | `anchore/syft` rilis resmi | `syft_1.54.0_checksums.txt` → sha256 = **OK** | `~/.local/bin/syft` |

Instalasi lewat `scripts/bootstrap_tools.sh --install syft codeql --yes` (tanpa `curl | sh`, tanpa sudo).

## Uji fungsi
| Uji | Perintah | Hasil |
|---|---|---|
| Versi | `codeql version`, `syft version` | 2.27.1 / 1.54.0 |
| Bahasa | `codeql resolve languages` | python, cpp, csharp, yaml, actions, html, csv, xml → **Java tidak diperlukan** untuk analisis Python |
| SBOM repo internal | `syft dir:. -o spdx-json` | "No packages discovered" — repo tanpa manifest dependensi; **bukan** bukti bersih |
| SBOM target ber-manifest | `syft dir:/tmp/oss-click -o spdx-json` | **102 paket** terdeteksi (mis. `actions/checkout v7.0.1`) → tool terbukti bekerja |
| CodeQL DB | `codeql database create --language=python` | sukses (peringatan `dynload path` tidak fatal) |
| CodeQL query pack | `codeql pack download codeql/python-queries` | terpasang `codeql/python-queries@1.8.11` di `~/.codeql/packages` |
| CodeQL analisis | `codeql database analyze /tmp/db-click codeql/python-queries:codeql-suites/python-security-and-quality.qls --format=sarif-latest -j 4` | **174 query dievaluasi**, mencakup **91/91 berkas Python + 6/6 berkas GitHub Actions**; SARIF: **139 temuan** |

### Sebaran temuan CodeQL (nyata, 139)
| Rule | n | Kelas |
|---|---|---|
| `ineffectual-statement` | 44 | maintainability |
| `cyclic-import` | 31 | struktur |
| `mixed-returns` | 14 | maintainability |
| `unused-global-variable` | 11 | maintainability |
| `empty-except` | 10 | **error handling** |
| `file-not-closed` | 5 | resource leak |
| `import-and-import-from` | 5 | maintainability |
| `unreachable-statement` | 4 | logika |
| `unnecessary-lambda` | 4 | maintainability |
| `unused-local-variable` | 3 | maintainability |
| **`clear-text-logging-sensitive-data`** | **1** | **security (potensi bocor data sensitif ke log)** |
| **`overly-permissive-file`** | **1** | **security (permission berkas terlalu longgar)** |

Catatan: temuan keamanan (`clear-text-logging-sensitive-data`, `overly-permissive-file`) adalah contoh kelas temuan yang
**tidak ditangkap** lint cepat — inilah nilai tambah CodeQL saat dipakai pada codebase yang lisensinya mengizinkan.

Artefak: `codeql-oss-click.sarif`, `sbom-oss-click-spdx.json`, `sbom-spdx.json`, `sbom-cyclonedx.json`.

## ⚠️ Batas lisensi CodeQL (WAJIB dipatuhi)
Dari README resmi rilis CodeQL CLI:

> "GitHub CodeQL can only be used on codebases that are released under an OSI-approved open source license,
> or to perform academic research. It can't be used to generate CodeQL databases for or during automated
> analysis, continuous integration or continuous delivery, whether as part of normal software engineering
> processes or otherwise."

**Konsekuensi operasional di ekosistem ini:**
1. CodeQL **boleh** dipakai untuk target rekonstruksi yang berlisensi OSI-approved, atau riset akademik.
2. CodeQL **TIDAK boleh** dipakai untuk kode internal/proprietary ekosistem, dan **tidak boleh** dipasang di CI/CD.
3. Untuk kode internal: pakai `semgrep` + `ruff` + `trivy` (+ `syft` untuk SBOM) — semuanya bebas dipakai internal.
4. Pelanggaran = risiko legal, bukan sekadar teknis → kepatuhan ini bagian dari gate keamanan.
