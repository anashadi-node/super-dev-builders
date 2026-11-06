"""Fixture DID mobile/desktop — uji bahwa bukti yang dirujuk benar-benar ada.

Fixture bisa "lulus" benchmark hanya karena handoff-nya menyebut nama fitur. Itu
tidak membuktikan apa pun bila berkas bukti hilang atau hash sudah bergeser. Uji di
sini mengunci dua hal: artefak fixture cocok dengan hash tercatat, dan handoff
menghasilkan skor di atas ambang terhadap label independen.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import did_validate

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blok in iter(lambda: fh.read(65536), b""):
            h.update(blok)
    return h.hexdigest()


def test_artefak_fixture_cocok_dengan_hash_tercatat():
    for target, rel in (("android-mini", "artifact/android-mini.apk"),
                        ("desktop-mini", "artifact/desktop-mini")):
        stamp = os.path.join(ROOT, "fixtures", target, "artifact.sha256")
        artefak = os.path.join(ROOT, "fixtures", target, rel)
        assert os.path.isfile(artefak), f"{target}: artefak tidak ada — jalankan make fixtures"
        tercatat = open(stamp, encoding="utf-8").read().split()[0]
        assert _sha256(artefak) == tercatat, f"{target}: hash bergeser, bangun ulang fixture"


def test_sumber_fixture_ikut_git_dan_bukan_biner_pihak_ketiga():
    for rel in ("fixtures/desktop-mini/src/desktop-mini.c",
                "fixtures/desktop-mini/src/installer.sh",
                "fixtures/desktop-mini/src/update-channel.json",
                "fixtures/android-mini/src/AndroidManifest.xml",
                "fixtures/android-mini/src/assets/config.json"):
        path = os.path.join(ROOT, rel)
        assert os.path.isfile(path), f"sumber hilang: {rel}"
        assert os.path.getsize(path) < 8000, f"sumber tak wajar besar: {rel}"


def test_handoff_fixture_lolos_ambang_benchmark():
    for target in ("android-mini", "desktop-mini"):
        truth = json.load(open(os.path.join(ROOT, "benchmarks", target, "ground_truth.json"), encoding="utf-8"))
        handoff = json.load(open(os.path.join(ROOT, "benchmarks", target, "handoff.json"), encoding="utf-8"))
        skor = did_validate.bench(handoff, truth)
        assert skor["hallucination_rate"] == 0, f"{target}: ada klaim OBSERVED tanpa bukti"
        assert skor["recall"] >= 0.9, f"{target}: recall {skor['recall']:.3f}"
        assert skor["precision"] >= 0.9, f"{target}: presisi {skor['precision']:.3f}"


def test_evidence_yang_dirujuk_handoff_ada_di_disk():
    for target in ("android-mini", "desktop-mini"):
        handoff = json.load(open(os.path.join(ROOT, "benchmarks", target, "handoff.json"), encoding="utf-8"))
        for item in handoff["evidence_manifest"]:
            path = os.path.join(ROOT, item["path"])
            assert os.path.isfile(path), f"{target}: evidence hilang {item['path']}"
            assert _sha256(path) == item["sha256"], f"{target}: hash evidence bergeser {item['path']}"
