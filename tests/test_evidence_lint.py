"""Aturan #3: tidak ada credential/token/PII di evidence — diuji dengan canary.

Nilai rahasia dibangkitkan di dalam test (bukan ditulis di berkas) supaya
repo sendiri tidak memuat string yang tampak seperti token nyata.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from evidence_lint import lint_record


def _rec(**over):
    r = {"kind": "network", "provenance": "capture", "captured_at": "2026-10-07T11:00:00+07:00",
         "redaction_status": "redacted", "status": "OBSERVED"}
    r.update(over)
    return r


def test_clean_record_has_no_errors():
    errors, warnings = [], []
    lint_record(_rec(), "r[0]", errors, warnings)
    assert errors == [], errors


def test_github_token_value_is_flagged():
    token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"[:36]
    errors, _ = [], []
    lint_record(_rec(**{"note": f"header={token}"}), "r[0]", errors, [])
    assert any("rahasia belum diredaksi" in e for e in errors), errors


def test_bearer_token_value_is_flagged():
    errors = []
    lint_record(_rec(**{"note": "Authorization: Bearer abcdef123456.ghijkl"}), "r[0]", errors, [])
    assert any("rahasia belum diredaksi" in e for e in errors), errors


def test_secret_key_name_is_flagged_even_with_plain_value():
    """Token di bawah kunci bernama 'token'/'cookie'/'password' harus ketahuan."""
    errors = []
    lint_record(_rec(**{"cookie": "sesi=abc"}), "r[0]", errors, [])
    assert any("rahasia belum diredaksi" in e for e in errors), errors


def test_missing_required_metadata_is_an_error():
    errors = []
    bad = _rec()
    bad.pop("redaction_status")
    lint_record(bad, "r[0]", errors, [])
    assert any("metadata wajib hilang: redaction_status" in e for e in errors), errors


def test_inferred_requires_numeric_confidence():
    errors = []
    lint_record(_rec(status="INFERRED"), "r[0]", errors, [])
    assert any("confidence" in e for e in errors), errors
    errors = []
    lint_record(_rec(status="INFERRED", confidence=80), "r[0]", errors, [])
    assert errors == [], errors


def test_unknown_must_not_carry_guesses():
    errors = []
    lint_record(_rec(status="UNKNOWN", guess="mungkin pakai Next.js"), "r[0]", errors, [])
    assert any("dugaan" in e for e in errors), errors


def test_lint_record_is_serialisable(tmp_path):
    """Sanity: record hasil lint tetap JSON-valid (dipakai pipeline lain)."""
    p = tmp_path / "r.json"
    p.write_text(json.dumps([_rec()]))
    assert json.loads(p.read_text())[0]["kind"] == "network"
