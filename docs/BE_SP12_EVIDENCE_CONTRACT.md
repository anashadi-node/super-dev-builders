# BE-SP-12 Capability Evidence Contract

**Status:** C1-01 implemented — `sdb.capability.evidence/1`
**Capability:** BE-SP-12 — Backend QA / Test Engineer
**Registry:** `registry/capability_pilot.yaml`
**Runtime evidence:** `runs/capability/` (**gitignored; tidak di-commit**)
**Validator/CLI:** `scripts/sdb_capability_evidence.py`

Dokumen ini adalah kontrak evidence untuk vertical slice BE-SP-12. Ia tidak
memberi persetujuan merge, acceptance independen, atau otorisasi rilis.

## 1. Batas wewenang

Empat status berikut terpisah dan **tidak naik otomatis**:

1. **Execution evidence** — hasil perintah tes yang dilaporkan builder.
2. **Acceptance** — keputusan reviewer berwenang; bukan hasil otomatis exit code.
3. **Independent verification** — pengesahan pihak yang bukan produsen evidence.
4. **Release authorization** — keputusan Owner/release authority di luar modul ini.

Builder hanya dapat menghasilkan:

- `evidence_level: AGENT_REPORTED`
- `review_status: NOT_REVIEWED`
- `release_authorization: NOT_AUTHORIZED`
- `acceptance_status: INFORMATIONAL_ONLY` bila eksekusi PASS

Klaim `CI_ATTESTED`, `INDEPENDENT_REVIEW`, `REVIEWED_INDEPENDENT`, `APPROVED`,
atau otorisasi rilis melalui JSON ditolak sebagai self-attestation.

## 2. Registry pilot

`registry/capability_pilot.yaml` bukan katalog baru dan tidak menggantikan katalog
26 capability. Registry tersebut hanya berisi capability yang telah diberi izin
pilot. ID tidak boleh diduplikasi, diubah, atau dipindahkan dari katalog sumber.

Syarat entri:

- `id` berpola `XX-YY-NN` dan unik;
- `status` hanya `PILOT` atau `ACTIVE`;
- BE-SP-12 harus terdaftar sebelum evidence diterima.

## 3. Skema v1

Berkas skema: `registry/capability_evidence.schema.json`
Identifier: `sdb.capability.evidence/1`
JSON Schema: draft 2020-12

Field wajib:

| Field | Aturan |
|---|---|
| `schema` | tepat `sdb.capability.evidence/1` |
| `capability_id` | pola valid dan dikenal registry pilot |
| `revision` | SHA Git penuh 40 hex, sama dengan `git rev-parse HEAD` |
| `test_command` | teks 1–512 karakter; dicatat, **tidak dijalankan validator** |
| `exit_code` | integer 0–255; boolean ditolak |
| `test_results` | hitungan nonnegatif dan konsisten |
| `artifact_refs` | daftar path relatif + sha256, maksimum 16 |
| `evidence_level` | hanya `AGENT_REPORTED` |
| `verification_timestamp` | UTC `YYYY-MM-DDTHH:MM:SSZ`, bukan masa depan |
| `review_status` | hanya `NOT_REVIEWED` |
| `release_authorization` | hanya `NOT_AUTHORIZED` |
| `integrity` | opsional pada input; wajib pada hasil `record` |

Field tambahan ditolak. Parser juga menolak key JSON ganda, `NaN`, `Infinity`,
dan `-Infinity`.

## 4. Aturan hasil tes

`test_results` wajib mempunyai tepat lima kunci:

```json
{
  "passed": 12,
  "failed": 0,
  "skipped": 1,
  "errors": 0,
  "total": 13
}
```

Invarian:

- `total == passed + failed + skipped + errors`;
- `total > 0`;
- setidaknya satu tes benar-benar dieksekusi (`passed + failed + errors > 0`);
- `exit_code != 0` tidak pernah menghasilkan `execution_status: PASS`;
- `failed > 0` atau `errors > 0` tidak pernah menghasilkan PASS;
- eksekusi PASS tetap hanya `INFORMATIONAL_ONLY` pada level builder.

