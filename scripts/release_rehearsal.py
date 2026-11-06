#!/usr/bin/python3
"""Rehearsal rilis — buat run rilis SUNGGUHAN dari alat yang ada, lalu uji gerbangnya.

MASALAH YANG DISELESAIKAN
-------------------------
`release_check.py` menuntut tujuh artefak segar + satu verdict mesin, tetapi repo ini
tidak punya satu pun run rilis: `runs/` gitignored dan tak pernah diisi artefak rilis.
Akibatnya gerbang rilis hanya "terbukti" lewat argumen, bukan lewat eksekusi.

Script ini menjalankan rantai nyata (build, test, security, audit, docs) ke sebuah
direktori run, lalu memanggil gerbangnya. Yang dihasilkan adalah keluaran alat —
bukan tulisan tangan — sehingga PASS tidak bisa dikarang.

BATAS JUJUR
-----------
- Ini **rehearsal**, bukan rilis produk pelanggan: targetnya repo SDB sendiri.
- `reports/review-*.md` dihasilkan mesin (diff + lint + log commit). Review manusia
  tetap wajib untuk rilis sebenarnya; berkas itu menyatakannya secara eksplisit.
- Bila scanner keamanan tidak tersedia, verdict = BLOCKED dan gerbang GAGAL —
  "tidak diperiksa" tidak pernah menjadi "bersih".

Pemakaian:
    python3 scripts/release_rehearsal.py                 # runs/release-rehearsal
    python3 scripts/release_rehearsal.py --slug rilis-demo
Exit: 0 = gerbang PASS (+ uji negatif berhasil menolak), 1 = gerbang gagal.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import release_check  # noqa: E402


def _cap(cmd: list[str], log_path: str, cwd: str = ROOT) -> int:
    """Jalankan perintah, simpan keluaran APA ADANYA + kode keluar di kepala log."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    proses = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(f"$ {' '.join(cmd)}\n# exit={proses.returncode}  waktu={datetime.now().astimezone().isoformat(timespec='seconds')}\n")
        fh.write(proses.stdout)
        if proses.stderr:
            fh.write("\n--- stderr ---\n" + proses.stderr)
    return proses.returncode


