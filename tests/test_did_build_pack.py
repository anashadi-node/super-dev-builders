"""Uji gerbang build pack: kesiapan harus dihitung, bukan dipercaya."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import did_build_pack as bp


def _handoff(**ubah):
    h = {
        "schema": "sdb.did.handoff/1",
        "target": {"slug": "demo", "name": "Demo App", "type": "web"},
        "evidence_manifest": [{"id": "E-001", "path": "a.txt"}, {"id": "E-002", "path": "b.txt"}],
        "findings": [
            {"id": "F-001", "status": "OBSERVED", "severity": "high", "claim": "Bug A — rincian", "evidence": ["E-001"]},
            {"id": "F-002", "status": "INFERRED", "severity": "low", "claim": "Dugaan B", "evidence": ["E-002"]},
        ],
        "features": [
            {"id": "FT-01", "name": "Fitur satu", "priority": "must", "findings": ["F-001"],
             "acceptance_tests": [{"given": "g", "when": "w", "then": "t"}]},
        ],
        "build_seeds": {"entities": [{"name": "x"}], "api": [{"path": "/a"}], "states": ["kosong"]},
        "handoff": {"builders_ready": True, "blocking_unknowns": 0},
    }
    h.update(ubah)
    return h


def _cek(h):
    return {c["kode"]: c for c in bp.periksa(h)}


def test_handoff_layak_lulus_semua_gerbang():
    cek = _cek(_handoff())
    assert all(c["ok"] for c in cek.values()), cek


def test_fitur_must_tanpa_tes_penerimaan_ditolak():
    h = _handoff()
    h["features"][0]["acceptance_tests"] = []
    cek = _cek(h)
    assert not cek["B01"]["ok"]
    assert "FT-01" in cek["B01"]["detail"]


def test_bukti_tak_terdaftar_menutup_gerbang():
    h = _handoff()
    h["findings"][0]["evidence"] = ["E-999"]
    assert not _cek(h)["B04"]["ok"]


def test_bendera_siap_tanpa_nol_blocking_ditolak():
    h = _handoff(handoff={"builders_ready": True, "blocking_unknowns": 2})
    assert not _cek(h)["B06"]["ok"]


def test_tiket_hanya_dari_temuan_teramati_dan_urut_p0():
    pack = bp.bangun_pack(_handoff())
    ids = [t["dari_temuan"] for t in pack["tiket_perbaikan"]]
    assert ids == ["F-001"], ids
    assert pack["tiket_perbaikan"][0]["prioritas"] == "P0"


def test_cli_gagal_tanpa_menulis_pack(tmp_path):
    h = _handoff()
    h["build_seeds"]["api"] = []
    src = tmp_path / "handoff.json"
    src.write_text(json.dumps(h), encoding="utf-8")
    out = tmp_path / "out"
    rc = subprocess.run([sys.executable, str(ROOT / "scripts/did_build_pack.py"),
                         "--handoff", str(src), "--out-dir", str(out)], capture_output=True)
    assert rc.returncode == 1
    assert not (out / "BUILD_PACK.md").exists()
    rc2 = subprocess.run([sys.executable, str(ROOT / "scripts/did_build_pack.py"),
                          "--handoff", str(src), "--out-dir", str(out), "--allow-not-ready"],
                         capture_output=True)
    assert rc2.returncode == 0 and (out / "BUILD_PACK.md").exists()
