"""Wiring Divisi Investigasi (DID) di SDB: charter, pack, tahap, registry, dashboard.

Uji ini menjaga agar DID tetap "menempel" pada mesin yang ada (satu registry tahap,
satu registry skill, pack otomatis) dan tidak menjadi pohon paralel yang cepat basi.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import pack_build
import stage_registry


def test_tahap_01c_ada_dan_punya_alat():
    rows = {r["code"]: r for r in stage_registry.stages()}
    assert "01C" in rows, "tahap DID hilang dari registry"
    st = rows["01C"]
    assert st["tool"] == "did_validate.py"
    assert any("handoff.json" in a for a in st["artifacts"])
    assert st["kind"] == "exec" and st["human"] is False


def test_charter_investigator():
    path = os.path.join(ROOT, "agents", "sdb-investigator.yaml")
    charter = yaml.safe_load(open(path, encoding="utf-8"))
    assert charter["id"] == "sdb-investigator"
    assert charter["divisions"] == ["D1"]
    # profil Hermes harus profil yang sudah ada (tanpa membuat profil/config baru)
    known = {yaml.safe_load(open(p, encoding="utf-8")).get("hermes_profile")
             for p in glob.glob(os.path.join(ROOT, "agents", "*.yaml"))}
    assert charter["hermes_profile"] in known
    assert charter["evidence_rules"]["machine_gate"] == "scripts/did_validate.py"
    assert "write_product_code" in charter["permissions"]["forbidden"]
    assert "auth_bypass" in charter["permissions"]["forbidden"]
    assert charter["model_routing"]["primary"] == "deepseek-flash"


def test_pack_did_sehat_dan_dalam_batas():
    packs = pack_build.build_packs(ROOT)
    assert "sdb-investigator" in packs
    pack = json.load(open(os.path.join(ROOT, "platform", "packs", "sdb-investigator.json"), encoding="utf-8"))
    assert pack_build.pack_errors(pack) == []
    assert pack_build.registry_drift(pack) == []
    total = len(pack["skills"]) + len(pack["required_native"])
    assert total <= pack_build.MAX_SKILLS, f"{total} > {pack_build.MAX_SKILLS}"


def test_pack_tidak_memuat_replica_skill():
    pack = json.load(open(os.path.join(ROOT, "platform", "packs", "sdb-investigator.json"), encoding="utf-8"))
    ids = {s["id"] for s in pack["skills"]}
    assert "replica-skill-pipeline" not in ids
    assert {"did-evidence-ledger", "did-handoff", "did-benchmark"} <= ids


def test_registry_konsisten_dengan_persetujuan():
    reg = yaml.safe_load(open(os.path.join(ROOT, "registry", "skills.yaml"), encoding="utf-8"))
    assert len(reg["custom"]) == int(reg["approved_custom_count"])
    ids = {c["id"] for c in reg["custom"]}
    for sid in ("did-evidence-ledger", "did-handoff", "did-benchmark"):
        assert sid in ids


def test_dashboard_mengenali_investigator():
    agents = json.load(open(os.path.join(ROOT, "dashboard", "agents.json"), encoding="utf-8"))
    assert agents["sdb-investigator"]["stages"] == ["01C"]
    assert "did_validate" in agents["sdb-investigator"]["gates"]


def test_cli_menolak_handoff_yang_tidak_ada():
    p = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "did_validate.py"),
                        "validate", "--target", "tidak-ada-target-ini"],
                       capture_output=True, text=True)
    assert p.returncode == 2
    assert "tidak ada" in (p.stdout + p.stderr).lower()


def test_dokumen_did_ada():
    for rel in ("docs/DID_DIVISI_INVESTIGASI.md",):
        assert os.path.exists(os.path.join(ROOT, rel)), f"{rel} hilang"
