"""Aturan #6 registry: entri pihak ketiga harus punya pin + jejak scan/review/alasan.

Regresi yang dicegah (audit 2026-10-07): `registry_lint.py` dulu berisi
`elif section.startswith("third"): pass` — no-op, sehingga aturan #6 hanya tampak
diperiksa. Sekarang diperiksa nyata, tetapi tidak boleh over-fire: entri yang DITAHAN
(QUARANTINE/DEFER) cukup punya alasan, tidak wajib bukti scan.
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from sdb_common import load_yaml, repo_path


def test_registry_lint_passes_on_repo_state():
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "registry_lint.py")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_third_party_has_pinned_commit_and_source():
    reg = load_yaml(repo_path("registry", "skills.yaml")) or {}
    rows = reg.get("third_party") or []
    assert rows, "registry third_party tidak boleh kosong"
    for x in rows:
        assert x.get("repo"), x
        assert x.get("pinned_commit"), f"{x.get('repo')} tanpa pinned_commit (aturan #6)"
        assert x.get("status"), f"{x.get('repo')} tanpa status"


def test_adopted_third_party_have_scan_evidence():
    """Setiap entri yang benar-benar DIPAKAI harus punya bukti scan tercatat.

    Kalau test ini gagal, itu temuan nyata: tambahkan bukti scan/review ke entri
    registry, atau turunkan statusnya menjadi QUARANTINE/DEFER bila memang belum
    diaudit. Jangan melonggarkan test.
    """
    reg = load_yaml(repo_path("registry", "skills.yaml")) or {}
    adopted = {"INSTALLED", "IN_USE", "OPTIONAL"}
    scan_fields = ("scan", "scanner", "scan_evidence", "security_scan", "audit", "audit_status")
    missing = [x.get("repo") for x in (reg.get("third_party") or [])
               if x.get("status") in adopted and not any(x.get(f) for f in scan_fields)]
    assert missing == [], f"terpakai tapi tanpa bukti scan: {missing}"


def test_held_third_party_have_a_reason_somewhere():
    """QUARANTINE/DEFER: tidak dipakai, jadi cukup ada alasan (di entri atau tools.yaml)."""
    reg = load_yaml(repo_path("registry", "skills.yaml")) or {}
    tools = load_yaml(repo_path("registry", "tools.yaml")) or {}
    held_ids = {it.get("id") for sec in ("quarantine", "deferred")
                for it in (tools.get(sec) or []) if isinstance(it, dict)}
    note_fields = ("gate_note", "decision_note", "evidence", "caveats", "license_note", "reason")
    missing = []
    for x in (reg.get("third_party") or []):
        if x.get("status") in ("QUARANTINE", "DEFER"):
            short = str(x.get("repo") or "").split("/")[-1].lower()
            if not any(x.get(f) for f in note_fields) and short not in held_ids:
                missing.append(x.get("repo"))
    assert missing == [], f"ditahan tanpa alasan: {missing}"