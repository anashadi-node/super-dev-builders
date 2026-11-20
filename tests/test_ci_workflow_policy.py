"""Kontrak CI sebagai tes: gerbang keamanan tidak boleh hijau palsu.

Setiap tes di sini membaca `.github/workflows/ci.yml` yang SUNGGUHAN dipakai GitHub,
lalu untuk gerbang rahasia ia MENJALANKAN blok `run:` hasil ekstraksi — bukan salinan
logika. Tujuannya menangkap empat cara gerbang bisa mati diam-diam:

1. scanner tidak terpasang -> dulu `make secrets` `exit 0` (hijau palsu);
2. versi scanner bergeser tanpa pin;
3. langkah dihapus/dilunakkan (`|| true`, `exit 0`);
4. nama job/status check berubah sehingga branch protection tidak lagi mengikat.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import string
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
CODEOWNERS = REPO / ".github" / "CODEOWNERS"
PIN_GITLEAKS = "8.28.0"


def _wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _job() -> dict:
    return _wf()["jobs"]["check"]


def _steps() -> list[dict]:
    return _job()["steps"]


def _step(needle: str) -> dict:
    for step in _steps():
        if needle.lower() in str(step.get("name", "")).lower():
            return step
    raise AssertionError(f"langkah yang memuat {needle!r} tidak ada di ci.yml")


def _run_block(needle: str) -> str:
    block = _step(needle).get("run")
    assert isinstance(block, str) and block.strip(), f"langkah {needle!r} tanpa blok run"
    return block


def _run(block: str, *, path: str | None = None, cwd: Path | None = None,
         extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": path if path is not None else os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
    }
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", "-c", block], cwd=str(cwd or REPO), env=env,
        capture_output=True, text=True, timeout=300,
    )


# --- 1. struktur yang mengikat branch protection --------------------------

def test_nama_job_dan_status_check_tidak_berubah() -> None:
    """`check (lint + registry + test + drift)` adalah required status check.

    Mengganti nama job = gerbang di branch protection berhenti mengikat PR, tanpa
    ada yang error. Karena itu nama ini dikunci di tes.
    """
    wf = _wf()
    assert list(wf["jobs"]) == ["check"]
    assert wf["jobs"]["check"]["name"] == "check (lint + registry + test + drift)"


def test_boundary_runner_dan_tidak_ada_trigger_berprivilege() -> None:
    wf = _wf()
    # `on` bisa terbaca True oleh YAML 1.1, jadi diterima dua bentuk.
    on = wf.get("on", wf.get(True))
    assert isinstance(on, dict)
    assert set(on) <= {"push", "pull_request", "workflow_dispatch"}
    assert "pull_request_target" not in on
    assert "workflow_run" not in on
    assert _job()["runs-on"] == "ubuntu-latest"


def test_permission_token_minimal() -> None:
    wf = _wf()
    assert wf["permissions"] == {"contents": "read"}
    # permission tingkat job tidak boleh menaikkan hak secara diam-diam
    assert "permissions" not in _job()


def test_semua_action_dipin_sha() -> None:
    for step in _steps():
        uses = step.get("uses")
        if not uses:
            continue
        acting, _, ref = str(uses).partition("@")
        assert re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", acting), uses
        assert re.fullmatch(r"[0-9a-f]{40}", ref), f"belum dipin ke commit SHA: {uses}"


def test_langkah_lama_tidak_dihapus() -> None:
    """Hardening menambah, bukan mengganti. Gate lama harus tetap ada."""
    wajib = [
        "checkout", "setup python", "dependensi uji", "tesseract", "lint (ruff",
        "lint registry", "test suite", "drift skill", "docs lint",
        "cakupan inti", "benchmark did", "higiene", "manifest paket",
    ]
    nama = [str(s.get("name", "")).lower() for s in _steps()]
    for needle in wajib:
        assert any(needle in n for n in nama), f"langkah wajib hilang: {needle}"


# --- 2. gerbang rahasia benar-benar fail-closed ---------------------------

def test_gerbang_rahasia_tidak_memakai_make_secrets() -> None:
    """`make secrets` exit 0 saat gitleaks absen; memakainya di CI = hijau palsu."""
    blok = _run_block("Pindai rahasia")
    assert "make secrets" not in blok
    for pola in (r"\|\|\s*true", r"exit\s+0\s*$", r"set\s+\+e"):
        assert not re.search(pola, blok, re.MULTILINE), f"pelemahan gerbang: {pola}"


def test_gerbang_rahasia_gagal_bila_scanner_tidak_ada() -> None:
    blok = _run_block("Pindai rahasia")
    hasil = _run(blok, path="/usr/bin:/bin")  # gitleaks ada di ~/.local/bin
    assert shutil.which("gitleaks", path="/usr/bin:/bin") is None, "prasyarat tes tidak sah"
    assert hasil.returncode != 0, "gerbang HIJAU padahal scanner tidak tersedia"
    assert "FAIL" in (hasil.stdout + hasil.stderr)


def test_gerbang_rahasia_menolak_versi_berbeda() -> None:
    blok = _run_block("Pindai rahasia")
    with tempfile.TemporaryDirectory() as tmp:
        shim = Path(tmp) / "gitleaks"
        shim.write_text("#!/bin/sh\necho 8.27.0\n", encoding="utf-8")
        shim.chmod(0o755)
        hasil = _run(blok, path=f"{tmp}:/usr/bin:/bin")
    assert hasil.returncode != 0, "gerbang menerima versi scanner di luar pin"
    assert "FAIL" in (hasil.stdout + hasil.stderr)


def test_versi_pin_di_workflow_sama_dengan_pin_tes() -> None:
    assert _step("Pasang gitleaks").get("env", {}).get("GITLEAKS_VERSION") == PIN_GITLEAKS


def test_checksum_scanner_tertanam_bukan_diunduh() -> None:
    """Checksum dari origin yang sama = tidak melindungi dari origin yang disusupi."""
    step = _step("Pasang gitleaks")
    sha = step.get("env", {}).get("GITLEAKS_SHA256", "")
    assert re.fullmatch(r"[0-9a-f]{64}", sha), sha
    blok = str(step["run"])
    assert "checksums.txt" not in blok, "checksum diunduh dari jaringan, bukan tertanam"
    assert "sha256sum -c -" in blok


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks tidak terpasang lokal")
def test_gerbang_rahasia_lulus_dengan_scanner_asli() -> None:
    """Eksekusi nyata: allowlist `.gitleaks.toml` harus tetap 0 temuan di HEAD."""
    blok = _run_block("Pindai rahasia")
    try:
        hasil = _run(blok)
        assert hasil.returncode == 0, hasil.stdout + hasil.stderr
        laporan = REPO / "reports" / "ci" / "gitleaks.json"
        assert laporan.is_file(), "laporan rahasia tidak dibuat"
        assert json.loads(laporan.read_text(encoding="utf-8")) == []
    finally:
        bersihkan = REPO / "reports" / "ci"
        for sisa in (bersihkan / "gitleaks.json", bersihkan / "meta.json"):
            sisa.unlink(missing_ok=True)
        if bersihkan.is_dir() and not any(bersihkan.iterdir()):
            bersihkan.rmdir()


# --- 3. baseline rahasia teraudit (ratchet) ------------------------------

BASELINE = REPO / ".github" / "gitleaks-baseline.json"
# Satu-satunya commit yang boleh muncul di baseline. Menambah entri baru ke baseline
# adalah cara paling halus untuk mematikan gerbang, jadi daftar ini dikunci.
BASELINE_COMMITS = {
    "223dc4c4d18f49d94ad686c40bfb28afd17bc933",  # digest SHA-256 di manifest hash
    "72eec21bcf39edc42a7155b9ed97e88114c55d71",  # profil Chromium (kunci publik + MAC)
}


def test_baseline_hanya_berisi_temuan_teraudit() -> None:
    assert BASELINE.is_file(), "baseline rahasia hilang; gerbang akan gagal di riwayat lama"
    entri = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert isinstance(entri, list) and 1 <= len(entri) <= 10, len(entri)
    for e in entri:
        assert e["Secret"] == "REDACTED", "baseline memuat nilai rahasia"
        assert e["RuleID"] == "generic-api-key", e["RuleID"]
        assert e["Commit"] in BASELINE_COMMITS, f"commit tak teraudit masuk baseline: {e['Commit']}"
        assert e["Fingerprint"].startswith(f"{e['Commit']}:{e['File']}:{e['RuleID']}:"), e["Fingerprint"]
    assert _run_block("Pindai rahasia").count("--baseline-path .github/gitleaks-baseline.json") == 1


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks tidak terpasang lokal")
def test_ratchet_menolak_kebocoran_baru(tmp_path: Path) -> None:
    """Baseline tidak boleh mematikan gerbang: kebocoran baru wajib FAIL.

    Klon `--shared` memakai objek git yang sama (cepat, hemat disk) sehingga riwayat
    asli tetap terpindai; canary sintetis ditambahkan sebagai commit baru di klon.
    """
    klon = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", "--shared", str(REPO), str(klon)], check=True)
    # Baseline dibaca dari working tree; di sesi ini ia belum di-commit, jadi disalin
    # dari working tree asli supaya klon mencerminkan keadaan CI yang sebenarnya.
    shutil.copy2(BASELINE, klon / ".github" / "gitleaks-baseline.json")
    # Token canary DIBANGKITKAN saat runtime: menanam token berbentuk PAT di source
    # akan ditangkap gitleaks sebagai kebocoran nyata (dan memang seharusnya begitu).
    acak = random.Random(20261120)
    alfabet = string.ascii_letters + string.digits
    token = "ghp_" + "".join(acak.choice(alfabet) for _ in range(36))
    canary = klon / "canary_kebocoran.txt"
    canary.write_text(f"token = {token}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(klon), "add", "canary_kebocoran.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(klon), "-c", "commit.gpgsign=false", "-c",
         "user.name=canary", "-c", "user.email=canary@invalid",
         "commit", "-q", "-m", "canary kebocoran sintetis"],
        check=True,
    )
    hasil = _run(_run_block("Pindai rahasia"), cwd=klon)
    assert hasil.returncode != 0, "ratchet GAGAL: kebocoran baru lolos karena baseline"
    laporan = klon / "reports" / "ci" / "gitleaks.json"
    assert laporan.is_file(), "gerbang tidak menulis laporan di klon"
    bocor = [t["File"] for t in json.loads(laporan.read_text(encoding="utf-8"))]
    assert bocor == ["canary_kebocoran.txt"], f"isi laporan tak terduga: {bocor}"


# --- 4. artefak bukti per commit -----------------------------------------

def test_artefak_uji_terikat_commit_sha() -> None:
    step = _step("Simpan artefak")
    uses = str(step["uses"])
    assert re.fullmatch(r"actions/upload-artifact@[0-9a-f]{40}", uses)
    assert step["if"] == "always()"
    assert "${{ github.sha }}" in str(step["with"]["name"])
    assert 1 <= int(step["with"]["retention-days"]) <= 30
    isi = str(step["with"]["path"])
    for berkas in ("junit.xml", "gitleaks.json", "meta.json"):
        assert berkas in isi
    assert step["with"]["if-no-files-found"] in {"warn", "error"}


def test_junit_dari_satu_kali_eksekusi_suite() -> None:
    step = _step("Test suite")
    assert "make test" in str(step["run"])
    assert "reports/ci/junit.xml" in str(step.get("env", {}).get("PYTEST_ADDOPTS", ""))
    # tidak boleh ada langkah yang menjalankan suite kedua hanya untuk JUnit
    ulang = [s for s in _steps() if "--junitxml" in str(s.get("run", ""))]
    assert ulang == [], "ada eksekusi suite tambahan"


def test_metadata_eksekusi_tanpa_rahasia() -> None:
    blok = _run_block("Metadata eksekusi")
    for terlarang in ("SECRET", "TOKEN", "PASSWORD", "PRIVATE_KEY", "CREDENTIAL"):
        assert terlarang not in blok.upper(), f"metadata menyentuh {terlarang}"
    assert '"evidence_level": "CI_ATTESTED"' in blok
    assert '"independent_review": False' in blok

    with tempfile.TemporaryDirectory() as tmp:
        hasil = _run(blok, cwd=Path(tmp), extra_env={"HOME": tmp})
        assert hasil.returncode == 0, hasil.stdout + hasil.stderr
        meta = json.loads((Path(tmp) / "reports" / "ci" / "meta.json").read_text())
    assert meta["schema"] == "sdb-ci-evidence/1"
    assert meta["evidence_level"] == "CI_ATTESTED"
    assert meta["independent_review"] is False
    assert meta["sdb_done_policy"] == "attested"
    assert meta["sdb_evidence_mode"] == "legacy"
    # versi python milik runner (bukan milik mesin yang menjalankan tes ini)
    assert re.fullmatch(r"\d+\.\d+\.\d+", meta["python"]), meta["python"]


# --- 5. CODEOWNERS --------------------------------------------------------

def test_codeowners_valid_dan_mencakup_jalur_kritis() -> None:
    assert CODEOWNERS.is_file()
    baris = [
        ln.strip() for ln in CODEOWNERS.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    assert baris, "CODEOWNERS kosong"
    for ln in baris:
        pola, _, pemilik = ln.partition(" ")
        assert pola.startswith("/") or pola.startswith("*"), pola
        assert re.fullmatch(r"@[A-Za-z0-9][A-Za-z0-9-]*", pemilik.strip()), pemilik

    teks = " ".join(baris)
    for jalur in ("/.github/", "/.github/CODEOWNERS", "/.gitleaks.toml",
                  "sdb_build_worker.py", "sdb_evidence.py", "/registry/",
                  "stages.yaml", "test_ci_workflow_policy.py"):
        assert jalur in teks, f"jalur kritis tidak dilindungi: {jalur}"
    # pola global "*" hanya boleh ada bila ada reviewer kedua (belum ada di repo ini)
    assert not any(ln.startswith("* ") for ln in baris), (
        "pola global '*' membuat PR pemilik tunggal tidak bisa disetujui"
    )
