"""Test untuk 2 skill pengganti hasil riset lanjutan (mandat Owner 2026-10-04).

Fokus: menjaga klaim "kapabilitas melebihi skill yang dihapus" tetap berbasis bukti,
bukan narasi. Test ini cepat (baca file/JSON saja), tidak menjalankan Chromium/LLM.
"""
from __future__ import annotations

import json
import os
import re

import pytest
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(REPO, "registry", "skills.yaml")
EVIDENCE = os.path.join(REPO, "reports", "upgrade-evidence")

NEW_SKILLS = {
    "local-llm-serving": {"serving-llms-vllm", "inference-sh-cli"},
    "realtime-visual-engine": {"touchdesigner-mcp"},
}


def _registry() -> dict:
    with open(REGISTRY, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.mark.parametrize("skill_id,replaces", sorted(NEW_SKILLS.items()))
def test_skill_terdaftar_dengan_klaim_parity_dan_bukti(skill_id, replaces):
    reg = _registry()
    entry = next((c for c in (reg.get("custom") or []) if c.get("id") == skill_id), None)
    assert entry is not None, f"{skill_id} tidak ada di registry"
    raw_replaces = entry.get("replaces")
    listed = set(raw_replaces if isinstance(raw_replaces, list) else [x.strip() for x in str(raw_replaces).split(",")])
    assert listed >= replaces, f"{skill_id} harus menyatakan replaces {replaces}, ada {listed}"
    assert entry.get("parity", "").startswith(">="), f"{skill_id} wajib punya klaim parity >= dengan alasan"
    ev = os.path.join(REPO, entry.get("evidence", ""))
    assert os.path.exists(ev), f"artefak bukti tidak ada: {ev}"
    assert os.path.getsize(ev) > 200, "artefak bukti terlalu kecil untuk valid"


@pytest.mark.parametrize("skill_id", sorted(NEW_SKILLS))
def test_skill_tidak_melanggar_aturan_privilege(skill_id):
    root = os.path.join(REPO, "skills", skill_id)
    assert os.path.isfile(os.path.join(root, "SKILL.md")), f"SKILL.md hilang di {skill_id}"
    assert os.path.isdir(os.path.join(root, "scripts")), f"scripts/ hilang di {skill_id}"
    pola = [re.compile(r"\bsudo\b"), re.compile(r"curl[^\n|]*\|\s*(ba)?sh"), re.compile(r"os\.system\(")]
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith((".py", ".sh")):
                continue
            text = open(os.path.join(dirpath, name), encoding="utf-8").read()
            for p in pola:
                assert not p.search(text), f"{os.path.join(dirpath, name)} melanggar aturan: {p.pattern}"


def test_bukti_serving_menunjukkan_continuous_batching():
    with open(os.path.join(EVIDENCE, "local-llm-serving-bench.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    assert d["health"][0] == 200 and d["health"][1]["status"] == "ok"
    assert d["single"]["status"] == 200 and d["single"]["completion_tokens"] > 0
    par = d["parallel_run"]
    assert par["n"] == 4 and par["all_http_200"] is True
    assert par["aggregate_tok_per_s"] > d["single"]["tok_per_s"], "batching tidak menaikkan throughput agregat"
    assert d["continuous_batching_proven"] is True
    assert (d.get("rss_mb_after_parallel") or 0) > 100, "memori server tidak terukur"


def test_bukti_visual_realtime_memenuhi_kriteria():
    with open(os.path.join(EVIDENCE, "realtime-visual-report.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    assert d["gl_renderer"], "tidak ada konteks WebGL nyata"
    assert d["udp_received"], "kontrol eksternal tidak diterima"
    assert d["udp_override_active"] is True
    assert d["param_changes_pixels"] is True
    assert d["last_frame_differs_from_internal_default"] is True
    assert d["applied_value_reproduces_last_frame"] is True
    assert d["unique_frames"] >= 8
    assert d["ffmpeg_rc"] == 0 and d["mp4_bytes"] > 10_000
    assert os.path.exists(os.path.join(EVIDENCE, "realtime-visual.mp4"))


def test_provenance_model_terpin_sha256():
    src = open(os.path.join(REPO, "skills", "model-hub-provenance", "scripts", "fetch_gguf.py"), encoding="utf-8").read()
    m = re.search(r'EXPECTED_SHA256 = "([0-9a-f]{64})"', src)
    assert m, "sha256 model tidak dipin di script pengunduh"
    assert "modelscope" in src and "hf-mirror" in src, "jalur alternatif sumber model tidak terdokumentasi di script"
