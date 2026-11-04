"""Gate #0 — uji negatif: gate keamanan harus MENOLAK, bukan hanya ada.

Bug yang dicegah di sini (audit 2026-10-07): YAML tulis-tangan menulis "false"
dengan kutip. Python menilainya truthy, jadi `redact_before_prompt: "false"` LOLOS
gate dan `docker_socket: "false"` justru diblokir — keduanya terbalik.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from gate_check import as_bool, evaluate


def _base(**over):
    """Manifest Mode A yang jujur dan lolos gate."""
    m = {
        "target_name": "uji",
        "authorization_type": "owned",
        "mode": "A",
        "license_or_permission_ref": "milik sendiri",
        "allowed_targets": {"web_urls": ["https://example.invalid"]},
        "approved_by": "Mas Anas",
        "approved_at": "2026-10-07T11:40:00+07:00",
        "forbidden_actions": [
            "auth_bypass", "captcha_or_anti_bot_bypass", "paywall_bypass",
            "rate_limit_bypass", "drm_or_licensing_bypass", "certificate_pinning_bypass",
            "private_endpoint_bruteforce", "hidden_backend_source_extraction",
        ],
        "forbidden_data": ["credentials", "session_tokens", "cookies", "payment_data", "private_user_data"],
        "retention": {"redact_before_prompt": True},
        "sandbox": {
            "whole_process_isolation": True,
            "non_root": True,
            "workspace_only_mounts": True,
            "docker_socket": False,
            "host_credentials_mounted": False,
            "network_egress": "restricted",
        },
    }
    m.update(over)
    return m


def test_baseline_manifest_passes():
    fail, blocked, _ = evaluate(_base())
    assert fail == [] and blocked == [], f"baseline harus PASS, dapat fail={fail} blocked={blocked}"


def _mode_b(**over):
    """Manifest mode B (analisis mendalam) dengan biner milik sendiri."""
    m = _base(mode="B", deep_analysis_allowed=True,
              allowed_targets={"apk_ipa_binaries": ["~/super-dev-builders/targets/uji"]})
    m.update(over)
    return m


def test_mode_b_owned_lolos_bila_operator_cocok():
    """Keputusan Owner 2026-11-04: milik sendiri = izinnya kepemilikan, bukan surat pihak ketiga."""
    import getpass
    fail, blocked, _ = evaluate(_mode_b(owner_operator=getpass.getuser()))
    assert fail == [] and blocked == [], f"dapat fail={fail} blocked={blocked}"


def test_mode_b_owned_tanpa_owner_operator_ditolak():
    fail, blocked, _ = evaluate(_mode_b())
    assert not fail
    assert any("owner_operator" in b for b in blocked), blocked


def test_mode_b_owned_operator_berbeda_ditolak():
    """Kalau siapa pun bisa menulis 'owned', gerbang ini tidak menjaga apa pun."""
    fail, blocked, _ = evaluate(_mode_b(owner_operator="orang-lain"))
    assert not fail
    assert any("hanya untuk pemilik" in b for b in blocked), blocked


def test_mode_b_staging_tetap_ditolak():
    fail, blocked, _ = evaluate(_mode_b(authorization_type="staging", owner_operator="siapa-saja"))
    assert not fail
    assert any("written_permission atau owned" in b for b in blocked), blocked


def test_mode_b_written_permission_masih_lolos():
    fail, blocked, _ = evaluate(_mode_b(authorization_type="written_permission"))
    assert fail == [] and blocked == [], f"dapat fail={fail} blocked={blocked}"


def test_as_bool_parses_quoted_strings():
    assert as_bool("false")[0] is False
    assert as_bool("true")[0] is True
    assert as_bool(False)[0] is False
    assert as_bool("maybe")[1] is not None, "nilai non-boolean harus jadi error, bukan diam"


def test_quoted_false_in_redact_is_rejected():
    """'false' (kutip) dulu truthy -> gate lolos. Sekarang harus FAIL."""
    fail, _, _ = evaluate(_base(retention={"redact_before_prompt": "false"}))
    assert any("redact_before_prompt" in f for f in fail), fail


def test_quoted_true_in_docker_socket_is_rejected():
    """'true' (kutip) dulu truthy -> FAIL; pastikan tetap FAIL dan pesannya benar."""
    m = _base()
    m["sandbox"] = {**m["sandbox"], "docker_socket": "true"}
    fail, _, _ = evaluate(m)
    assert "sandbox.docker_socket wajib false" in fail, fail


def test_missing_optional_false_fields_is_ok():
    """docker_socket/host_credentials_mounted tidak ada = default false, bukan FAIL."""
    m = _base()
    m["sandbox"] = {k: v for k, v in m["sandbox"].items()
                    if k not in ("docker_socket", "host_credentials_mounted")}
    fail, _, _ = evaluate(m)
    assert not any("docker_socket" in f or "host_credentials_mounted" in f for f in fail), fail


def test_deep_in_mode_a_is_blocked():
    _fail, blocked, _ = evaluate(_base(deep_analysis_allowed=True))
    assert any("mode A" in b for b in blocked), blocked


def test_missing_approval_is_blocked():
    m = _base()
    m.pop("approved_by")
    m.pop("approved_at")
    _fail, blocked, _ = evaluate(m)
    assert len(blocked) == 2, blocked


def test_missing_forbidden_actions_fails():
    m = _base(forbidden_actions=["auth_bypass"])
    fail, _, _ = evaluate(m)
    assert any("forbidden_actions kurang" in f for f in fail), fail

def test_allowed_urls_accepts_both_key_names():
    """Template memakai 'urls', capture_web dulu membaca 'web_urls' -> izin selalu kosong."""
    from gate_check import allowed_urls, count_allowed
    assert allowed_urls({"urls": ["https://a.example"]}) == ["https://a.example"]
    assert allowed_urls({"web_urls": ["https://b.example"]}) == ["https://b.example"]
    assert allowed_urls({"urls": ["https://a.example"], "web_urls": ["https://b.example"]}) == \
        ["https://a.example", "https://b.example"]
    assert count_allowed({"urls": ["https://a.example"], "repos": ["r/x"]}) == 2


def test_template_manifest_key_matches_capture_reader():
    """Regresi lintas berkas: kunci di templates/ harus terbaca oleh gate maupun capture."""
    import tomllib  # noqa: F401  (hanya memastikan stdlib ada)
    import yaml
    from doctor import repo_path
    from gate_check import allowed_urls, count_allowed
    tmpl = yaml.safe_load(open(repo_path("templates", "authorization_manifest.yaml")))
    assert count_allowed(tmpl["allowed_targets"]) == 0, "template default memang kosong"
    assert "urls" in tmpl["allowed_targets"]
    m = _base()
    m["allowed_targets"] = {"urls": ["https://contoh.example"]}
    assert allowed_urls(m["allowed_targets"]) == ["https://contoh.example"]
