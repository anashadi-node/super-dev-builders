# Security Gate Report — <target/rilis>

- Tanggal:
- Scope yang dipindai:
- Mode: Gate #0 / pra-deploy / audit rilis

## 1. Gate #0 (otorisasi & scope)
- authorization.yaml: PASS/FAIL/BLOCKED
- forbidden actions dipatuhi: ya/tidak (buktinya)

## 2. Scan deterministik
| Tool | Versi | Scope | Hasil | Artefak |
|---|---|---|---|---|
| semgrep |  |  |  |  |
| codeql |  |  |  |  |
| trivy (fs/image/secret/misconfig) |  |  |  |  |
| dependency audit |  |  |  |  |

## 3. Temuan
| ID | Severity | Exploitability | Confidence | Bukti/provenance | Status |
|---|---|---|---|---|---|

## 4. Triage & keputusan
- Critical/high tertutup: <n>/<n>
- Diterima eksplisit manusia (siapa, alasan):
- Blocker rilis:

## 5. Batasan review
- LLM review bukan satu-satunya gate:
- Area yang tidak tercakup tooling:
