#!/usr/bin/python3
"""Gate #0 — Authorization & Scope Gate (workflows/gate0.yaml).

Pemakaian:
    /usr/bin/python3 scripts/gate_check.py --target <slug>
    /usr/bin/python3 scripts/gate_check.py --manifest path/to/authorization.yaml

Exit code: 0 = PASS, 1 = FAIL, 2 = BLOCKED.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import load_yaml, now_iso, repo_path, write_json  # noqa: E402

CORE_FORBIDDEN = {
    "auth_bypass",
    "captcha_or_anti_bot_bypass",
    "paywall_bypass",
    "rate_limit_bypass",
    "drm_or_licensing_bypass",
    "certificate_pinning_bypass",
    "private_endpoint_bruteforce",
    "hidden_backend_source_extraction",
}
CORE_FORBIDDEN_DATA = {"credentials", "session_tokens", "cookies", "payment_data", "private_user_data"}
VALID_AUTH_TYPES = {"owned", "open_source", "staging", "written_permission"}


def as_text(value) -> str:
    """Normalisasi YAML scalar (str/datetime/int/None) menjadi teks aman."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return str(iso()).strip()
    return str(value).strip()


def evaluate(manifest: dict):
    fail, blocked, warn = [], [], []
    if not isinstance(manifest, dict):
        return ["manifest bukan mapping YAML"], [], []

    def get(key, default=None):
        return manifest.get(key, default)

    name = as_text(get("target_name"))
    if not name:
        fail.append("target_name kosong")
    elif name != name.lower() or " " in name:
        warn.append(f"target_name '{name}' sebaiknya slug lowercase tanpa spasi")

    auth_type = as_text(get("authorization_type"))
    if auth_type not in VALID_AUTH_TYPES:
        fail.append(f"authorization_type tidak valid: '{auth_type}' (pilih: {sorted(VALID_AUTH_TYPES)})")

    mode = as_text(get("mode")) or "A"
    if mode not in ("A", "B"):
        fail.append(f"mode harus 'A' atau 'B' (dapat '{mode}')")

    if auth_type == "written_permission" and not as_text(get("license_or_permission_ref")):
        fail.append("authorization_type=written_permission wajib mengisi license_or_permission_ref")
    if auth_type in ("owned", "open_source", "staging") and not as_text(get("license_or_permission_ref")):
        warn.append("license_or_permission_ref kosong (sebaiknya diisi: lisensi/ref kepemilikan)")

    targets = get("allowed_targets") or {}
    if not isinstance(targets, dict):
        fail.append("allowed_targets harus mapping")
        targets = {}
    total_targets = sum(len(v) for v in targets.values() if isinstance(v, list))
    if total_targets == 0:
        fail.append("allowed_targets kosong (minimal satu url/repo/app)")

    deep = bool(get("deep_analysis_allowed"))
    binaries = targets.get("apk_ipa_binaries") or []
    if mode == "A":
        if deep:
            blocked.append("mode A tidak boleh deep_analysis_allowed=true (butuh izin tertulis -> mode B)")
        if binaries:
            blocked.append("mode A tidak boleh memuat apk_ipa_binaries")
    if mode == "B":
        if auth_type != "written_permission":
            blocked.append("mode B wajib authorization_type=written_permission")
        if not deep:
            warn.append("mode B tetapi deep_analysis_allowed=false")

    if get("network_capture_allowed") is None:
        warn.append("network_capture_allowed belum diisi (eksplisit true/false lebih baik)")

    forbidden = set(get("forbidden_actions") or [])
    missing_forbidden = CORE_FORBIDDEN - forbidden
    if missing_forbidden:
        fail.append(f"forbidden_actions kurang: {sorted(missing_forbidden)}")

    fb_data = set(get("forbidden_data") or [])
    missing_data = CORE_FORBIDDEN_DATA - fb_data
    if missing_data:
        fail.append(f"forbidden_data kurang: {sorted(missing_data)}")

    retention = get("retention") or {}
    if not isinstance(retention, dict) or not retention.get("redact_before_prompt"):
        fail.append("retention.redact_before_prompt wajib true")

    sandbox = get("sandbox") or {}
    if not isinstance(sandbox, dict):
        fail.append("sandbox harus mapping")
        sandbox = {}
    if not sandbox.get("whole_process_isolation"):
        fail.append("sandbox.whole_process_isolation wajib true (terminal sandbox bukan containment)")
    if not sandbox.get("non_root"):
        fail.append("sandbox.non_root wajib true")
    if not sandbox.get("workspace_only_mounts"):
        fail.append("sandbox.workspace_only_mounts wajib true")
    if sandbox.get("docker_socket"):
        fail.append("sandbox.docker_socket wajib false")
    if sandbox.get("host_credentials_mounted"):
        fail.append("sandbox.host_credentials_mounted wajib false")
    if not sandbox.get("network_egress"):
        warn.append("sandbox.network_egress sebaiknya 'restricted'")

    if not as_text(get("approved_by")):
        blocked.append("approved_by kosong — butuh orang yang mengesahkan (keputusan manusia)")
    if not as_text(get("approved_at")):
        blocked.append("approved_at kosong — butuh timestamp persetujuan")

    return fail, blocked, warn


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gate #0 authorization & scope gate")
    ap.add_argument("--target", help="slug target (membaca evidence/<slug>/authorization.yaml)")
    ap.add_argument("--manifest", help="path authorization manifest langsung")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--out", help="tulis verdict ke path ini (default: reports/<target>/gate0-verdict.json)")
    args = ap.parse_args(argv)

    if not args.target and not args.manifest:
        ap.error("butuh --target atau --manifest")
    manifest_path = args.manifest or repo_path("evidence", args.target, "authorization.yaml")
    if not os.path.exists(manifest_path):
        result = {
            "gate": "gate0",
            "verdict": "BLOCKED",
            "checked_at": now_iso(),
            "manifest": manifest_path,
            "fail": [],
            "blocked": [f"manifest tidak ditemukan: {manifest_path}"],
            "warn": ["jalankan scripts/init_target.py <slug> lalu isi manifest"],
        }
    else:
        try:
            manifest = load_yaml(manifest_path)
        except Exception as exc:  # noqa: BLE001
            manifest = None
            result = {
                "gate": "gate0",
                "verdict": "FAIL",
                "checked_at": now_iso(),
                "manifest": manifest_path,
                "fail": [f"gagal parse manifest: {exc}"],
                "blocked": [],
                "warn": [],
            }
        else:
            fail, blocked, warn = evaluate(manifest)
            verdict = "PASS" if not fail and not blocked else ("BLOCKED" if blocked and not fail else "FAIL")
            if fail and blocked:
                verdict = "FAIL"
            result = {
                "gate": "gate0",
                "verdict": verdict,
                "checked_at": now_iso(),
                "manifest": manifest_path,
                "target": (manifest or {}).get("target_name"),
                "mode": (manifest or {}).get("mode"),
                "fail": fail,
                "blocked": blocked,
                "warn": warn,
            }

    slug = args.target or (result.get("target") or "unknown")
    out_path = args.out or repo_path("reports", str(slug), "gate0-verdict.json")
    write_json(out_path, result)

    if not args.quiet:
        print(f"Gate #0 verdict: {result['verdict']}  ({out_path})")
        for label, items in (("FAIL", result["fail"]), ("BLOCKED", result["blocked"]), ("WARN", result["warn"])):
            for item in items:
                print(f"  {label}: {item}")
        if result["verdict"] == "PASS":
            print("  lanjut: capture Mode A diizinkan (scope sesuai manifest)")
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
