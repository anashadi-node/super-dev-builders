"""C1-07 — penjaga exception rahasia historis (fingerprint-scoped).

Membuktikan brief STEP 4:

1. false positive historis dikecualikan satu per satu (per fingerprint), bukan per file;
2. secret sintetis baru dengan rule yang sama tetap terdeteksi;
3. temuan baru di file yang sama tetap terdeteksi (exception terikat commit + baris);
4. kegagalan scanner gagal-tertutup (fail-closed);
5. tidak ada allowlist luas.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
IGNORE_FILE = REPO / ".gitleaksignore"
BASELINE_FILE = REPO / ".github" / "gitleaks-baseline.json"
CONFIG_FILE = REPO / ".gitleaks.toml"
CI_FILE = REPO / ".github" / "workflows" / "ci.yml"
MAKEFILE = REPO / "Makefile"

GITLEAKS = shutil.which("gitleaks")
needs_gitleaks = pytest.mark.skipif(GITLEAKS is None, reason="binary gitleaks tidak tersedia")

FINGERPRINT_RE = re.compile(
    r"^(?P<commit>[0-9a-f]{40}):(?P<file>[^:]+):(?P<rule>[A-Za-z0-9_-]+):(?P<line>[1-9][0-9]*)$"
)

# Nilai sintetis dibuat saat runtime: berkas ini ikut dipindai riwayat repo, jadi literal
# ber-entropy tinggi di sini akan menjadi temuan `generic-api-key` palsu di repo sendiri.
SYNTHETIC_SECRET = base64.b64encode(
    hashlib.sha256(b"C1-07 negative test fixture").digest()
).decode()


def fingerprints() -> list[tuple[str, str, str, int]]:
    """Ambil exception dari `.gitleaksignore` (komentar & baris kosong dilewati)."""
    entries: list[tuple[str, str, str, int]] = []
    for raw in IGNORE_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = FINGERPRINT_RE.match(line)
        assert match, f"format fingerprint tidak sah: {line!r}"
        entries.append((match["commit"], match["file"], match["rule"], int(match["line"])))
    return entries


def git(*args: str, cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def scan(repo: Path, report: Path, config: Path | None = None) -> tuple[int, list[dict]]:
    exe = GITLEAKS
    assert exe is not None
    cmd = [exe, "detect", "--no-banner", "--redact", "--log-opts=--all"]
    if config is not None:
        cmd += ["--config", str(config)]
    cmd += ["--report-format", "json", "--report-path", str(report)]
    proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else []
    return proc.returncode, data


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git("init", "-q", cwd=path)
    git("config", "user.email", "c107@example.invalid", cwd=path)
    git("config", "user.name", "C1-07 Test", cwd=path)
    git("config", "commit.gpgsign", "false", cwd=path)
    return path


def commit(repo: Path, message: str) -> str:
    git("add", "-A", cwd=repo)
    git("commit", "-qm", message, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo).stdout.strip()


# --- 1. Exception harus per-fingerprint, bukan per-file / per-rule -----------------


def test_ignore_entries_are_fingerprint_scoped() -> None:
    entries = fingerprints()
    assert len(entries) == 2, f"harus tepat 2 fingerprint (10 temuan -> 2 baris), dapat {len(entries)}"
    assert len(set(entries)) == len(entries), "fingerprint duplikat"
    for line in IGNORE_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        assert "*" not in line, f"wildcard tidak diizinkan di exception: {line!r}"
        assert line.count(":generic-api-key:") == 1, "exception harus menyebut rule persis sekali"


def test_ignore_matches_ci_baseline_exactly() -> None:
    baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    baseline_keys = {(b["Commit"], b["File"], b["RuleID"], b["StartLine"]) for b in baseline}
    assert baseline_keys == set(fingerprints()), (
        "exception .gitleaksignore harus identik dengan baseline CI "
        f"(baseline={len(baseline_keys)}, ignore={len(fingerprints())})"
    )


def test_exceptions_target_real_commits_and_lines() -> None:
    for sha, path, rule, line in fingerprints():
        assert git("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0, f"commit {sha} tidak ada"
        blob = git("show", f"{sha}:{path}")
        assert blob.returncode == 0, f"{path} tidak ada di commit {sha}"
        assert line <= len(blob.stdout.split("\n")), f"baris {line} di luar isi {path}"
        assert rule == "generic-api-key"


# --- 2. Rule tetap hidup: secret sintetis baru tetap terdeteksi --------------------


@needs_gitleaks
def test_new_synthetic_secret_with_same_rule_is_detected(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "synthetic")
    (repo / "config.py").write_text(f'api_key="{SYNTHETIC_SECRET}"\n', encoding="utf-8")
    commit(repo, "add secret")
    rc, findings = scan(repo, tmp_path / "new.json")
    assert rc == 1, "secret sintetis tidak terdeteksi -> deteksi melemah"
    assert [f["RuleID"] for f in findings] == ["generic-api-key"]


# --- 3. Exception terikat commit: temuan baru di file yang sama tetap dilaporkan ---


@needs_gitleaks
def test_exception_is_commit_scoped_not_path_wide(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "scoped")
    target = repo / "Preferences"
    target.write_text(f'{{"api_key":"{SYNTHETIC_SECRET}"}}\n', encoding="utf-8")
    first = commit(repo, "add one-line blob")

    rc, findings = scan(repo, tmp_path / "before.json")
    assert rc == 1 and len(findings) == 1
    (repo / ".gitleaksignore").write_text(
        f"{first}:Preferences:generic-api-key:1\n", encoding="utf-8"
    )
    commit(repo, "add exception")

    rc, findings = scan(repo, tmp_path / "excepted.json")
    assert rc == 0 and findings == [], "exception per-fingerprint tidak bekerja"

    target.write_text(
        f'{{"api_key":"{SYNTHETIC_SECRET}"}}\napi_key="{SYNTHETIC_SECRET[::-1]}"\n',
        encoding="utf-8",
    )
    second = commit(repo, "add second secret to same file")

    rc, findings = scan(repo, tmp_path / "after.json")
    assert rc == 1, "temuan baru di file yang dikecualikan hilang -> suppress terlalu luas"
    assert [f["Commit"] for f in findings] == [second]
    assert [f["StartLine"] for f in findings] == [2]


@needs_gitleaks
def test_historical_findings_map_to_exceptions_and_scan_is_clean(tmp_path: Path) -> None:
    clone = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(REPO), str(clone)], check=True)
    config = clone / ".gitleaks.toml"
    shutil.copy2(CONFIG_FILE, config)
    ignore_copy = clone / ".gitleaksignore"
    ignore_copy.unlink(missing_ok=True)  # keadaan sebelum exception dipasang

    rc, findings = scan(clone, tmp_path / "raw.json", config=config)
    assert rc == 1, "tanpa exception, pemindaian riwayat harus menemukan 10 temuan historis"
    found = {(f["Commit"], f["File"], f["RuleID"], f["StartLine"]) for f in findings}
    assert found == set(fingerprints()), (
        "tanpa exception, riwayat harus memuat tepat 10 temuan yang diaudit "
        f"(ditemukan {len(found)}, diharapkan {len(set(fingerprints()))})"
    )

    shutil.copy2(IGNORE_FILE, ignore_copy)
    rc, findings = scan(clone, tmp_path / "excepted.json", config=config)
    remaining = {(f["Commit"], f["File"], f["RuleID"], f["StartLine"]) for f in findings}
    assert not (remaining & set(fingerprints())), "temuan historis masih muncul setelah exception"
    assert len(remaining) < 10


# --- 4. Tidak ada allowlist luas ---------------------------------------------------


def test_config_has_no_broad_allowlist() -> None:
    tomllib = pytest.importorskip("tomllib")
    config = tomllib.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    excepted_paths = [path for _, path, _, _ in fingerprints()]
    for entry in config.get("allowlists", []):
        assert "targetRules" not in entry, "targetRules diabaikan gitleaks -> menyesatkan"
        for pattern in entry.get("paths", []):
            assert pattern.rstrip().endswith("$"), f"allowlist tidak ter-anchor ke file: {pattern}"
            rx = re.compile(pattern)
            for path in excepted_paths:
                assert not rx.search(path), f"allowlist {pattern} menutupi file yang dikecualikan"
        assert entry.get("description"), "setiap allowlist wajib punya justifikasi tertulis"


def test_make_secrets_scans_full_history() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    block = makefile.split("\nsecrets:", 1)[1].split("\nsecrets-raw:", 1)[0]
    assert "--config .gitleaks.toml" in block
    assert '--log-opts="--all"' in block
    assert "--redact" in block


# --- 5. Scanner gagal -> tertutup --------------------------------------------------


@needs_gitleaks
def test_scanner_failure_fails_closed(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "broken")
    (repo / "a.txt").write_text("x\n", encoding="utf-8")
    commit(repo, "init")
    broken = repo / "broken.toml"
    broken.write_text("[[rules\n  id = ", encoding="utf-8")
    proc = subprocess.run(
        [GITLEAKS, "detect", "--no-banner", "--config", str(broken), "--log-opts=--all",
         "--report-format", "json", "--report-path", str(tmp_path / "broken.json")],
        cwd=repo, capture_output=True, text=True,
    )
    assert proc.returncode != 0, "konfigurasi rusak harus membuat scanner gagal, bukan hijau"

    ci = CI_FILE.read_text(encoding="utf-8")
    assert "set -euo pipefail" in ci
    assert 'command -v gitleaks >/dev/null 2>&1 || { echo "FAIL gitleaks tidak tersedia di runner"; exit 1; }' in ci
    assert "test -s reports/ci/gitleaks.json" in ci
    assert "--baseline-path .github/gitleaks-baseline.json" in ci
