"""Uji provenance hasil bench: status post-hoc tidak boleh hilang saat diukur ulang.

Regresi yang dijaga: `bench --json-out` pernah menimpa laporan sehingga field
`post_hoc`, `gate`, dan `why_not_promoted` lenyap. Angka indikatif lalu terbaca
seperti gerbang rilis.
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import did_validate as dv


def _fixture(tmp_path):
    """Handoff + label minimal di tmp_path.

    Sengaja tidak memakai `runs/<t>/did/*` : artefak itu tidak ada di runner CI,
    dan uji yang bergantung padanya merah di mesin bersih (uji tak hermetik).
    """
    handoff = {"target": {"slug": "contoh"},
               "features": [{"id": "F-001", "name": "Halaman kas", "status": "OBSERVED",
                             "evidence": ["E-001"], "keywords": ["kas"]}]}
    truth = {"features": [{"id": "T-001", "name": "Halaman kas", "keywords": ["kas"]}]}
    h = tmp_path / "handoff.json"
    t = tmp_path / "ground_truth-posthoc.json"
    h.write_text(json.dumps(handoff), encoding="utf-8")
    t.write_text(json.dumps(truth), encoding="utf-8")
    return h, t


def test_label_di_luar_benchmarks_ditandai_post_hoc(tmp_path):
    truth = tmp_path / "ground_truth-posthoc.json"
    truth.write_text(json.dumps({"features": []}), encoding="utf-8")
    prov = dv._bench_provenance(str(truth))
    assert prov["post_hoc"] is True
    assert prov["gate"]
    assert prov["why_not_promoted"]


def test_label_di_benchmarks_bukan_post_hoc():
    prov = dv._bench_provenance(os.path.join(ROOT, "benchmarks", "rt-rw-portal", "ground_truth.json"))
    assert prov["post_hoc"] is False
    assert prov["truth"].startswith("benchmarks/")
    assert "gate" not in prov


def test_bench_json_out_mempertahankan_provenance(tmp_path):
    handoff, truth = _fixture(tmp_path)
    out = tmp_path / "bench.json"
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "did_validate.py"), "bench",
         "--handoff", str(handoff), "--truth", str(truth), "--json-out", str(out)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["post_hoc"] is True
    assert data["gate"] and data["why_not_promoted"]
    assert data["precision"] == 1.0
    assert out.read_text(encoding="utf-8").endswith("\n")
