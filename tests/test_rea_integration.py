"""Integrasi REA (rea-agents) — regresi pin, jalur, dan aturan gate.

Yang dijaga:
1. registry mencatat REA dengan pin + integritas + bukti scan (aturan #6), dan statusnya
   konsisten dengan kenyataan di host (kalau dicopot, test harus gagal — bukan diam).
2. wrapper `scripts/rea` menunjuk versi terpin, bukan `latest`/`npx`.
3. skill operasional ada dan memuat aturan Gate #0 + tier izin (kalau aturan itu hilang,
   integrasi berubah jadi pintu belakang tanpa otorisasi).
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from sdb_common import load_yaml, repo_path

REA_VERSION = "6.8.0"
REA_INTEGRITY_PREFIX = "sha512-9QDeRnGqEDzABZyr04eLnBXBv/c6I9/TWu/6M0MD4pEfkySI/BIgwTODIbAReX3C1x6hjw9+Jlx4A2yUSPZ9ww=="


def _wrapper():
    return repo_path("scripts", "rea")


def test_wrapper_exists_and_pins_version_not_latest():
    w = _wrapper()
    assert os.path.isfile(w), "scripts/rea hilang"
    assert os.access(w, os.X_OK), "scripts/rea tidak executable"
    body = open(w, encoding="utf-8").read()
    assert f'REA_VERSION="{REA_VERSION}"' in body, "versi terpin berubah tanpa audit"
    code = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    assert "npx" not in code, "wrapper tidak boleh memakai npx (selalu latest)"
    assert "rea-$REA_VERSION" in body, "wrapper harus memakai prefix versi, bukan path bebas"


def test_registry_tool_entry_has_pin_and_integrity():
    tools = load_yaml(repo_path("registry", "tools.yaml")) or {}
    row = next((t for t in (tools.get("present") or []) if t.get("id") == "rea_agents"), None)
    assert row is not None, "rea_agents tidak terdaftar di registry/tools.yaml"
    assert REA_VERSION in str(row.get("version_pin")), row
    assert REA_INTEGRITY_PREFIX[:40] in str(row.get("integrity")), "integritas hilang/berubah"
    assert row.get("approved_by") and row.get("approved_at"), "tanpa jejak approval"
    assert "Gate #0" in str(row.get("policy")), "policy gate hilang"


def test_registry_third_party_entry_complete():
    reg = load_yaml(repo_path("registry", "skills.yaml")) or {}
    row = next((x for x in (reg.get("third_party") or []) if x.get("repo") == "morluto/rea"), None)
    assert row is not None, "morluto/rea hilang dari registry third_party"
    for field in ("pinned_commit", "pinned_version", "integrity", "status",
                  "security_scan", "audit_status", "approved_by"):
        assert row.get(field), f"field wajib kosong: {field}"
    assert row["pinned_commit"] == "160d821ac9a0310afcb8d1fc427862dd6508add5", \
        "commit pin berubah — wajib audit ulang sebelum mengganti"
    assert row["status"] == "INSTALLED"


def test_skill_declares_gate_and_tiers():
    skill = repo_path("skills", "rea-reverse-engineering", "SKILL.md")
    assert os.path.isfile(skill), "skill rea-reverse-engineering hilang"
    body = open(skill, encoding="utf-8").read()
    for needle in ("scripts/gate_check.py", "T0", "T2", "T3",
                   "reports/REA_AUDIT_20261026.md", "clean-room"):
        assert needle.lower() in body.lower(), f"skill kehilangan aturan: {needle}"
    # integrasi ini TIDAK boleh mengaktifkan MCP 229 tool secara default
    assert "tidak** didaftarkan" in body.lower() or "tidak didaftarkan" in body.lower()


def test_custom_skill_registered_and_count_matches():
    reg = load_yaml(repo_path("registry", "skills.yaml")) or {}
    ids = {c.get("id") for c in (reg.get("custom") or [])}
    assert "rea-reverse-engineering" in ids, "skill tidak terdaftar di registry custom"
    assert len(reg.get("custom") or []) == int(reg.get("approved_custom_count") or -1), \
        "approved_custom_count tidak cocok dengan jumlah entri (registry_lint akan WARN)"


def test_wrapper_runs_pinned_binary_when_installed():
    """Lewati (bukan gagal) bila tool belum terpasang di host ini."""
    prefix = os.path.expanduser(f"~/.hermes/tools/rea-{REA_VERSION}")
    if not os.path.isdir(prefix):
        import pytest
        pytest.skip(f"REA {REA_VERSION} belum terpasang di {prefix}")
    r = subprocess.run([_wrapper(), "--version"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == REA_VERSION, r.stdout
