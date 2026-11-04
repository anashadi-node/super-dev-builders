"""recon-forge — uji negatif & positif tanpa menyentuh jaringan atau target nyata.

Fokus uji: alat ini alat *izin*. Kegagalan paling mahal bukan "tidak bisa jalan",
melainkan "jalan padahal tidak boleh". Karena itu penolakan diuji lebih dulu.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "recon-forge.py"
os.environ["SDB_AUDIT_DISABLED"] = "1"


def load_tool(root: Path | None = None):
    spec = importlib.util.spec_from_file_location("recon_forge", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if root is not None:
        mod.REPO = root
        mod.AUDIT_LOG = root / "audit" / "audit-log.jsonl"
        mod.REA_WRAPPER = root / "scripts" / "rea"
    return mod


def fake_repo(tmp_path: Path, verdict: dict | None, urls=("http://127.0.0.1:8201",)) -> Path:
    (tmp_path / "reports" / "uji").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence" / "uji").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tools").mkdir(exist_ok=True)
    (tmp_path / "tools" / "audit-log.py").write_text("print('ok')\n", encoding="utf-8")
    if verdict is not None:
        (tmp_path / "reports" / "uji" / "gate0-verdict.json").write_text(
            json.dumps(verdict), encoding="utf-8")
    manifest = (
        "schema_version: 2.2\n"
        "target_name: uji\n"
        "mode: A\n"
        "allowed_targets:\n"
        f"  urls: [{', '.join(repr(u) for u in urls)}]\n"
    )
    (tmp_path / "evidence" / "uji" / "authorization.yaml").write_text(manifest, encoding="utf-8")
    return tmp_path


def test_tanpa_gate_harus_menolak(tmp_path):
    root = fake_repo(tmp_path, None)
    mod = load_tool(root)
    try:
        mod.require_gate("uji")
    except mod.ForgeError as exc:
        assert exc.code == 2
        assert "Gate #0 belum ada" in str(exc)
    else:
        raise AssertionError("require_gate LOLOS tanpa verdict — lubang keamanan")


def test_gate_fail_harus_menolak(tmp_path):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "FAIL"})
    mod = load_tool(root)
    try:
        mod.require_gate("uji")
    except mod.ForgeError as exc:
        assert exc.code == 2 and "STOP" in str(exc)
    else:
        raise AssertionError("verdict FAIL diterima — lubang keamanan")


def test_verdict_target_lain_harus_menolak(tmp_path):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "lain", "verdict": "PASS"})
    mod = load_tool(root)
    try:
        mod.require_gate("uji")
    except mod.ForgeError as exc:
        assert exc.code == 2 and "bukan 'uji'" in str(exc)
    else:
        raise AssertionError("verdict milik target lain diterima")


def test_url_di_luar_scope_harus_menolak(tmp_path):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    mod = load_tool(root)
    try:
        mod.require_url("uji", "http://evil.invalid/")
    except mod.ForgeError as exc:
        assert exc.code == 2 and "TOLAK" in str(exc)
    else:
        raise AssertionError("URL di luar allowed_targets diterima")


def test_url_dalam_scope_lolos(tmp_path):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    mod = load_tool(root)
    mod.require_url("uji", "http://127.0.0.1:8201/index.html")


def test_plan_menulis_rencana_tanpa_eksekusi(tmp_path, capsys):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    mod = load_tool(root)
    args = type("A", (), {"target": "uji", "kind": "web", "json": True})()
    assert mod.cmd_plan(args) == 0
    plan = json.loads((root / "runs" / "uji" / "recon-plan.json").read_text(encoding="utf-8"))
    assert plan["gate0"] == "PASS"
    assert {s["engine"] for s in plan["stages"]} == {"rea", "sdb"}
    assert plan["combination"]["rebuild"].startswith("replica-skill")


def test_plan_mencatat_gate_missing(tmp_path):
    root = fake_repo(tmp_path, None)
    mod = load_tool(root)
    args = type("A", (), {"target": "uji", "kind": "native", "json": True})()
    assert mod.cmd_plan(args) == 0
    plan = json.loads((root / "runs" / "uji" / "recon-plan.json").read_text(encoding="utf-8"))
    assert plan["gate0"] == "MISSING"


def test_build_craft_tanpa_biner_berhenti(tmp_path, capsys, monkeypatch):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    mod = load_tool(root)
    monkeypatch.setattr(mod, "craft_bin", lambda: None)
    args = type("A", (), {"target": "uji", "engine": "craft"})()
    assert mod.cmd_build(args) == 3
    assert "belum terpasang" in capsys.readouterr().err


def test_build_replica_tanpa_spec_menolak(tmp_path):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    mod = load_tool(root)
    args = type("A", (), {"target": "uji", "engine": "replica"})()
    try:
        mod.cmd_build(args)
    except mod.ForgeError as exc:
        assert exc.code == 2 and "SPEC belum ada" in str(exc)
    else:
        raise AssertionError("build jalan tanpa SPEC — melanggar G1")


def test_mean_coverage_mengabaikan_yang_tidak_terukur():
    mod = load_tool()
    rows = [{"coverage": 1.0}, {"coverage": 0.5}, {"coverage": None}, {"status": "NOT_MEASURED"}]
    assert mod.mean_coverage(rows) == 0.75
    assert mod.mean_coverage([]) is None


def test_report_menandai_yang_hilang_sebagai_missing(tmp_path):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    mod = load_tool(root)
    args = type("A", (), {"target": "uji"})()
    assert mod.cmd_report(args) == 0
    rep = json.loads((root / "reports" / "uji" / "recon-forge-report.json").read_text(encoding="utf-8"))
    status = {s["stage"]: s["status"] for s in rep["stages"]}
    assert status["01A.gate0"] == "PASS"
    assert status["01B.recon"] == "MISSING"
    assert status["09.parity"] == "UNPROVEN"  # bukan MISSING: alat menyatakan belum terukur
    assert rep["ladder"]["evidence_collected"] is False
    assert rep["ladder"]["release_ready"] is False
    assert any("paritas" in u for u in rep["unknowns"]) or any("SPEC" in u for u in rep["unknowns"])


def test_doctor_json_memuat_kunci_wajib(tmp_path, monkeypatch, capsys):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    mod = load_tool(root)
    monkeypatch.setattr(mod, "rea_version", lambda: "6.8.0")
    monkeypatch.setattr(mod, "craft_bin", lambda: None)
    monkeypatch.setattr(mod, "chromium_bin", lambda: Path("/bin/true"))
    args = type("A", (), {"json": True})()
    assert mod.cmd_doctor(args) == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data["engines"]) >= {"rea", "craft_anything", "chromium", "sdb_scripts"}
    assert data["engines"]["craft_anything"]["found"] is False
    assert "honest_note" in data["verdict"]


def test_native_tanpa_path_ditolak(tmp_path):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    mod = load_tool(root)
    args = type("A", (), {"target": "uji", "path": "", "kind": "native", "decompile": False,
                          "decompile_limit": 0, "timeout": 10, "json": False})()
    try:
        mod.cmd_recon(args)
    except mod.ForgeError as exc:
        assert exc.code == 2 and "--path" in str(exc)
    else:
        raise AssertionError("recon native jalan tanpa --path")


def test_native_path_di_luar_izin_ditolak(tmp_path):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    luar = tmp_path / "luar" / "evil.bin"
    luar.parent.mkdir(parents=True)
    luar.write_bytes(b"\x7fELF")
    mod = load_tool(root)
    try:
        mod.require_path("uji", str(luar))
    except mod.ForgeError as exc:
        assert exc.code == 2 and "TOLAK" in str(exc)
    else:
        raise AssertionError("path di luar akar izin diterima")


def test_native_path_di_dalam_akar_izin_lolos(tmp_path):
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    dalam = root / "targets" / "uji" / "app.bin"
    dalam.parent.mkdir(parents=True)
    dalam.write_bytes(b"\x7fELF")
    mod = load_tool(root)
    assert mod.require_path("uji", str(dalam)) == dalam.resolve()
    assert mod.require_path("uji", str(dalam.parent)) == dalam.parent.resolve()


def test_node_ok_memakai_patch_minimum_rea():
    mod = load_tool()
    assert mod.node_ok("v26.13.0") is True
    assert mod.node_ok("v26.7.0") is False      # yang Hermes bawa: gagal syarat
    assert mod.node_ok("v24.22.1") is True
    assert mod.node_ok("v24.21.0") is False
    assert mod.node_ok("v22.23.4") is True
    assert mod.node_ok("") is False


def test_jdk_ok_menolak_instalasi_terpotong(tmp_path):
    """`bin/java` 0 byte + `release` kosong = JDK palsu (kasus nyata 2026-11-04)."""
    mod = load_tool()
    buruk = tmp_path / "jdk-21.0.13+9"
    (buruk / "bin").mkdir(parents=True)
    (buruk / "bin" / "java").write_bytes(b"")
    (buruk / "release").write_bytes(b"")
    assert mod.jdk_ok(buruk) is False
    assert mod.jdk_home([tmp_path]) is None, "JDK rusak dipilih sebagai JAVA_HOME"


def test_jdk_home_memilih_yang_utuh(tmp_path):
    mod = load_tool()
    for nama, versi in (("jdk-21.0.13+9", "21.0.13+9"), ("jdk-21.0.14+7", "21.0.14+7")):
        d = tmp_path / nama
        (d / "bin").mkdir(parents=True)
        (d / "bin" / "java").write_bytes(b"\x7fELF")
        (d / "release").write_text(f'JAVA_VERSION="{versi}"\n', encoding="utf-8")
    assert mod.jdk_home([tmp_path]) == tmp_path / "jdk-21.0.14+7"


def test_doctor_tidak_klaim_recon_biner_siap_bila_java_drift(tmp_path, capsys):
    """Provider `ghidra` ok tapi `ghidra-java` gagal → recon-biner WAJIB False."""
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    rea = root / "scripts" / "rea"
    rea.parent.mkdir(parents=True, exist_ok=True)
    rea.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    rea.chmod(0o755)
    mod = load_tool(root)
    payload = {"healthy": False, "scope_checks": [
        {"name": "node", "ok": True, "detail": "v26.13.0"},
        {"name": "ghidra", "ok": True, "detail": "12.1.4"},
        {"name": "ghidra-java", "ok": False, "detail": "config_drift"},
        {"name": "ghidra-headless", "ok": True, "detail": "ok"},
    ]}
    asli = mod.run
    setattr(mod, "run", lambda *a, **k: {"exit": 0, "stdout": json.dumps(payload), "stderr": ""})
    try:
        args = type("A", (), {"json": True, "target": "-"})()
        assert mod.cmd_doctor(args) == 0
    finally:
        setattr(mod, "run", asli)
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"]["native_ready"] is False
    assert out["engines"]["rea"]["blockers"] == ["ghidra-java"]


def test_sha256_tree_deterministik_dan_sensitif_isi(tmp_path):
    """Digest direktori harus sama untuk isi sama (urutan tulis beda) dan beda bila isi beda."""
    mod = load_tool()
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    for d in (a, b, c):
        (d / "functions").mkdir(parents=True)
    (a / "index.json").write_text('{"n":1}', encoding="utf-8")
    (a / "functions" / "f1.c").write_text("int main(void){return 0;}", encoding="utf-8")
    (b / "functions" / "f1.c").write_text("int main(void){return 0;}", encoding="utf-8")
    (b / "index.json").write_text('{"n":1}', encoding="utf-8")
    (c / "index.json").write_text('{"n":2}', encoding="utf-8")
    (c / "functions" / "f1.c").write_text("int main(void){return 0;}", encoding="utf-8")
    assert mod.sha256_tree(a) == mod.sha256_tree(b)
    assert mod.sha256_tree(a) != mod.sha256_tree(c)
    assert mod.tree_bytes(a) == mod.tree_bytes(b) > 0


def test_stamp_artifact_direktori_tidak_null(tmp_path):
    """Artefak direktori (hasil decompile-all) wajib punya sha256 + bytes nyata, bukan null/0."""
    root = fake_repo(tmp_path, {"gate": "gate0", "target": "uji", "verdict": "PASS"})
    dec = root / "evidence" / "uji" / "rea" / "20260101T000000-decompiled"
    (dec / "functions").mkdir(parents=True)
    (dec / "decompile-index.json").write_text("[]", encoding="utf-8")
    (dec / "functions" / "f1.c").write_text("int main(void){return 0;}", encoding="utf-8")
    mod = load_tool(root)
    art = {"op": "decompile-all", "file": "evidence/uji/rea/20260101T000000-decompiled"}
    mod.stamp_artifact(art)
    assert art["sha256"] == mod.sha256_tree(dec)
    assert art["bytes"] == mod.tree_bytes(dec) > 0


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
