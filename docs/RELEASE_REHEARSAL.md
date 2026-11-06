# Rehearsal gerbang rilis

> 2026-11-06 — run pertama yang benar-benar mengeksekusi rantai rilis SDB.

## Kenapa ada

`scripts/release_check.py` menuntut tujuh artefak segar + `reports/security-verdict.json`
bernilai `PASS`. Sebelum hari ini belum pernah ada run rilis di repo, jadi gerbang itu
hanya diuji lewat unit test di `tmp_path` — cukup untuk membuktikan logikanya, tidak
cukup untuk membuktikan rantainya.

`scripts/release_rehearsal.py` menutup celah itu: satu perintah menjalankan build,
test, scanner keamanan, higiene, dan audit ke sebuah run dir, lalu memanggil gerbangnya.

```
make release-rehearsal
```

## Rantai yang dijalankan

| Langkah | Alat | Artefak |
|---|---|---|
| 1 | tulis requirement | `requirements.md` |
| 2 | `compileall` + `build_fixtures.py --verify` | `logs/build-*.log`, `logs/build-fixtures-*.log` |
| 3 | `pytest tests/test_release_gate.py tests/test_did_contract.py` | `logs/tests-*.log` |
| 4 | `security_verdict.py` → `tools/scan-keamanan.sh` (semgrep, syft, trivy, ruff, privasi-media) | `reports/security-gate.md`, `reports/security-verdict.json` |
| 5 | `repo_hygiene.py` + `workflow_run.py` | `reports/assurance-audit.md`, `logs/hygiene-*.log` |
| 6 | `release_check.py` | verdict PASS/FAIL + exit code |

Setelah gerbang PASS, skrip menjalankan **uji negatif**: salinan run yang sama dengan
`logs/tests-*.log` dihapus harus **ditolak** (exit 1). Tanpa uji negatif, "gerbang
PASS" hanya membuktikan satu arah.

## Temuan nyata dari run pertama

Gerbang **menolak** run pertama. Itu bukan kegagalan rehearsal — itu gunanya:

1. **`scripts/sdb_jobs.py:120` — SQL dinamis.** Semgrep severity ERROR: nama kolom
   masuk ke string SQL. Diperbaiki dengan pernyataan SQL utuh per kolom
   (`_SET_FIELD_SQL`), tanpa interpolasi. Temuan hilang.
2. **3 temuan ruff keamanan di kode baru** (`F401` impor tak terpakai, dua `F541`
   f-string tanpa placeholder). Diperbaiki.
3. **47 temuan ruff-inti BARU** pada 27 pasangan (kode, berkas): `S603`/`S607`
   subprocess, `S310` urlopen, `S101` assert, `S103` chmod, `S608` SQL. Semuanya
   diperiksa satu per satu; yang aman (argv list, tanpa shell, host tetap, jalur
   absolut) ditriase ke `tools/sast-diterima.json` dengan sebab + pemilik D8 +
   kedaluwarsa 2027-01-31. Yang tidak aman (SQL) diperbaiki, bukan ditriase.

## Hasil akhir

```
GERBANG: PASS (exit 0) · run: runs/release-rehearsal
UJI NEGATIF: menolak dengan benar (exit 1)
security verdict: PASS
```

## Batas jujur

- Target rehearsal adalah **repo SDB sendiri**, bukan produk pelanggan.
- `reports/review-*.md` dibuat mesin (commit, diff, lint). Rilis sungguhan tetap
  butuh peninjau manusia yang berbeda dari pelaksana.
- `runs/` gitignored: artefak run tidak ikut git. Yang bisa diperiksa ulang adalah
  skrip + hasil di dokumen ini.
- Scanner lokal ada di mesin ini (semgrep, syft, trivy). Di CI GitHub-hosted alat itu
  tidak tersedia, sehingga rehearsal **tidak** dijalankan per-PR; `did-suite` tetap.
