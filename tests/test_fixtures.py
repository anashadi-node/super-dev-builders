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

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_fixtures
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


def test_toolchain_fixture_dikunci_dan_fail_closed(monkeypatch):
    assert build_fixtures.CC == "/usr/bin/gcc-13"
    assert build_fixtures.LD == "/usr/bin/ld.bfd"
    monkeypatch.setattr(build_fixtures.os.path, "isfile", lambda _path: True)
    monkeypatch.setattr(build_fixtures.os, "access", lambda _path, _mode: True)
    monkeypatch.setattr(build_fixtures, "_versi", lambda _path: "versi-salah")
    with pytest.raises(RuntimeError, match="versi toolchain fixture bergeser"):
        build_fixtures.verify_toolchain()


def _wajibkan_toolchain_tersedia():
    try:
        build_fixtures.verify_toolchain()
    except RuntimeError as exc:
        if os.environ.get("SDB_REQUIRE_FIXTURE_TOOLCHAIN") == "1":
            pytest.fail(str(exc))
        pytest.skip(f"toolchain fixture ter-pin tidak tersedia: {exc}")


def test_build_fixture_tidak_bergantung_cwd(tmp_path, monkeypatch):
    _wajibkan_toolchain_tersedia()
    hashes = []
    for index in range(3):
        cwd = tmp_path / f"cwd-{index}"
        out = tmp_path / f"out-{index}"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        hashes.append(
            {
                target: build_fixtures.sha256(builder(str(out / target)))
                for target, builder in build_fixtures.BUILDERS.items()
            }
        )
    assert hashes[0] == hashes[1] == hashes[2]


def test_android_menolak_symlink_sebelum_menulis(tmp_path):
    out = tmp_path / "android"
    assets = out / "src" / "assets"
    assets.mkdir(parents=True)
    korban = tmp_path / "korban-sintetis.txt"
    korban.write_text("JANGAN_DIUBAH", encoding="utf-8")
    (assets / "config.json").symlink_to(korban)

    with pytest.raises(RuntimeError, match="symlink"):
        build_fixtures.build_android(str(out))
    assert korban.read_text(encoding="utf-8") == "JANGAN_DIUBAH"


def test_android_menolak_berkas_tambahan_dari_apk(tmp_path):
    _wajibkan_toolchain_tersedia()
    out = tmp_path / "android"
    ekstra = out / "src" / "lib" / "x86_64" / "extra.secret"
    ekstra.parent.mkdir(parents=True)
    ekstra.write_text("NILAI_SINTETIS", encoding="utf-8")

    with pytest.raises(RuntimeError, match=r"ekstra=.*extra\.secret"):
        build_fixtures.build_android(str(out))


def test_android_menolak_symlink_pada_ancestor(tmp_path):
    luar = tmp_path / "luar"
    luar.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(luar, target_is_directory=True)

    with pytest.raises(RuntimeError, match="melewati symlink"):
        build_fixtures.build_android(str(alias / "android"))
    assert not (luar / "android").exists()


def test_android_menolak_hardlink_sebelum_menulis(tmp_path):
    out = tmp_path / "android"
    assets = out / "src" / "assets"
    assets.mkdir(parents=True)
    korban = tmp_path / "korban-hardlink-sintetis.txt"
    korban.write_text("JANGAN_DIUBAH", encoding="utf-8")
    os.link(korban, assets / "config.json")

    with pytest.raises(RuntimeError, match="hardlink"):
        build_fixtures.build_android(str(out))
    assert korban.read_text(encoding="utf-8") == "JANGAN_DIUBAH"