## 5. Binding revisi dan artefak

### 5.1 Revisi

`record` membandingkan `revision` dengan `git rev-parse HEAD`. SHA pendek dan
revision lain ditolak. Ini mencegah evidence dari kode lama dipasang ke HEAD baru.

### 5.2 Artefak

Setiap entri artefak harus mempunyai tepat:

```json
{"path": "artifacts/junit.xml", "sha256": "<64 hex>"}
```

Validator menolak:

- path absolut, kosong, `.` atau komponen `..`;
- backslash dan NUL;
- file/direktori/root symlink;
- path yang keluar dari root repository;
- file hilang, bukan regular file, terlalu besar, atau duplikat;
- SHA-256 tidak valid atau tidak sama dengan isi nyata.

Batas: 16 artefak, masing-masing maksimum 8 MiB.

## 6. Integritas dan penulisan

`record` menghitung `integrity` sebagai SHA-256 atas JSON kanonik seluruh field
selain `integrity`. `validate` menghitung ulang nilai tersebut dan menolak evidence
yang berubah.

Penulisan memakai sibling temporary file yang di-`fsync`. Mode immutable membuat
path final melalui hard link eksklusif sehingga race dengan penulis lain gagal tanpa
overwrite; `--replace` eksplisit memakai `os.replace`. Temporary file dibersihkan
bila gagal. Root output dan input `validate` dikunci ke `runs/capability/`; symlink
pada rantai root atau path evidence ditolak.

Lokasi default:

```text
runs/capability/<capability_id>/<revision-40hex>.json
```

Evidence runtime tidak boleh di-stage atau di-commit.

## 7. CLI

Mencatat evidence (validator tidak menjalankan command berikut):

```bash
.venv/bin/python scripts/sdb_capability_evidence.py record \
  --capability BE-SP-12 \
  --revision HEAD \
  --command ".venv/bin/python -m pytest tests/test_capability_evidence.py -q" \
  --exit-code 0 --passed 53 --failed 0 --skipped 0 --errors 0 --total 53
```

Validasi evidence:

```bash
.venv/bin/python scripts/sdb_capability_evidence.py validate \
  runs/capability/BE-SP-12/<revision>.json
```

Exit CLI:

- `0`: valid dan execution PASS;
- `2`: valid tetapi execution FAIL, atau evidence ditolak.

Output selalu JSON. Error memuat `result: REJECTED`, kode mesin, alasan, dan
`release_authorization: NOT_AUTHORIZED`.

## 8. Acceptance T1–T10

| ID | Kontrol wajib |
|---|---|
| T1 | Evidence sah diterima; tulis atomik; immutable default |
| T2 | Capability tidak dikenal/tidak sah ditolak |
| T3 | Revision dan hash mismatch ditolak |
| T4 | JSON rusak, key ganda, schema invalid, NaN/Infinity ditolak |
| T5 | Exit code gagal tidak menghasilkan PASS |
| T6 | Nol tes dan semua-skip tidak menghasilkan acceptance |
| T7 | Traversal, absolute path, dan symlink ditolak |
| T8 | Self-attestation tidak menjadi independent verification |
| T9 | Mutasi terarah di salinan scratch membuktikan kontrol sensitif |
| T10 | 19 workflow stages dan 9 struktur agent tetap identik dengan HEAD |

Tes acuan: `tests/test_capability_evidence.py`.

## 9. Non-goals

Modul ini tidak:

- mengeksekusi `test_command` dari payload;
- membaca secrets, kredensial, atau `.env`;
- memakai jaringan;
- mengubah workflow, agent, CI, atau branch protection;
- memberikan independent acceptance;
- mengaktifkan `verified`;
- melakukan push, merge, deploy, atau release authorization.

Konfigurasi kebijakan tetap:

- `SDB_DONE_POLICY=attested`
- `SDB_EVIDENCE_MODE=legacy`
