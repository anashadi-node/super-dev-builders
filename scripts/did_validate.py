#!/usr/bin/env python3
"""Validator paket handoff Divisi Investigasi (DID) — deterministik, tanpa LLM.

Kenapa alat ini ada: spesifikasi untuk divisi Builders hanya berguna kalau bisa
diperiksa mesin. Alat ini menolak (exit 1) handoff yang:
  - tidak punya Gate #0 PASS yang benar-benar ada di disk,
  - mengutip evidence yang tidak ada / hash-nya berubah / berisi rahasia,
  - menyatakan INFERRED tanpa tes pemalsu, atau UNKNOWN tanpa probe,
  - mengklaim fitur must-have tanpa bukti OBSERVED,
  - mengaku memakai Replica Skill / menulis kode / mendaftarkan MCP,
  - melewati anggaran biaya yang disepakati.

Pemakaian:
  python3 scripts/did_validate.py validate --target e1-app
  python3 scripts/did_validate.py validate --handoff runs/e1-app/did/handoff.json --render
  python3 scripts/did_validate.py bench --handoff X.json --truth benchmarks/e1/ground_truth.json
  python3 scripts/did_validate.py profiles

Hanya stdlib. Exit: 0 = PASS, 1 = FAIL, 2 = berkas/argumen bermasalah.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_ID = "sdb.did.handoff/1"
SEVERITIES = ("error", "warn", "info")
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key PEM"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"), "GitHub token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "API key (sk-)"),
    (re.compile(r"\b0x[a-fA-F0-9]{64}\b"), "private key hex"),
]
HEDGE_WORDS = ("mungkin", "sepertinya", "diduga", "kira-kira", "probably", "likely")


# ---------------------------------------------------------------- util
def _load(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inside(root: str, path: str) -> bool:
    root = os.path.realpath(root)
    p = os.path.realpath(path)
    return p == root or p.startswith(root + os.sep)


def now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def profiles(root: str = ROOT) -> dict:
    with open(os.path.join(root, "platform", "did_profiles.json"), encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- checks
class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []
        self.metrics: dict = {}

    def add(self, cid: str, ok: bool, detail: str, severity: str = "error") -> None:
        self.checks.append({"id": cid, "ok": bool(ok), "severity": severity, "detail": detail})

    @property
    def failed(self) -> list[dict]:
        return [c for c in self.checks if not c["ok"] and c["severity"] == "error"]

    @property
    def passed(self) -> bool:
        return not self.failed


def _status_of(findings: dict) -> dict:
    return {f.get("id"): str(f.get("status", "")).upper() for f in findings.values()}


def validate(handoff: dict, root: str = ROOT) -> Report:
    rep = Report()
    prof = profiles(root)

    # R01 — bentuk & versi
    ok = isinstance(handoff, dict) and handoff.get("schema") == SCHEMA_ID
    rep.add("R01_schema", ok, f"schema={handoff.get('schema')!r} (harus {SCHEMA_ID})")
    target = (handoff.get("target") or {}).get("slug") or ""
    rep.add("R01b_target", bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", target)),
            f"slug target={target!r}")

    ttype = (handoff.get("target") or {}).get("type") or (handoff.get("scope") or {}).get("profile") or ""
    prof_def = (prof.get("profiles") or {}).get(ttype)
    rep.add("R02_profile", prof_def is not None,
            f"target type={ttype!r}; dikenal: {', '.join(sorted((prof.get('profiles') or {})))}")

    # R03 — Gate #0 nyata di disk (bukan sekadar diklaim di JSON)
    verdict_path = os.path.join(root, "reports", target, "gate0-verdict.json")
    claimed = str(((handoff.get("target") or {}).get("authorization") or {}).get("gate0_verdict", "")).upper()
    disk_verdict, why = None, ""
    if os.path.exists(verdict_path):
        try:
            disk_verdict = str(_load(verdict_path).get("verdict", "")).upper()
        except Exception as exc:  # noqa: BLE001
            why = f"verdict tidak terbaca: {exc}"
    else:
        why = "reports/<target>/gate0-verdict.json tidak ada — jalankan scripts/gate_check.py"
    rep.add("R03_gate0", disk_verdict == "PASS" and claimed == "PASS",
            f"disk={disk_verdict or why}; handoff={claimed or 'kosong'}")

    # R04 — evidence: ada, hash cocok, di dalam repo, tanpa rahasia
    ev_items = handoff.get("evidence_manifest") or []
    ev_ids = {e.get("id") for e in ev_items if e.get("id")}
    rep.add("R04a_manifest", bool(ev_items), f"{len(ev_items)} entri evidence")
    bad_hash, missing, outside, secret_hits = [], [], [], []
    total_bytes = 0
    for e in ev_items:
        p = str(e.get("path", ""))
        abs_p = p if os.path.isabs(p) else os.path.join(root, p)
        if not p or not os.path.exists(abs_p):
            missing.append(p or "(kosong)")
            continue
        if not inside(root, abs_p):
            outside.append(p)
            continue
        total_bytes += os.path.getsize(abs_p)
        if str(e.get("sha256", "")).lower() != sha256_file(abs_p):
            bad_hash.append(p)
        try:
            text = open(abs_p, encoding="utf-8", errors="ignore").read()
        except OSError:
            text = ""
        for pat, label in SECRET_PATTERNS:
            if pat.search(text):
                secret_hits.append(f"{p}:{label}")
    rep.add("R04b_exists", not missing, f"hilang: {missing[:5]}" if missing else "semua ada")
    rep.add("R04c_inside_repo", not outside, f"keluar repo: {outside[:5]}" if outside else "aman")
    rep.add("R04d_hash", not bad_hash, f"hash berubah: {bad_hash[:5]}" if bad_hash else "cocok")
    rep.add("R04e_no_secret", not secret_hits, f"kandidat rahasia: {secret_hits[:3]}" if secret_hits else "bersih")

    # R05 — findings: status, confidence, falsifikasi, rujukan evidence
    findings = {f.get("id"): f for f in (handoff.get("findings") or []) if f.get("id")}
    allowed = {"OBSERVED", "INFERRED", "UNKNOWN", "OUT_OF_SCOPE"}
    bad_status, no_ev, no_conf, no_falsify, dangling = [], [], [], [], []
    for fid, f in findings.items():
        st = str(f.get("status", "")).upper()
        if st not in allowed:
            bad_status.append(f"{fid}={st or 'kosong'}")
            continue
        refs = f.get("evidence") or []
        if st == "OBSERVED" and not refs:
            no_ev.append(fid)
        for r in refs:
            if r not in ev_ids:
                dangling.append(f"{fid}->{r}")
        if st == "INFERRED":
            c = f.get("confidence")
            if not isinstance(c, (int, float)) or not 0 <= c <= 100:
                no_conf.append(fid)
            fals = f.get("falsification") or {}
            if not (fals.get("test") and fals.get("expected")):
                no_falsify.append(fid)
    rep.add("R05a_status", not bad_status, f"status tak dikenal: {bad_status[:5]}")
    rep.add("R05b_observed_has_evidence", not no_ev, f"OBSERVED tanpa evidence: {no_ev[:5]}")
    rep.add("R05c_refs_valid", not dangling, f"rujukan menggantung: {dangling[:5]}")
    rep.add("R05d_inferred_conf+falsify", not (no_conf or no_falsify),
            f"INFERRED tanpa confidence: {no_conf[:5]} | tanpa falsifikasi: {no_falsify[:5]}")

    # R06 — unknown wajib punya probe + impact
    unk = handoff.get("unknowns") or []
    bad_unk = [u.get("id") for u in unk
               if not (u.get("question") and u.get("probe") and u.get("impact") in {"blocking", "non-blocking"})]
    rep.add("R06_unknowns_complete", not bad_unk, f"tidak lengkap: {bad_unk[:5]}" if bad_unk else f"{len(unk)} unknown lengkap")

    # R07 — coverage sesuai profil target & depth
    cov = {c.get("category"): c for c in (handoff.get("coverage") or [])}
    required = list((prof_def or {}).get("required_categories") or [])
    depth = str((handoff.get("scope") or {}).get("depth", (prof_def or {}).get("default_depth", "L2"))).upper()
    required += list(((prof.get("depths") or {}).get(depth) or {}).get("adds_categories") or [])
    missing_cov = [c for c in required if c not in cov]
    weak_cov = [c for c in required if c in cov and str(cov[c].get("status", "")).upper() == "MISSING"]
    rep.add("R07a_coverage_present", not missing_cov, f"kategori belum dilaporkan: {missing_cov}")
    rep.add("R07b_coverage_filled", not weak_cov, f"kategori MISSING: {weak_cov}")

    # R08 — fitur must-have: bukti OBSERVED + acceptance test lengkap
    feats = handoff.get("features") or []
    must = [f for f in feats if str(f.get("priority", "")).lower() == "must"]
    st_map = _status_of(findings)
    unsupported, no_at = [], []
    for f in must:
        refs = f.get("evidence") or []
        observed = any(st_map.get(x) == "OBSERVED" for x in refs) or any(
            st_map.get(x) == "OBSERVED" for x in (f.get("findings") or []))
        if not observed:
            unsupported.append(f.get("id"))
        ats = f.get("acceptance_tests") or []
        if not ats or any(not (a.get("given") and a.get("when") and a.get("then")) for a in ats):
            no_at.append(f.get("id"))
    rep.add("R08a_must_has_observed", not unsupported, f"must tanpa bukti OBSERVED: {unsupported[:5]}")
    rep.add("R08b_must_has_tests", not no_at, f"must tanpa acceptance test lengkap: {no_at[:5]}")

    # R09 — build seeds
    seeds = handoff.get("build_seeds") or {}
    api = seeds.get("api") or []
    api_bad = [a.get("path") for a in api if str(a.get("status", "")).upper() == "INFERRED" and not a.get("probe")]
    rep.add("R09a_api_probe", not api_bad, f"API INFERRED tanpa probe: {api_bad[:5]}")
    need_seeds = list((prof_def or {}).get("required_seeds") or [])
    missing_seeds = [k for k in need_seeds if not seeds.get(k)]
    rep.add("R09b_seeds_present", not missing_seeds, f"seed wajib kosong: {missing_seeds}")

    # R10 — disiplin: tidak ada replica skill, tidak menulis kode, MCP tidak didaftarkan
    disc = handoff.get("discipline") or {}
    rep.add("R10a_no_replica", disc.get("replica_skill_used") is False, f"replica_skill_used={disc.get('replica_skill_used')}")
    rep.add("R10b_readonly", disc.get("wrote_code") is False, f"wrote_code={disc.get('wrote_code')}")
    rep.add("R10c_no_mcp", disc.get("mcp_registered") is False, f"mcp_registered={disc.get('mcp_registered')}")
    rep.add("R10d_redacted", disc.get("redaction_applied") is True, f"redaction_applied={disc.get('redaction_applied')}")

    # R11 — anggaran (profil < depth < eksplisit)
    budget = handoff.get("budget") or {}
    limits = dict(prof.get("default_limits") or {})
    limits.update((prof_def or {}).get("limits") or {})
    limits.update(((prof.get("depths") or {}).get(depth) or {}).get("limits") or {})
    used = budget.get("used") or {}
    over = []
    for k, lim in limits.items():
        if k in used and isinstance(lim, (int, float)) and used[k] > lim:
            over.append(f"{k}={used[k]}>{lim}")
    rep.add("R11_budget", not over, f"melebihi anggaran: {over}" if over else "dalam anggaran")

    # R12 — kesiapan Builders
    ready = bool((handoff.get("handoff") or {}).get("builders_ready"))
    blocking = [u for u in unk if u.get("impact") == "blocking"]
    rep.add("R12_builders_ready", (not ready) or (not blocking),
            f"builders_ready={ready}, blocking_unknowns={len(blocking)}")

    # R13 — ambang mutu (dari platform/did_profiles.json, bukan angka di kode)
    bar = (prof_def or {}).get("quality_bar") or {}
    total_f0 = len(findings)
    obs0 = sum(1 for f in findings.values() if str(f.get("status", "")).upper() == "OBSERVED")
    obs_ratio = (obs0 / total_f0) if total_f0 else 0.0
    unk_ratio = len(unk) / max(total_f0 + len(unk), 1)
    cov_pct = (sum(1 for c in required if str(cov.get(c, {}).get("status", "")).upper() == "COVERED") / len(required) * 100) if required else 100.0
    q_fail = []
    if "min_observed_ratio" in bar and obs_ratio < float(bar["min_observed_ratio"]):
        q_fail.append(f"observed {obs_ratio:.2f} < {bar['min_observed_ratio']}")
    if "max_unknown_ratio" in bar and unk_ratio > float(bar["max_unknown_ratio"]):
        q_fail.append(f"unknown {unk_ratio:.2f} > {bar['max_unknown_ratio']}")
    if "min_coverage_pct" in bar and cov_pct < float(bar["min_coverage_pct"]):
        q_fail.append(f"coverage {cov_pct:.0f}% < {bar['min_coverage_pct']}%")
    rep.add("R13_quality_bar", not q_fail, "; ".join(q_fail) if q_fail else
            f"observed {obs_ratio:.2f}, unknown {unk_ratio:.2f}, coverage {cov_pct:.0f}%", severity="warn")

    # metrik
    total_f = len(findings)
    obs = sum(1 for f in findings.values() if str(f.get("status", "")).upper() == "OBSERVED")
    inf = sum(1 for f in findings.values() if str(f.get("status", "")).upper() == "INFERRED")
    rep.metrics = {
        "target": target, "type": ttype, "depth": depth,
        "findings": total_f, "observed": obs, "inferred": inf,
        "unknowns": len(unk), "blocking_unknowns": len(blocking),
        "features": len(feats), "must_features": len(must),
        "coverage_required": len(required),
        "coverage_covered": sum(1 for c in required if str(cov.get(c, {}).get("status", "")).upper() == "COVERED"),
        "evidence_files": len(ev_items), "evidence_bytes": total_bytes,
        "checks": len(rep.checks), "failed": len(rep.failed),
        "observed_ratio": round(obs / total_f, 3) if total_f else 0.0,
        "unknown_ratio": round(len(unk) / max(total_f + len(unk), 1), 3),
        "quality_bar": bar,
        "quality_warnings": q_fail,
    }
    return rep


# ---------------------------------------------------------------- render
def render_md(h: dict, rep: Report) -> str:
    t = h.get("target") or {}
    sc = h.get("scope") or {}
    m = rep.metrics
    L = [f"# Spesifikasi Investigasi — {t.get('name') or t.get('slug')}", "",
         f"> Dihasilkan `did_validate.py` pada {now()}. Sumber tunggal: `runs/{t.get('slug')}/did/handoff.json`.",
         f"> Status validasi: **{'PASS' if rep.passed else 'FAIL'}** · depth {m.get('depth')} · profil {m.get('type')}", ""]
    L += ["## 1. Ringkasan", "", str((h.get("handoff") or {}).get("summary") or "—"), "",
          f"- Fitur: **{m['features']}** (must {m['must_features']}) · temuan OBSERVED {m['observed']} / INFERRED {m['inferred']}",
          f"- Unknown: {m['unknowns']} (blocking {m['blocking_unknowns']}) · coverage {m['coverage_covered']}/{m['coverage_required']}",
          f"- Evidence: {m['evidence_files']} berkas · {round(m['evidence_bytes']/1024, 1)} KB", ""]
    if sc.get("in_scope"):
        L += ["**Dalam lingkup:** " + ", ".join(sc["in_scope"]), ""]
    if sc.get("out_of_scope"):
        L += ["**Di luar lingkup:** " + ", ".join(sc["out_of_scope"]), ""]

    L += ["## 2. Fitur & kriteria terima", "", "| ID | Fitur | Prioritas | Status | Bukti | Tes terima |", "|---|---|---|---|---|---|"]
    for f in h.get("features") or []:
        ats = f.get("acceptance_tests") or []
        L.append(f"| {f.get('id')} | {f.get('name')} | {f.get('priority')} | {f.get('status')} | "
                 f"{', '.join(f.get('evidence') or []) or '—'} | {len(ats)} |")

    L += ["", "## 3. Kontrak API teramati", "", "| Metode | Path | Status | Bukti | Catatan |", "|---|---|---|---|---|"]
    for a in (h.get("build_seeds") or {}).get("api") or []:
        L.append(f"| {a.get('method')} | `{a.get('path')}` | {a.get('status')} | "
                 f"{', '.join(a.get('evidence') or []) or '—'} | {a.get('note') or a.get('probe') or '—'} |")

    L += ["", "## 4. Model data yang disarankan", ""]
    for e in (h.get("build_seeds") or {}).get("entities") or []:
        fields = ", ".join(f.get("name", "?") for f in e.get("fields") or [])
        L.append(f"- **{e.get('name')}** ({e.get('status')}): {fields or '—'}")

    L += ["", "## 5. Unknown & probe", "", "| ID | Pertanyaan | Dampak | Probe |", "|---|---|---|---|"]
    for u in h.get("unknowns") or []:
        L.append(f"| {u.get('id')} | {u.get('question')} | {u.get('impact')} | {u.get('probe')} |")

    L += ["", "## 6. Jejak bukti", "", "| ID | Berkas | Status | Waktu |", "|---|---|---|---|"]
    for e in h.get("evidence_manifest") or []:
        L.append(f"| {e.get('id')} | `{e.get('path')}` | {e.get('status')} | {e.get('captured_at')} |")

    L += ["", "## 7. Hasil validasi mesin", "", "| Aturan | Hasil | Detail |", "|---|---|---|"]
    for c in rep.checks:
        L.append(f"| {c['id']} | {'PASS' if c['ok'] else 'FAIL'} | {c['detail']} |")
    L += ["", "_Dokumen ini dihasilkan dari handoff JSON; jangan diedit manual._", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- bench
_STOP = {"dan", "yang", "untuk", "dengan", "pada", "dari", "ini", "itu", "the", "and", "with", "for"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _stem(tok: str) -> str:
    """Stem ringan Indonesia/Inggris: cukup untuk menyamakan imbuhan, bukan NLP penuh."""
    for pre in ("memper", "menge", "meng", "meny", "men", "mem", "pen", "per", "ber", "ter", "di", "me", "pe"):
        if tok.startswith(pre) and len(tok) - len(pre) >= 4:
            tok = tok[len(pre):]
            break
    for suf in ("kannya", "nya", "kan", "an", "lah"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            tok = tok[: -len(suf)]
            break
    return tok


def _tokens(s: str) -> set:
    return {_stem(t) for t in _norm(s).split() if t not in _STOP and len(t) > 2}


def bench(handoff: dict, truth: dict) -> dict:
    """Precision/recall handoff vs label independen.

    Ekstra yang tidak ada di label dipisah dua: `hallucinated` (diklaim OBSERVED
    tanpa bukti apa pun) dan `extras` (temuan sah di luar cakupan label SPEC).
    Tanpa pemisahan ini, fitur jujur yang kebetulan tidak diuji terlihat seperti karangan.
    """
    claimed = [f for f in handoff.get("features") or [] if str(f.get("status", "")).upper() != "OUT_OF_SCOPE"]
    truth_feats = truth.get("features") or []

    def blob(cf: dict) -> str:
        return _norm(" ".join([str(cf.get("name", "")), str(cf.get("claim", "")),
                               " ".join(cf.get("keywords") or [])]))

    def label_phrases(tf: dict) -> list:
        """Tiap frasa dicek sendiri-sendiri; menggabungnya jadi satu string membuat
        pencocokan mustahil (bug: label panjang tak pernah jadi substring handoff)."""
        raw = [str(tf.get("name", "")), *(tf.get("keywords") or []), *(tf.get("aliases") or [])]
        return [_norm(x) for x in raw if x and len(_norm(x)) >= 3]

    def label_text(tf: dict) -> str:
        return " ".join([str(tf.get("id", "")), *(label_phrases(tf))])

    keys_of = [(label_phrases(tf), _tokens(label_text(tf)), tf) for tf in truth_feats]

    # Cocokkan dengan skor, bukan "yang pertama cocok". Uji pertama-cocok pernah
    # memberi label kas kepada fitur beranda (yang hanya menyebut modul lain dalam
    # ringkasannya), sehingga fitur kas sendiri tercatat sebagai ekstra dan recall
    # tampak lebih tinggi daripada kenyataan.
    kandidat = []
    for i, cf in enumerate(claimed):
        b = blob(cf)
        bt = _tokens(blob(cf))
        for keys, lt, tf in keys_of:
            hits = [k for k in keys if len(k) >= 3 and k in b]
            jac = len(bt & lt) / max(len(bt | lt), 1)
            if hits:
                # frasa lebih panjang = lebih spesifik = skor lebih tinggi
                skor = 2.0 + max(len(k) for k in hits) / 100.0
            elif jac >= 0.60:
                skor = jac
            else:
                continue
            kandidat.append((skor, i, tf.get("id")))
    kandidat.sort(key=lambda x: (-x[0], x[1], str(x[2])))

    taken, matched_truth, hit = set(), [], set()
    for skor, i, tid in kandidat:
        if tid in taken or i in hit:
            continue
        taken.add(tid)
        hit.add(i)
        matched_truth.append(tid)

    unmatched = [c for i, c in enumerate(claimed) if i not in hit]
    hallucinated = [c.get("id") for c in unmatched
                    if str(c.get("status", "")).upper() == "OBSERVED"
                    and not (c.get("evidence") or c.get("findings"))]
    extras = [c.get("id") for c in unmatched if c.get("id") not in hallucinated]
    missed = [tf.get("id") for tf in truth_feats if tf.get("id") not in taken]

    tp = len(matched_truth)
    precision = tp / max(tp + len(unmatched), 1)
    recall = tp / max(len(truth_feats), 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    return {
        "truth_features": len(truth_feats), "claimed_features": len(claimed),
        "true_positives": tp, "missed": missed, "extras": extras, "hallucinated": hallucinated,
        "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
        "hallucination_rate": round(len(hallucinated) / max(len(claimed), 1), 3),
    }


# ---------------------------------------------------------------- CLI
def _resolve_handoff(args) -> str:
    if args.handoff:
        return args.handoff
    if not args.target:
        raise SystemExit("butuh --target atau --handoff")
    return os.path.join(ROOT, "runs", args.target, "did", "handoff.json")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validator handoff Divisi Investigasi (DID)")
    sub = ap.add_subparsers(dest="cmd")

    v = sub.add_parser("validate", help="validasi handoff")
    v.add_argument("--target")
    v.add_argument("--handoff")
    v.add_argument("--render", action="store_true", help="tulis runs/<t>/did/SPEC_DID.md")
    v.add_argument("--json-out", help="default reports/<t>/did-validation.json")
    v.add_argument("--quiet", action="store_true")

    b = sub.add_parser("bench", help="ukur precision/recall terhadap ground truth")
    b.add_argument("--handoff", required=True)
    b.add_argument("--truth", required=True)
    b.add_argument("--json-out")

    sub.add_parser("profiles", help="tampilkan profil target & depth")

    args = ap.parse_args(argv)
    if args.cmd in (None, "profiles"):
        prof = profiles()
        for name, p in sorted((prof.get("profiles") or {}).items()):
            print(f"{name:10s} depth_default={p.get('default_depth')} seeds={','.join(p.get('required_seeds') or [])}")
            print(f"           kategori: {', '.join(p.get('required_categories') or [])}")
        for name, d in (prof.get("depths") or {}).items():
            print(f"depth {name}: +{', '.join(d.get('adds_categories') or []) or '—'}")
        return 0

    if args.cmd == "bench":
        res = bench(_load(args.handoff), _load(args.truth))
        print(json.dumps(res, indent=1, ensure_ascii=False))
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as fh:
                json.dump(res, fh, indent=1, ensure_ascii=False)
        return 0

    path = _resolve_handoff(args)
    if not os.path.exists(path):
        print(f"FAIL: handoff tidak ada: {path}", file=sys.stderr)
        return 2
    try:
        handoff = _load(path)
    except json.JSONDecodeError as exc:
        print(f"FAIL: JSON tidak valid: {exc}", file=sys.stderr)
        return 2

    rep = validate(handoff, ROOT)
    target = (handoff.get("target") or {}).get("slug") or "unknown"
    out = args.json_out or os.path.join(ROOT, "reports", target, "did-validation.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    payload = {"schema": "sdb.did.validation/1", "generated_at": now(),
               "handoff": os.path.relpath(path, ROOT), "passed": rep.passed,
               "metrics": rep.metrics, "checks": rep.checks}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)

    if args.render:
        md = render_md(handoff, rep)
        md_path = os.path.join(ROOT, "runs", target, "did", "SPEC_DID.md")
        os.makedirs(os.path.dirname(md_path), exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(md)

    if not args.quiet:
        for c in rep.checks:
            if not c["ok"]:
                print(f"{'FAIL' if c['severity'] == 'error' else 'WARN'} {c['id']}: {c['detail']}")
        print(f"did_validate: {'PASS' if rep.passed else 'FAIL'} · "
              f"{rep.metrics['findings']} temuan · must {rep.metrics['must_features']} · "
              f"coverage {rep.metrics['coverage_covered']}/{rep.metrics['coverage_required']} · -> {os.path.relpath(out, ROOT)}")
    return 0 if rep.passed else 1


if __name__ == "__main__":
    sys.exit(main())
