#!/usr/bin/python3
"""Gate #0 — Authorization & Scope Gate (workflows/gate0.yaml).

Pemakaian:
    /usr/bin/python3 scripts/gate_check.py --target <slug>
    /usr/bin/python3 scripts/gate_check.py --manifest path/to/authorization.yaml

Exit code: 0 = PASS, 1 = FAIL, 2 = BLOCKED.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import load_yaml, now_iso, repo_path, validate_slug, write_json

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


def allowed_urls(allowed_targets) -> list[str]:
    """Semua URL yang diizinkan dari manifest — semua nama kunci yang berbeda.

    Bug nyata (audit 2026-10-07): template menulis `allowed_targets.urls` sementara
    capture_web.py membaca `allowed_targets.web_urls`, sehingga daftar izin selalu
    kosong dan capture ditolak untuk semua URL. Fungsi ini jadi satu sumber kebenaran.
    """
    if not isinstance(allowed_targets, dict):
        return []
    out = []
    for key in ("urls", "web_urls"):
        vals = allowed_targets.get(key)
        if isinstance(vals, list):
            out += [as_text(v) for v in vals if as_text(v)]
    return out


def count_allowed(allowed_targets) -> int:
    """Jumlah target yang diizinkan lintas semua nama kunci (urls/web_urls dan lainnya)."""
    if not isinstance(allowed_targets, dict):
        return 0
    n = len(allowed_urls(allowed_targets))
    for key in ("repos", "apps", "apk_ipa_binaries"):
        vals = allowed_targets.get(key)
        if isinstance(vals, list):
            n += len([v for v in vals if as_text(v)])
    return n


def as_bool(value):
    """Kembalikan (bool|None, error|None).

    YAML tulis-tangan sering memberi string "false"/"true" (kutip). Python menilainya
    TRUTHY, sehingga `redact_before_prompt: "false"` lolos gate dan `docker_socket:
    "false"` malah diblokir — keduanya terbalik. Field keamanan wajib boolean tegas.
    """
    if isinstance(value, bool):
        return value, None
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes", "on", "1"):
            return True, None
        if low in ("false", "no", "off", "0"):
            return False, None
    return None, f"nilai bukan boolean tegas: {value!r}"


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


def operator_of_manifest(manifest) -> str:
    """Nama operator (akun OS) yang dipakai untuk mengesahkan `owned` mode B.

    Keputusan Owner 2026-11-04: artefak milik sendiri boleh dianalisis mendalam tanpa
    surat izin pihak ketiga — tetapi hanya oleh pemiliknya. Karena itu manifest wajib
    menyebut `owner_operator` secara mesin-terbaca (nama akun OS), bukan prosa bebas:
    mencocokkan teks seperti "Mas Anas (pemilik)" ke nama akun akan menjadi tebakan.
    """
    return as_text((manifest or {}).get("owner_operator")).lower()


def current_operator() -> str:
    try:
        return getpass.getuser().strip().lower()
    except (KeyError, OSError):
        return as_text(os.environ.get("USER")).lower()


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
    total_targets = count_allowed(targets)
    if total_targets == 0:
        fail.append("allowed_targets kosong (minimal satu url/repo/app)")

    raw_deep = get("deep_analysis_allowed")
    deep, err = (False, None) if raw_deep is None else as_bool(raw_deep)
    if err:
        fail.append(f"deep_analysis_allowed: {err}")
    binaries = targets.get("apk_ipa_binaries") or []
    if mode == "A":
        if deep:
            blocked.append("mode A tidak boleh deep_analysis_allowed=true (butuh izin tertulis -> mode B)")
        if binaries:
            blocked.append("mode A tidak boleh memuat apk_ipa_binaries")
    if mode == "B":
        if auth_type == "written_permission":
            pass
        elif auth_type == "owned":
            # Artefak milik sendiri: izinnya adalah kepemilikan, tapi harus dibuktikan
            # bahwa yang menjalankan gerbang memang pemiliknya (akun OS), bukan sekadar
            # tulisan "owned" di manifest.
            operator = operator_of_manifest(manifest)
            if not operator:
                blocked.append(
                    "mode B + owned wajib mengisi owner_operator (nama akun OS pemilik) — "
                    "tanpa itu gerbang tidak bisa membedakan pemilik dari penyusup")
            elif operator != current_operator():
                blocked.append(
                    f"mode B + owned hanya untuk pemilik: owner_operator '{operator}' "
                    f"tidak sama dengan operator saat ini '{current_operator()}'")
        else:
            blocked.append(
                "mode B wajib authorization_type=written_permission atau owned "
                f"(dapat '{auth_type}')")
        if not deep:
            warn.append("mode B tetapi deep_analysis_allowed=false")

    if get("network_capture_allowed") is None:
        warn.append("network_capture_allowed belum diisi (eksplisit true/false lebih baik)")
    else:
        _, err = as_bool(get("network_capture_allowed"))
        if err:
            fail.append(f"network_capture_allowed: {err}")

    forbidden = set(get("forbidden_actions") or [])
    missing_forbidden = CORE_FORBIDDEN - forbidden
    if missing_forbidden:
        fail.append(f"forbidden_actions kurang: {sorted(missing_forbidden)}")

    fb_data = set(get("forbidden_data") or [])
    missing_data = CORE_FORBIDDEN_DATA - fb_data
    if missing_data:
        fail.append(f"forbidden_data kurang: {sorted(missing_data)}")

    retention = get("retention") or {}
    if not isinstance(retention, dict):
        fail.append("retention harus mapping")
        retention = {}
    redact, err = as_bool(retention.get("redact_before_prompt"))
    if err:
        fail.append(f"retention.redact_before_prompt: {err}")
    elif redact is not True:
        fail.append("retention.redact_before_prompt wajib true")

    sandbox = get("sandbox") or {}
    if not isinstance(sandbox, dict):
        fail.append("sandbox harus mapping")
        sandbox = {}

    def sb(key, want: bool, must: bool = True):
        """want = nilai wajib. must=True -> salah tipe/missing = FAIL, nilai lawan = FAIL.
        must=False -> hanya 'true' tegas yang FAIL (field opsional, bawaannya false)."""
        raw = sandbox.get(key)
        if raw is None:
            if must:
                fail.append(f"sandbox.{key} wajib diisi")
            return
        val, err = as_bool(raw)
        if err:
            fail.append(f"sandbox.{key}: {err}")
        elif val is not want:
            fail.append(f"sandbox.{key} wajib {str(want).lower()}")

    sb("whole_process_isolation", True)
    sb("non_root", True)
    sb("workspace_only_mounts", True)
    sb("docker_socket", False, must=False)
    sb("host_credentials_mounted", False, must=False)
    if sandbox.get("network_egress") and as_text(sandbox.get("network_egress")) != "restricted":
        warn.append(f"sandbox.network_egress '{sandbox.get('network_egress')}' (disarankan 'restricted')")

    if not as_text(get("approved_by")):
        blocked.append("approved_by kosong — butuh orang yang mengesahkan (keputusan manusia)")
    if not as_text(get("approved_at")):
        blocked.append("approved_at kosong — butuh timestamp persetujuan")

    return fail, blocked, warn


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gate #0 authorization & scope gate")
    ap.add_argument("target_pos", nargs="?", help="slug target (posisional; alternatif --target)")
    ap.add_argument("--target", help="slug target (membaca evidence/<slug>/authorization.yaml)")
    ap.add_argument("--manifest", help="path authorization manifest langsung")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--out", help="tulis verdict ke path ini (default: reports/<target>/gate0-verdict.json)")
    args = ap.parse_args(argv)

    if args.target_pos and not args.target:
        args.target = args.target_pos
    if not args.target and not args.manifest:
        ap.error("butuh <target> atau --target atau --manifest")
    if args.target:
        try:
            args.target = validate_slug(args.target)
        except ValueError as exc:
            print(f"FATAL: {exc}", file=sys.stderr)
            return 2
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
        except (OSError, RuntimeError) as exc:
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
