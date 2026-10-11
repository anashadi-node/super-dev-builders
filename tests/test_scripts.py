"""Test suite deterministik untuk scripts ekosistem.

Jalankan: /usr/bin/python3 -m pytest tests -q
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


common = load("sdb_common")
gate = load("gate_check")
lint = load("evidence_lint")
release = load("release_check")
registry = load("registry_lint")


# ---------------------------------------------------------------- YAML backend
def test_fallback_yaml_matches_pyyaml_on_repo_files():
    """Parser fallback harus memberi hasil sama dengan PyYAML untuk semua YAML repo.

    Pengecualian: .github/workflows/** — YAML Actions penuh (kunci `on:` adalah
    boolean di YAML 1.1, banyak scalar memakai block scalar), sedangkan parser
    fallback adalah subset by design. Workflow TIDAK dilewati begitu saja: ia tetap
    wajib valid menurut PyYAML (minimal satu diperiksa), dan validitas Actions-nya
    diverifikasi ulang oleh runner GitHub saat push.
    """
    yaml = pytest.importorskip("yaml")
    checked = 0
    workflows = 0
    for base, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
        for fname in files:
            if not fname.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(base, fname)
            rel = os.path.relpath(path, REPO)
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            if rel.replace(os.sep, "/").startswith(".github/workflows/"):
                assert yaml.safe_load(text) is not None, f"workflow YAML tidak valid: {rel}"
                workflows += 1
                continue
            expected = yaml.safe_load(text)
            got = common.fallback_yaml_load(text)
            assert got == expected, f"fallback parser berbeda untuk {rel}"
            checked += 1
    assert checked >= 10, f"hanya {checked} file YAML diperiksa (registry/templates/workflows/agents harus terbaca)"
    assert workflows >= 1, "harus ada minimal satu workflow yang diperiksa validitasnya"


def test_fallback_yaml_block_scalar_matches_pyyaml():
    """Regresi 11 Okt: block scalar (>- , |) dulu menghasilkan '| Mentah' → parser
    fallback berbeda dari PyYAML pada evidence/rt-rw-portal/authorization.yaml."""
    yaml = pytest.importorskip("yaml")
    folded = "notes: >-\n  paragraf satu baris satu\n  lanjutan satu\n\n  paragraf dua\nkey: nilai\n"
    literal = "notes: |\n  satu\n  dua\nkey: nilai\n"
    chomped = "notes: |-\n  satu\n  dua\nkey: nilai\n"
    for text in (folded, literal, chomped):
        assert common.fallback_yaml_load(text) == yaml.safe_load(text)


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
    # Kontrol positif: kedua nilai di bawah SENGAJA tidak nyata — JWT sintetis dan
    # contoh resmi AWS docs (AKIAIOSFODNN7EXAMPLE). Fungsinya menguji detektor itu
    # sendiri, jadi polanya HARUS berbentuk valid agar assert-nya bermakna.
    # nosemgrep: generic.secrets.security.detected-jwt-token.detected-jwt-token
    hits = list(common.scan_for_secrets({"token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdEFGH123"}))
    assert hits, "JWT harus terdeteksi"
    # nosemgrep: generic.secrets.security.detected-aws-access-key-id-value.detected-aws-access-key-id-value
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
    fail, blocked, _ = gate.evaluate(good_manifest())
    assert fail == [] and blocked == [], f"harus PASS, dapat fail={fail} blocked={blocked}"


def test_gate_fails_when_forbidden_actions_incomplete():
    m = good_manifest()
    m["forbidden_actions"] = ["auth_bypass"]
    fail, _, _ = gate.evaluate(m)
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
    code = gate.main(["--manifest", str(manifest), "--quiet", "--out", str(tmp_path / "v1.json")])
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
    assert gate.main(["--manifest", str(manifest), "--quiet", "--out", str(tmp_path / "v2.json")]) == 0


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


def test_evidence_dir_satisfies_contract():
    """Setiap artefak bukti WAJIB punya blok kontrak (provenance/captured_at/...).

    Tanpa tes ini, `evidence_lint` hanya gate manual — dan gate manual pernah
    terlewat saat commit. Fakta ini (bukan niat baik) yang menutup celahnya.
    """
    ev = os.path.join(REPO, "reports", "upgrade-evidence")
    assert lint.main([ev]) == 0, "artefak bukti melanggar kontrak docs/EVIDENCE_SCHEMA.md"


def test_evidence_meta_helper_is_lint_clean():
    """`evidence_meta` = satu-satunya jalan benar untuk 4 kunci kontrak."""
    meta = common.evidence_meta("provenance-uji", captured_at="2026-01-01T00:00:00+0700")
    assert tuple(meta) == common.EVIDENCE_META_KEYS
    assert meta["status"] == "FACT" and meta["redaction_status"] == "clean"
    rec = {"id": "x", **meta}
    errs, warns = [], []
    lint.lint_record(rec, "x[0]", errs, warns)
    assert errs == [], errs


def test_write_evidence_json_wraps_raw_under_contract(tmp_path):
    """Keluaran mentah alat pihak ketiga dititipkan di `raw`, bukan menimpa kontrak.

    Regresi: pernah menulis keluaran mentah semgrep/trivy APA ADANYA ke
    reports/ → 8 ERROR 'metadata wajib hilang' di CI (gerbang evidence pecah).
    """
    out = os.path.join(tmp_path, "tool.json")
    raw = {"results": [{"check_id": "r.a", "level": "ERROR"}]}
    common.write_evidence_json(out, raw, "tool-x 1.0 --scan .", status="FACT")
    obj = json.load(open(out, encoding="utf-8"))
    for key in common.EVIDENCE_META_KEYS:
        assert key in obj, f"kontrak hilang: {key}"
    assert obj["raw"] == raw, "data mentah wajib utuh (nol kehilangan bukti)"
    assert lint.main([out]) == 0, "artefak hasil write_evidence_json wajib lint-clean"

    # kontrol negatif: bentuk mentah langsung = FAIL kontrak (bukti tes berdaya)
    bad = os.path.join(tmp_path, "raw-only.json")
    common.write_json(bad, raw)
    assert lint.main([bad]) == 1, "keluaran mentah apa adanya harus DITOLAK lint"


def test_registry_matches_skill_directories():
    """Registry harus mencerminkan direktori skills/ (invariant, bukan angka mati)."""
    reg = common.load_yaml(os.path.join(REPO, "registry", "skills.yaml"))
    on_disk = {d for d in os.listdir(os.path.join(REPO, "skills"))
               if os.path.isfile(os.path.join(REPO, "skills", d, "SKILL.md"))}
    ids = {item["id"] for item in reg["custom"]}
    assert ids == on_disk, f"selisih registry vs disk: {ids ^ on_disk}"
    assert len(reg["custom"]) >= 21, "jumlah skill tidak boleh menyusut tanpa alasan tercatat"
    for item in reg["custom"]:
        assert os.path.exists(os.path.join(REPO, "skills", item["id"], "SKILL.md")), item["id"]
        assert item["profiles"], f"{item['id']} tanpa profil"


# ------------------------------------------------------------- pipeline E2E (capture/normalize/fidelity)
def _load(name, rel):
    import importlib.util as ilu
    spec = ilu.spec_from_file_location(name, os.path.join(REPO, rel))
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _manifest_t1(tmp_path):
    """Manifest Gate #0 lengkap + disahkan untuk target t1 (allowed http://127.0.0.1:8100)."""
    tgt = tmp_path / "evidence" / "t1"
    tgt.mkdir(parents=True, exist_ok=True)
    (tgt / "authorization.yaml").write_text(
        "schema_version: 2.2\n"
        "target_name: t1\n"
        "mode: A\n"
        "authorization_type: owned\n"
        "license_or_permission_ref: milik sendiri\n"
        "allowed_targets:\n  urls: [\"http://127.0.0.1:8100\"]\n"
        "network_capture_allowed: false\n"
        "deep_analysis_allowed: false\n"
        "forbidden_data: [credentials, session_tokens, cookies, payment_data, private_user_data]\n"
        "forbidden_actions: [auth_bypass, captcha_or_anti_bot_bypass, paywall_bypass, "
        "rate_limit_bypass, drm_or_licensing_bypass, certificate_pinning_bypass, "
        "private_endpoint_bruteforce, hidden_backend_source_extraction]\n"
        "retention:\n  redact_before_prompt: true\n"
        "sandbox:\n"
        "  whole_process_isolation: true\n  non_root: true\n  workspace_only_mounts: true\n"
        "  docker_socket: false\n  host_credentials_mounted: false\n  network_egress: restricted\n"
        "approved_by: \"Mas Anas\"\n"
        "approved_at: \"2026-10-07T11:50:00+07:00\"\n",
        encoding="utf-8")
    return tgt


def test_capture_web_menolak_url_di_luar_scope(tmp_path):
    """Gate #0 PASS, tapi URL di luar allowed_targets -> exit 2, tanpa buka browser."""
    _manifest_t1(tmp_path)
    cap = _load("cap", "scripts/capture_web.py")
    cap.repo_path = lambda *parts: os.path.join(str(tmp_path), *parts)   # sandbox manifest
    rc = cap.main(["--target", "t1", "--url", "https://pihak-lain.example/x", "--out", str(tmp_path / "o")])
    assert rc == 2


def test_capture_web_fail_closed_tanpa_gate0_pass(tmp_path):
    """Aturan #1: manifest belum disahkan (approved_by kosong) -> capture DITOLAK lebih dulu.

    Sebelum audit 2026-10-07, capture_web hanya mencocokkan daftar URL dan tidak pernah
    memanggil Gate #0, jadi manifest tanpa pengesahan pun tetap bisa membuka browser.
    """
    tgt = tmp_path / "evidence" / "t1"
    tgt.mkdir(parents=True)
    (tgt / "authorization.yaml").write_text(
        "target_name: t1\nallowed_targets:\n  urls: [\"http://127.0.0.1:8100\"]\n", encoding="utf-8")
    cap = _load("cap2", "scripts/capture_web.py")
    cap.repo_path = lambda *parts: os.path.join(str(tmp_path), *parts)
    rc_gate = cap.gate0_or_die("t1")
    assert rc_gate in (1, 2), f"manifest belum disahkan harus ditolak (dapat {rc_gate})"
    rc = cap.main(["--target", "t1", "--url", "http://127.0.0.1:8100/", "--out", str(tmp_path / "o")])
    assert rc in (1, 2), "capture harus dibatalkan sebelum menyentuh jaringan"


def test_capture_web_gate0_lolos_dengan_manifest_lengkap(tmp_path):
    _manifest_t1(tmp_path)
    cap = _load("cap3", "scripts/capture_web.py")
    cap.repo_path = lambda *parts: os.path.join(str(tmp_path), *parts)
    assert cap.gate0_or_die("t1", quiet=True) == 0


def test_fidelity_compare_butuh_input(tmp_path, capsys):
    mod = _load("fd", "scripts/fidelity_compare.py")
    assert mod.main(["--target", "x", "--original", str(tmp_path / "a"), "--rebuilt", str(tmp_path / "b")]) == 2


def test_normalize_butuh_artefak_capture(tmp_path):
    mod = _load("nz", "scripts/normalize_capture.py")
    assert mod.main(["--target", "x", "--capture", str(tmp_path / "kosong")]) == 2


def test_fidelity_report_menolak_tanpa_coverage(tmp_path):
    mod = _load("fr2", "scripts/fidelity_report.py")
    js = tmp_path / "fidelity.json"
    common.write_json(str(js), [{"dimension": "visual", "status": "ok"}])
    assert mod.main(["--target", "x", "--json", str(js), "--out", str(tmp_path / "r.md")]) == 0
    body = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "NOT_MEASURED" in body  # dimensi lain wajib eksplisit belum diukur


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
        # workdir run 16-tahap + root implementasi harus ikut dibuat,
        # supaya `sdb workflow <slug>` tidak menolak target yang baru di-init.
        assert os.path.isdir(os.path.join(REPO, "runs", slug, "reports"))
        assert os.path.isdir(os.path.join(REPO, "targets", slug, "src"))
    finally:
        import shutil
        for tree in ("evidence", "normalized", "reconstruction", "verification",
                     "reports", "runs", "targets"):
            shutil.rmtree(os.path.join(REPO, tree, slug), ignore_errors=True)
