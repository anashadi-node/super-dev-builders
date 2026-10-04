"""Test suite deterministik untuk scripts ekosistem.

Jalankan: /usr/bin/python3 -m pytest tests -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


common = load("sdb_common")
gate = load("gate_check")
lint = load("evidence_lint")
release = load("release_check")
registry = load("registry_lint")


# ---------------------------------------------------------------- YAML backend
def test_fallback_yaml_matches_pyyaml_on_repo_files():
    """Parser fallback harus memberi hasil sama dengan PyYAML untuk semua YAML repo."""
    yaml = pytest.importorskip("yaml")
    checked = 0
    for base, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
        for fname in files:
            if not fname.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(base, fname)
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            expected = yaml.safe_load(text)
            got = common.fallback_yaml_load(text)
            assert got == expected, f"fallback parser berbeda untuk {os.path.relpath(path, REPO)}"
            checked += 1
    assert checked >= 10, f"hanya {checked} file YAML diperiksa (registry/templates/workflows/agents harus terbaca)"


def test_redaction_removes_secret_keys_and_values():
    payload = {
        "headers": {"Authorization": "Bearer abcdef1234567890", "Cookie": "session=xyz",
                    "Accept": "application/json"},
        "body": {"email": "user@example.com", "note": "ok"},
    }
    keys, values = [], []
    clean = common.redact_obj(payload, keys, values)
    assert clean["headers"]["Authorization"] == common.REDACTED
    assert clean["headers"]["Cookie"] == common.REDACTED
    assert clean["headers"]["Accept"] == "application/json"
    assert common.REDACTED in clean["body"]["email"]
    assert "Authorization" in keys and "Cookie" in keys
    assert list(common.scan_for_secrets(clean)) == [], "hasil redaksi masih terdeteksi rahasia"


def test_scan_for_secrets_detects_jwt_and_aws_key():
    hits = list(common.scan_for_secrets({"token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdEFGH123"}))
    assert hits, "JWT harus terdeteksi"
    hits2 = list(common.scan_for_secrets({"aws": "AKIAIOSFODNN7EXAMPLE"}))
    assert hits2, "AWS access key harus terdeteksi"


# ------------------------------------------------------------------ Gate #0
def good_manifest(**over):
    base = {
        "schema_version": 2.2,
        "target_name": "example-target",
        "mode": "A",
        "owner_or_authorizer": "mas anas",
        "authorization_type": "owned",
        "license_or_permission_ref": "internal-asset-2026",
        "allowed_targets": {"urls": ["https://example.test"], "repos": [], "apps": [], "apk_ipa_binaries": []},
        "network_capture_allowed": True,
        "deep_analysis_allowed": False,
        "forbidden_data": ["credentials", "session_tokens", "cookies", "payment_data", "private_user_data"],
        "forbidden_actions": sorted(gate.CORE_FORBIDDEN),
        "retention": {"raw_evidence_days": 30, "redact_before_prompt": True},
        "sandbox": {"whole_process_isolation": True, "non_root": True, "workspace_only_mounts": True,
                    "network_egress": "restricted", "docker_socket": False, "host_credentials_mounted": False},
        "approved_by": "mas anas",
        "approved_at": "2026-10-04T08:00:00+07:00",
    }
    base.update(over)
    return base


def test_gate_pass_on_complete_manifest():
    fail, blocked, warn = gate.evaluate(good_manifest())
    assert fail == [] and blocked == [], f"harus PASS, dapat fail={fail} blocked={blocked}"


def test_gate_fails_when_forbidden_actions_incomplete():
    m = good_manifest()
    m["forbidden_actions"] = ["auth_bypass"]
    fail, blocked, _ = gate.evaluate(m)
    assert any("forbidden_actions kurang" in f for f in fail)


def test_gate_fails_when_sandbox_unsafe():
    m = good_manifest()
    m["sandbox"]["docker_socket"] = True
    m["sandbox"]["host_credentials_mounted"] = True
    fail, _, _ = gate.evaluate(m)
    assert any("docker_socket" in f for f in fail)
    assert any("host_credentials_mounted" in f for f in fail)


def test_gate_blocked_mode_b_without_written_permission():
    m = good_manifest(mode="B", deep_analysis_allowed=True)
    fail, blocked, _ = gate.evaluate(m)
    assert any("written_permission" in b for b in blocked)
    assert not fail, "bentuk manifest valid: seharusnya BLOCKED, bukan FAIL"


def test_gate_blocked_mode_a_with_deep_analysis():
    m = good_manifest(mode="A", deep_analysis_allowed=True)
    _, blocked, _ = gate.evaluate(m)
    assert any("mode A" in b for b in blocked)


def test_gate_blocked_without_human_approval():
    m = good_manifest(approved_by="", approved_at="")
    _, blocked, _ = gate.evaluate(m)
    assert any("approved_by" in b for b in blocked)
    assert any("approved_at" in b for b in blocked)


def test_gate_main_exit_codes(tmp_path):
    manifest = tmp_path / "authorization.yaml"
    manifest.write_text(
        "target_name: exitcode-test\nmode: A\nauthorization_type: owned\n"
        "allowed_targets: {urls: [https://x.test]}\nforbidden_actions: [auth_bypass]\n"
        "retention: {redact_before_prompt: true}\n"
        "sandbox: {whole_process_isolation: true, non_root: true, workspace_only_mounts: true,"
        " docker_socket: false, host_credentials_mounted: false}\n"
        "approved_by: tester\napproved_at: 2026-10-04T00:00:00+07:00\n",
        encoding="utf-8")
    code = gate.main(["--manifest", str(manifest), "--quiet"])
    assert code == 1, "manifest tidak lengkap harus FAIL (exit 1)"
    manifest.write_text(
        "target_name: exitcode-test\nmode: A\nauthorization_type: owned\n"
        "license_or_permission_ref: own\n"
        "allowed_targets: {urls: [https://x.test]}\n"
        f"forbidden_actions: {sorted(gate.CORE_FORBIDDEN)}\n"
        f"forbidden_data: {sorted(gate.CORE_FORBIDDEN_DATA)}\n"
        "retention: {redact_before_prompt: true}\n"
        "sandbox: {whole_process_isolation: true, non_root: true, workspace_only_mounts: true,"
        " network_egress: restricted, docker_socket: false, host_credentials_mounted: false}\n"
        "approved_by: tester\napproved_at: 2026-10-04T00:00:00+07:00\n",
        encoding="utf-8")
    assert gate.main(["--manifest", str(manifest), "--quiet"]) == 0


# --------------------------------------------------------------- evidence lint
def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_evidence_lint_passes_clean_records(tmp_path):
    write_json(tmp_path / "screens.json", [{
        "id": "home", "url": "/", "screenshot": "evidence/x/home.png",
        "provenance": "run-1", "captured_at": "2026-10-04T09:00:00+07:00",
        "redaction_status": "clean", "status": "FACT",
    }])
    assert lint.main([str(tmp_path)]) == 0


def test_evidence_lint_flags_missing_metadata_and_inferred_confidence(tmp_path):
    write_json(tmp_path / "network.json", [
        {"id": "x", "status": "INFERRED"},
        {"id": "y", "provenance": "run-1", "captured_at": "t", "redaction_status": "clean", "status": "FACT"},
    ])
    assert lint.main([str(tmp_path)]) == 1


def test_evidence_lint_flags_unredacted_secret(tmp_path):
    write_json(tmp_path / "network.json", [{
        "id": "x", "provenance": "run-1", "captured_at": "t", "redaction_status": "clean", "status": "FACT",
        "headers": {"Authorization": "Bearer abc123def456ghi789"},
    }])
    assert lint.main([str(tmp_path)]) == 1


# --------------------------------------------------------------- release gate
def test_release_gate_fails_without_artifacts(tmp_path):
    assert release.main(["--project", str(tmp_path), "--out", str(tmp_path / "verdict.json")]) == 1
    verdict = json.loads((tmp_path / "verdict.json").read_text())
    assert verdict["verdict"] == "FAIL" and len(verdict["failures"]) >= 5


def test_release_gate_passes_with_fresh_artifacts(tmp_path):
    for rel in ["requirements.md", "logs/build-1.log", "logs/tests-1.log", "reports/review-1.md",
                "reports/security-gate.md", "reports/assurance-audit.md", "reports/handover-1.md"]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("artifact", encoding="utf-8")
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "README-x.md").write_text("readme", encoding="utf-8")
    assert release.main(["--project", str(tmp_path), "--out", str(tmp_path / "verdict.json")]) == 0


# ------------------------------------------------------------- registry lint
def test_registry_lint_passes_on_repo():
    assert registry.main() == 0, "registry + frontmatter skill harus konsisten"


def test_registry_has_21_custom_skills():
    reg = common.load_yaml(os.path.join(REPO, "registry", "skills.yaml"))
    assert len(reg["custom"]) == 21
    for item in reg["custom"]:
        assert os.path.exists(os.path.join(REPO, "skills", item["id"], "SKILL.md")), item["id"]
        assert item["profiles"], f"{item['id']} tanpa profil"


# ------------------------------------------------------------- misc scripts
def test_fidelity_report_flags_low_coverage(tmp_path):
    import importlib.util as ilu
    spec = ilu.spec_from_file_location("fidelity", os.path.join(SCRIPTS, "fidelity_report.py"))
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    payload = [{"dimension": "visual", "status": "ok", "coverage": 0.3, "evidence": "x.png"}]
    src = tmp_path / "fidelity.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "report.md"
    assert mod.main(["--target", "selftest", "--json", str(src), "--out", str(out)]) == 0
    text = out.read_text()
    assert "coverage rendah" in text and "NOT_MEASURED" in text


def test_fidelity_report_missing_input_returns_2(tmp_path):
    import importlib.util as ilu
    spec = ilu.spec_from_file_location("fidelity2", os.path.join(SCRIPTS, "fidelity_report.py"))
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--target", "tidak-ada", "--json", str(tmp_path / "nope.json"),
                     "--out", str(tmp_path / "o.md")]) == 2


def test_install_skills_list_and_dry_run(capsys):
    import importlib.util as ilu
    spec = ilu.spec_from_file_location("installer", os.path.join(SCRIPTS, "install_skills.py"))
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--list"]) == 0
    capsys.readouterr()
    assert mod.main(["--profile", "sdb-builder", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "api-contract" in out or "database-migration-safety" in out


def test_init_target_creates_workspace_and_is_idempotent():
    import importlib.util as ilu
    spec = ilu.spec_from_file_location("init_target", os.path.join(SCRIPTS, "init_target.py"))
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    slug = "_selftest_init"
    try:
        assert mod.main([slug]) == 0
        assert mod.main([slug]) == 0
        base = os.path.join(REPO, "evidence", slug)
        assert os.path.exists(os.path.join(base, "authorization.yaml"))
        assert os.path.exists(os.path.join(base, "workspace.json"))
    finally:
        import shutil
        shutil.rmtree(os.path.join(REPO, "evidence", slug), ignore_errors=True)
        shutil.rmtree(os.path.join(REPO, "normalized", slug), ignore_errors=True)
        shutil.rmtree(os.path.join(REPO, "reconstruction", slug), ignore_errors=True)
        shutil.rmtree(os.path.join(REPO, "verification", slug), ignore_errors=True)
        shutil.rmtree(os.path.join(REPO, "reports", slug), ignore_errors=True)
