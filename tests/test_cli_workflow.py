"""Test untuk CLI satu pintu (`scripts/sdb.py`) dan runner 16 tahap (`scripts/workflow_run.py`).

Fokus: kontrak yang mudah rusak tanpa disadari —
  * CLI fail-closed (perintah tak dikenal tidak menebak, tidak menjalankan apa pun);
  * pemetaan perintah -> skrip benar-benar menunjuk berkas yang ADA di repo;
  * runner melaporkan MISSING secara jujur (tidak ada PASS bersyarat) dan
    tidak menghitung tahap tanpa tool sebagai "punya tool";
  * slug divalidasi sebelum dipakai membentuk jalur (CWE-22 path traversal).

Hermetik: semua uji runner memakai akar sintetis di `tmp_path` (opsi `--root`),
sehingga tidak menulis/membaca state host dan tidak meninggalkan sisa di repo.

Jalankan: <python> -m pytest tests/test_cli_workflow.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sdb = load("sdb")
wf = load("workflow_run")
common = load("sdb_common")
gate = load("gate_check")

DEMO = "sdb-local-demo"


def build_fake_target(root, slug=DEMO, skip_stages=()):
    """Buat artefak semua tahap runner di akar sintetis `root`.

    `skip_stages` = kode tahap yang sengaja TIDAK dibuat (untuk uji negatif).
    Return daftar jalur yang dibuat.
    """
    made = []
    for code, _name, patterns, _tool in wf.STAGES:
        if code in skip_stages:
            continue
        # ambil pola pertama yang bisa dibangun (pola fallback tanpa {t} dilewati)
        for pat in patterns:
            if "{t}" not in pat:
                continue
            rel = pat.replace("{t}", slug)
            if "**" in rel:
                d = os.path.join(root, rel.split("**", 1)[0].rstrip("/"))
                os.makedirs(d, exist_ok=True)
                f = os.path.join(d, "artefak.json")
            else:
                f = os.path.join(root, rel)
                os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("{}\n")
            made.append(f)
            break
    os.makedirs(os.path.join(root, "runs", slug), exist_ok=True)
    made.append(os.path.join(root, "runs", slug))
    return made


# ------------------------------------------------------------------ CLI sdb
def test_sdb_unknown_command_fails_closed():
    """Perintah tak dikenal -> exit 2, dan TIDAK menjalankan skrip apa pun."""
    assert sdb.main(["perintah-yang-tidak-ada"]) == 2


def test_sdb_no_args_prints_usage_and_exits_nonzero():
    """Tanpa argumen: tampilkan usage, exit non-nol (bukan diam-diam sukses)."""
    assert sdb.main([]) == 2


def test_sdb_list_json_is_parseable_and_complete():
    """`list --json` harus JSON sah dengan satu entri per perintah terdaftar."""
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = sdb.run(["list", "--json"])
    assert rc == 0
    data = json.loads(buf.getvalue())
    assert len(data) == len(sdb.COMMANDS)
    assert {"command", "kind", "target", "summary"} <= set(data[0])


def test_sdb_every_command_points_to_existing_script():
    """Regresi paling penting: perintah terdaftar tapi berkasnya tidak ada = CLI bohong."""
    missing = []
    for name in sdb.COMMANDS:
        _kind, path, _fixed = sdb.resolve(name)
        if not os.path.isfile(path):
            missing.append(f"{name} -> {path}")
    assert not missing, "perintah menunjuk skrip yang tidak ada: " + "; ".join(missing)


def test_sdb_resolve_rejects_unknown():
    """resolve() harus melempar KeyError (bukan mengembalikan jalur tebakan)."""
    try:
        sdb.resolve("tidak-ada")
    except KeyError:
        return
    raise AssertionError("resolve() seharusnya KeyError untuk perintah tak dikenal")


# ------------------------------------------------------- runner 16 tahap
def test_workflow_stage_codes_unique():
    """Kode tahap tidak boleh duplikat — duplikat menyembunyikan tahap yang hilang."""
    codes = [s[0] for s in wf.STAGES]
    assert len(codes) == len(set(codes))


def test_workflow_stage_patterns_are_relative():
    """Pola artefak harus relatif-repo; pola absolut bisa memindai file di luar repo."""
    for code, _name, patterns, _tool in wf.STAGES:
        for pat in patterns:
            assert not pat.startswith("/"), f"tahap {code}: pola absolut {pat!r}"

def test_workflow_all_stages_ok_on_complete_target(tmp_path):
    """Uji positif: target lengkap -> setiap tahap OK, dan OK selalu punya bukti."""
    build_fake_target(tmp_path)
    rows = wf.evaluate(DEMO, str(tmp_path))
    assert len(rows) == len(wf.STAGES)
    for r in rows:
        assert r["status"] == "OK", f"tahap {r['stage']} seharusnya OK"
        assert r["evidence"], f"tahap {r['stage']} OK tanpa bukti"
        assert "tool" in r


def test_workflow_missing_is_not_silently_passed(tmp_path):
    """Uji negatif: tanpa artefak approval produksi, tahap 13 harus MISSING (bukan PASS)."""
    build_fake_target(tmp_path, skip_stages={"13"})
    rows = wf.evaluate(DEMO, str(tmp_path))
    summary = wf.summarize(rows)
    assert summary["stages_total"] == len(wf.STAGES)
    assert summary["stages_ok"] + summary["stages_missing"] == summary["stages_total"]
    assert summary["stages_missing"] == 1
    assert "HUMAN APPROVAL PRODUKSI" in " ".join(summary["missing"])


def test_workflow_require_all_is_a_real_gate(tmp_path):
    """--require-all: MISSING => exit 1; lengkap => exit 0 (gerbang bisa hijau)."""
    build_fake_target(tmp_path, skip_stages={"13"})
    root = str(tmp_path)
    assert wf.main([DEMO, "--root", root, "--require-all"]) == 1
    build_fake_target(tmp_path)
    assert wf.main([DEMO, "--root", root, "--require-all"]) == 0


def test_workflow_report_mode_without_require_all(tmp_path):
    """Tanpa --require-all hanya laporan: exit 0 walau ada MISSING (untuk inspeksi)."""
    build_fake_target(tmp_path, skip_stages={"13", "16"})
    assert wf.main([DEMO, "--root", str(tmp_path)]) == 0


def test_workflow_unknown_target_is_blocked(tmp_path):
    """Target tak dikenal -> exit 2 (BLOCKED), bukan laporan kosong yang menyesatkan."""
    os.makedirs(os.path.join(tmp_path, "runs", "target-lain"), exist_ok=True)
    assert wf.main(["target-yang-tidak-ada", "--root", str(tmp_path)]) == 2


def test_workflow_summary_counts_stages_with_deterministic_tool():
    """Ringkasan harus jujur soal berapa tahap yang punya tool deterministik."""
    summary = wf.summarize(wf.evaluate(DEMO, "/tmp/akar-kosong-sdb"))
    assert summary["stages_with_deterministic_tool"] == sum(1 for s in wf.STAGES if s[3] != "-")
    assert "tool deterministik" in summary["note"]


# -------------------------------------------------- slug aman (CWE-22 path traversal)
def test_validate_slug_accepts_normal_slugs():
    """Slug wajar harus diterima apa adanya (termasuk konvensi '_' awal repo ini)."""
    for good in ("sdb-local-demo", "target_1", "_selftest_init", "_leading", "a", "A" * 64, "x.y-z"):
        assert common.validate_slug(good) == good


def test_validate_slug_rejects_traversal_and_separators():
    """Inti perbaikan CWE-22: '..' dan pemisah jalur harus DITOLAK.

    Positive control untuk aturan presisi: '-' dan '.' di AWAL masih ditolak
    (slug yang tampak seperti flag / direktori tersembunyi), sementara '_' awal
    DITERIMA — lihat test_validate_slug_accepts_normal_slugs. Tanpa pasangan ini,
    regex yang terlalu longgar (mis. '^.{1,64}$') akan lolos dari test.
    """
    bad = ["..", "../x", "../../../tmp/x", "a/b", "a\\b", ".", "", "   ",
           "a" * 65, "-leading", ".hidden", "_.._", "/etc/passwd", "x\x00y"]
    for b in bad:
        try:
            common.validate_slug(b)
        except ValueError:
            continue
        raise AssertionError(f"slug {b!r} seharusnya ditolak")


def test_gate_check_rejects_traversal_before_creating_dirs():
    """gate_check dengan slug traversal: exit 2 dan TIDAK ada direktori dibuat di luar repo.

    Inilah uji regresi untuk temuan nyata: sebelumnya `--target ../../../tmp/x`
    membuat direktori di luar repo (PermissionError pada /home/tmp).
    """
    rc = gate.main(["--target", "../../../tmp/zz-should-not-exist", "--quiet"])
    assert rc == 2, f"slug traversal seharusnya BLOCKED (exit 2), dapat {rc}"
    assert not os.path.exists("/tmp/zz-should-not-exist")


def test_gate_check_accepts_positional_target_like_other_commands(tmp_path):
    """`sdb gate <slug>` harus jalan seperti `sdb init <slug>` (posisional).

    Uji regresi: sebelumnya hanya `--target` yang didukung, sehingga alur
    Quickstart di README/GETTING_STARTED gagal dengan argparse error.
    """
    out_a, out_b = tmp_path / "a.json", tmp_path / "b.json"
    rc_pos = gate.main(["zz-posisional-gate", "--quiet", "--out", str(out_a)])
    rc_flag = gate.main(["--target", "zz-posisional-gate", "--quiet", "--out", str(out_b)])
    assert rc_pos == rc_flag, f"posisional={rc_pos} vs --target={rc_flag} harus identik"
    assert rc_pos != 0, "manifest kosong/tidak ada wajib fail-closed (bukan PASS)"
    assert out_a.read_text() == out_b.read_text(), "kedua bentuk harus menghasilkan verdict sama"


def test_gate_check_blocks_missing_target_without_crashing(tmp_path):
    """Target tanpa manifest -> BLOCKED terhormat (exit 2), bukan traceback."""
    rc = gate.main(["zz-manifest-tidak-ada", "--quiet", "--out", str(tmp_path / "v.json")])
    assert rc == 2, f"manifest tidak ada seharusnya BLOCKED (exit 2), dapat {rc}"


def test_gate_check_missing_target_is_usage_error():
    """Tanpa target/manifest sama sekali -> argparse usage error (exit 2)."""
    with pytest.raises(SystemExit) as exc:
        gate.main([])
    assert exc.value.code == 2


def test_workflow_rejects_traversal_slug():
    """Runner juga harus fail-closed pada slug traversal."""
    assert wf.main(["../../../tmp/zz-should-not-exist"]) == 2