def _tulis(path: str, isi: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(isi)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Rehearsal gerbang rilis (artefak nyata)")
    ap.add_argument("--slug", default="release-rehearsal")
    ap.add_argument("--run-dir", default=None)
    args = ap.parse_args(argv)

    run_dir = args.run_dir or os.path.join(ROOT, "runs", args.slug)
    if os.path.isdir(run_dir):
        shutil.rmtree(run_dir)  # artefak lama akan menipu gerbang "fresh"
    for sub in ("logs", "reports", "docs"):
        os.makedirs(os.path.join(run_dir, sub), exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    print("[1/6] requirement ...")
    _tulis(os.path.join(run_dir, "requirements.md"), f"""# Requirement — rehearsal rilis {ts}

Tujuan: membuktikan jalur rilis SDB bisa lulus gerbang memakai bukti yang dihasilkan
alat, bukan tulisan tangan.

## Kriteria penerimaan
1. Semua skrip Python terkompilasi (`compileall`).
2. Fixture DID dapat dibangun ulang dengan hash identik (`build_fixtures.py --verify`).
3. Uji unit gerbang rilis dan kontrak DID lulus (`pytest`).
4. Verdict keamanan keluar dari eksekusi scanner nyata.
5. Audit mutu repo dijalankan dan hasilnya dilampirkan.
6. Gerbang rilis menerima run ini (PASS) — dan menolak bila satu artefak hilang.
""")

    print("[2/6] build ...")
    rc_build = _cap([sys.executable, "-m", "compileall", "-q", "scripts"],
                    os.path.join(run_dir, f"logs/build-{ts}.log"))
    rc_fix = _cap([sys.executable, "scripts/build_fixtures.py", "--verify"],
                  os.path.join(run_dir, f"logs/build-fixtures-{ts}.log"))

    print("[3/6] tests ...")
    rc_test = _cap([sys.executable, "-m", "pytest", "-q", "tests/test_release_gate.py",
                    "tests/test_did_contract.py"],
                   os.path.join(run_dir, f"logs/tests-{ts}.log"))

    print("[4/6] security (scanner nyata; bisa beberapa menit) ...")
    rc_sec = _cap([sys.executable, "scripts/security_verdict.py", "--run-dir", run_dir,
                   "--project", ROOT],
                  os.path.join(run_dir, f"logs/security-{ts}.log"))
    verdict_path = os.path.join(run_dir, "reports", "security-verdict.json")
    verdict = {}
    if os.path.isfile(verdict_path):
        verdict = json.load(open(verdict_path, encoding="utf-8"))
    _tulis(os.path.join(run_dir, "reports", "security-gate.md"), f"""# Security gate (tahap 10b) — rehearsal {ts}

Verdict mesin: **{verdict.get('verdict', 'TIDAK ADA')}** (`reports/security-verdict.json`)

| kanal | hasil |
|---|---|
""" + "\n".join(f"| {c.get('name')} | {c.get('status')} (exit {c.get('exit_code')}) |"
                for c in (verdict.get("checks") or [])) +
"""

Sumber: `scripts/security_verdict.py` (semgrep + syft + trivy + ruff + scan rahasia +
privasi media). Tidak ada jalur PASS manual: kanal yang tidak bisa dijalankan
menghasilkan BLOCKED, bukan lewat.
""")

    print("[5/6] audit + review + docs ...")
    rc_hyg = _cap([sys.executable, "scripts/repo_hygiene.py"], os.path.join(run_dir, f"logs/hygiene-{ts}.log"))
    _cap([sys.executable, "scripts/workflow_run.py", os.path.basename(run_dir)],
         os.path.join(run_dir, f"logs/workflow-{ts}.log"))
    hygiene = open(os.path.join(run_dir, f"logs/hygiene-{ts}.log"), encoding="utf-8").read()
    _tulis(os.path.join(run_dir, "reports", "assurance-audit.md"), f"""# Assurance audit — rehearsal {ts}

Dihasilkan `repo_hygiene.py` + `workflow_run.py` (keluaran mentah di `logs/`).

## Higiene repo
```
{hygiene.strip()[-1500:]}
```

## Batas
Audit ini memeriksa bentuk artefak (ukuran, PII, berkas wajib), **bukan** kebenaran
logika produk. Uji fungsional ada di `logs/tests-*.log`.
""")
    git = shutil.which("git") or "/usr/bin/git"
    git_info = subprocess.run([git, "log", "-1", "--format=%h %s"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    diff_stat = subprocess.run([git, "diff", "--stat"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    _tulis(os.path.join(run_dir, f"reports/review-{ts}.md"), f"""# Review — rehearsal {ts}

> **Review mesin.** Otomatis dari commit, diff, dan lint. Bukan pengganti review
> manusia: rilis sebenarnya wajib ditinjau orang yang berbeda dari pelaksana.

- Commit: `{git_info or 'tanpa commit'}`
- Build exit: {rc_build} (compileall), {rc_fix} (fixture verify)
- Tests exit: {rc_test}
- Security exit: {rc_sec} → verdict {verdict.get('verdict', 'TIDAK ADA')}
- Higiene exit: {rc_hyg}

## Perubahan belum di-commit
```
{diff_stat or '(bersih)'}
```
""")
    _tulis(os.path.join(run_dir, "docs", "README-rilis.md"), f"""# README rilis — rehearsal {ts}

Cara menjalankan ulang:

```
python3 scripts/release_rehearsal.py --slug {args.slug}
python3 scripts/release_check.py --project runs/{args.slug}
```

Run ini mewakili REPLIKA jalur rilis pada repo SDB sendiri. Artefak dibuat oleh
alat: `compileall`, `build_fixtures.py --verify`, `pytest`, `security_verdict.py`,
`repo_hygiene.py`, `workflow_run.py`.
""")

    print("[6/6] gerbang rilis ...")
    rc_gate = release_check.main(["--project", run_dir])
    print(f"\nGERBANG: {'PASS' if rc_gate == 0 else 'FAIL'} (exit {rc_gate}) · run: {os.path.relpath(run_dir, ROOT)}")

    # Uji negatif: gerbang harus MENOLAK run yang sama bila satu artefak hilang.
    with tempfile.TemporaryDirectory() as tmp:
        salinan = os.path.join(tmp, "tanpa-tests")
        shutil.copytree(run_dir, salinan)
        for nama in os.listdir(os.path.join(salinan, "logs")):
            if nama.startswith("tests-"):
                os.remove(os.path.join(salinan, "logs", nama))
        rc_neg = release_check.main(["--project", salinan])
    print(f"UJI NEGATIF: {'menolak dengan benar' if rc_neg == 1 else 'GAGAL — gerbang meloloskan artefak hilang'}"
          f" (exit {rc_neg})")
    return 0 if rc_gate == 0 and rc_neg == 1 else 1


if __name__ == "__main__":
    sys.exit(main())
