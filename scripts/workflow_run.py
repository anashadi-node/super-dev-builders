#!/usr/bin/env python3
"""Runner 16 tahap — memberi tahu tahap mana yang PUNYA BUKTI dan mana yang BELUM.

Masalah yang diselesaikan: `docs/WORKFLOW_GATES.md` mendefinisikan 16 tahap, tetapi
hanya 2 tahap punya tool deterministik (Gate #0, Release Gate). Sisanya hanya "aturan
di atas kertas" — mudah diklaim, sulit diperiksa. Runner ini memeriksa artefak nyata
di disk untuk SETIAP tahap, lalu menyatakan jujur: ada / TIDAK ada.

Prinsip:
- BUKAN penilai kualitas. Runner ini hanya menjawab "artefak wajib tahap ini ada?".
  Kualitas isi diperiksa tool lain (`evidence_lint.py`, `release_check.py`, review manusia).
- Tanpa artefak => MISSING (bukan PASS bersyarat). Sejalan dengan WORKFLOW_GATES §2.
- Tahap yang belum punya tool deterministik ditandai `tool=-` supaya tidak menyesatkan.
- Exit 0 hanya bila semua artefak ada; `--require-all` (dipakai CI/gate) akan menolak
  selain itu. Tanpa `--require-all`, MODE laporan saja (exit tetap 0) untuk inspeksi.

Pemakaian:
    /usr/bin/python3 scripts/workflow_run.py sdb-local-demo
    /usr/bin/python3 scripts/workflow_run.py sdb-local-demo --json
    /usr/bin/python3 scripts/workflow_run.py sdb-local-demo --require-all

Intake (Command Deck -> runner):
    /usr/bin/python3 scripts/workflow_run.py --list-intakes
    /usr/bin/python3 scripts/workflow_run.py sdb-local-demo --intake latest
    /usr/bin/python3 scripts/workflow_run.py sdb-local-demo --intake latest --as 01

`--intake` menulis `runs/<t>/docs/intake-<id>.md` (brief verbatim + path absolut
lampiran) dan menunjuk kiriman terbaru di `runs/<t>/CONTEXT.md`. `--as 01` juga
mengisi `requirements.md` — hanya bila belum ada, dengan header provenance
"BELUM ditinjau manusia". Tahap lain tidak boleh diisi dari brief: brief bukan
pengganti ADR, plan, review, atau tes.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import now_iso, repo_path, validate_slug

import intake_lib

# Tahap yang artefaknya memang kata-kata Owner sendiri, sehingga boleh diisi
# langsung dari brief intake. Tahap lain TIDAK boleh: brief bukan pengganti ADR,
# plan, review, atau tes — mengisinya otomatis = mengarang bukti.
INTAKE_AS: dict[str, str] = {"01": "requirements.md"}

# (kode, nama, pola artefak relatif repo — {t} diganti slug target, tool deterministik)
# Pola memakai glob; artefak pertama yang cocok dianggap bukti.
STAGES: list[tuple[str, str, list[str], str]] = [
    ("01", "USER OBJECTIVE", ["runs/{t}/requirements.md"], "-"),
    ("01A", "AUTHORIZATION/SCOPE GATE", ["reports/{t}/gate0-verdict.json"], "gate_check.py"),
    ("01B", "RECON/EVIDENCE PACKAGE", ["normalized/{t}/inventory.json", "evidence/{t}/**/*.json"], "-"),
    ("02", "ORCHESTRATOR: KLARIFIKASI", ["runs/{t}/clarifications.md", "runs/{t}/requirements.md"], "-"),
    ("03", "RESEARCH (bila perlu)", ["runs/{t}/docs/research-*.md", "docs/RESEARCH_*"], "-"),
    ("04", "ARCHITECTURE + ADR", ["runs/{t}/docs/adr-*.md", "runs/{t}/docs/architecture-*.md"], "-"),
    ("05", "HUMAN DESIGN APPROVAL", ["runs/{t}/reports/approval-design.json", "runs/{t}/reports/approval-design-*.md"], "-"),
    ("06", "IMPLEMENTATION PLAN", ["runs/{t}/plan.md", "runs/{t}/tasks.json"], "-"),
    ("07", "IMPLEMENTASI (FE/BE)", ["targets/{t}/**/*"], "-"),
    ("08", "CODE REVIEW", ["runs/{t}/reports/review-*.md"], "-"),
    ("09", "QA / INTEGRATION / E2E", ["runs/{t}/logs/tests-*.log"], "-"),
    ("10", "SECURITY (SAST/DEP/SECRET)", ["runs/{t}/reports/security-gate.md"], "-"),
    ("11", "CODE AUDIT & ASSURANCE", ["runs/{t}/reports/assurance-audit.md"], "-"),
    ("12", "RELEASE GATE", ["runs/{t}/reports/release-verdict.json", "reports/{t}/release-gate.json"], "release_check.py"),
    ("13", "HUMAN APPROVAL PRODUKSI", ["runs/{t}/reports/approval-prod.json", "runs/{t}/reports/approval-prod-*.md"], "-"),
    ("14", "DEVOPS DEPLOY", ["runs/{t}/reports/deploy-*.md"], "-"),
    ("15", "OBSERVABILITY/SMOKE/ROLLBACK", ["runs/{t}/logs/smoke-*.log", "runs/{t}/docs/ROLLBACK_PLAN.md"], "-"),
    ("16", "DOCS + HANDOVER", ["runs/{t}/reports/handover-*.md", "runs/{t}/docs/README-*.md"], "-"),
]


def _root(root: str | None = None) -> str:
    """Akar pemeriksaan. Default REPO_ROOT; bisa diarahkan untuk uji/CI (hermetik)."""
    return root or repo_path()


def _expand(pattern: str, target: str, root: str | None = None) -> str:
    return os.path.join(_root(root), *pattern.replace("{t}", target).split("/"))


def find_evidence(pattern: str, target: str, root: str | None = None) -> list[str]:
    """Artefak di disk yang cocok dengan pola (glob rekursif bila memakai **)."""
    abs_pat = _expand(pattern, target, root)
    if "**" in abs_pat:
        # NB: jangan pakai nama `root` di sini — pernah menutupi parameter `root`
        # sehingga jalur bukti salah (ditemukan oleh uji positif 2026-10-07).
        walk_root = abs_pat.split("**", 1)[0].rstrip("/")
        if not os.path.isdir(walk_root):
            return []
        out = []
        for dirpath, _dirnames, filenames in os.walk(walk_root):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, _root(root))
                out.append(rel)
        return sorted(out)
    return sorted(os.path.relpath(p, _root(root)) for p in glob.glob(abs_pat))


def evaluate(target: str, root: str | None = None) -> list[dict]:
    """Status tiap tahap: ada(bukti) / MISSING, plus umur artefak dalam jam."""
    rows = []
    for code, name, patterns, tool in STAGES:
        hits: list[str] = []
        for pat in patterns:
            hits = find_evidence(pat, target, root)
            if hits:
                break
        age_h = None
        if hits:
            import time

            stamp = os.path.join(_root(root), hits[0])
            age_h = round((time.time() - os.path.getmtime(stamp)) / 3600.0, 1)
        rows.append({
            "stage": code,
            "name": name,
            "status": "OK" if hits else "MISSING",
            "tool": tool,
            "evidence": hits[:1],
            "age_hours": age_h,
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["status"] == "OK"]
    missing = [r for r in rows if r["status"] != "OK"]
    with_tool = [r for r in rows if r["tool"] != "-"]
    return {
        "stages_total": len(rows),
        "stages_ok": len(ok),
        "stages_missing": len(missing),
        "missing": [f"{r['stage']} {r['name']}" for r in missing],
        "stages_with_deterministic_tool": len(with_tool),
        "note": (
            f"{len(with_tool)} dari {len(rows)} tahap punya tool deterministik; "
            "sisanya diperiksa keberadaan artefaknya saja"
        ),
    }


def _intake_doc(target: str, d: dict, when: str) -> str:
    """Kartu konteks: brief verbatim + lampiran absolut, siap dibaca agen."""
    m = d["meta"]
    scen = f"{m.get('scen', '—')} — {m.get('scen_title', '')}".strip(" —")
    lines = [
        f"# Intake {d['id']} — konteks target {target}",
        "",
        f"> Ditulis otomatis oleh `workflow_run.py --intake` pada {when}.",
        f"> Sumber: `{d['dir']}`",
        "> Status: konteks mentah dari Owner — BELUM diverifikasi, bukan bukti kualitas.",
        "",
        f"- **Skenario**: {scen or '—'}",
        f"- **Tahap saat dikirim**: {m.get('stage') or '—'}",
        f"- **Target tertulis**: {m.get('target') or '—'}",
        f"- **Dibuat**: {m.get('created') or '—'}",
        f"- **Brief asli**: `{d['brief_path']}`",
        "",
        "## Brief (verbatim)",
        "",
        (d["brief"].strip() or "_brief kosong_"),
        "",
        "## Lampiran — path absolut",
        "",
    ]
    if d["files"]:
        lines += ["| Nama | Ukuran | sha256 | Path |", "|---|---|---|---|"]
        for f in d["files"]:
            lines.append(
                f"| {f['name']} | {f['size']} B | `{(f['sha256'] or '')[:16]}` | "
                f"`{f['path'] or '(hilang)'}` |"
            )
    else:
        lines.append("_tidak ada lampiran_")
    links = m.get("links") or []
    if links:
        lines += ["", "## Link", ""] + [f"- {u}" for u in links]
    return "\n".join(lines) + "\n"


CTX_BEGIN = "<!-- intake:begin -->"
CTX_END = "<!-- intake:end -->"


def _update_context(runs_dir: str, iid: str, rel_doc: str, scen: str, when: str) -> str:
    """Tunjuk intake terbaru di CONTEXT.md. Idempoten: blok ditulis ulang, bukan ditumpuk."""
    path = os.path.join(runs_dir, "CONTEXT.md")
    block = (
        f"{CTX_BEGIN}\n"
        "## Intake terbaru\n\n"
        f"- `{iid}` — {scen}\n"
        f"- Konteks: `{rel_doc}`\n"
        f"- Ditautkan: {when} (oleh `workflow_run.py --intake`)\n"
        f"{CTX_END}"
    )
    if os.path.isfile(path):
        txt = open(path, encoding="utf-8").read()
        if CTX_BEGIN in txt and CTX_END in txt:
            pre, post = txt.split(CTX_BEGIN, 1)[0], txt.split(CTX_END, 1)[1]
            txt = pre + block + post
        else:
            txt = txt.rstrip() + "\n\n" + block + "\n"
    else:
        txt = "# CONTEXT — konteks aktif target\n\n" + block + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(txt)
    return path


def _seed_requirements(runs_dir: str, target: str, d: dict, rel_doc: str, when: str) -> str | None:
    """Isi requirements.md dari brief — HANYA bila belum ada (tidak pernah menimpa)."""
    path = os.path.join(runs_dir, "requirements.md")
    if os.path.exists(path):
        return None
    body = (
        f"<!-- dibuat otomatis dari intake {d['id']} pada {when} — BELUM ditinjau manusia -->\n"
        f"# Requirements — {target}\n\n"
        f"Konteks lengkap: `{rel_doc}`\n\n"
        f"{d['brief'].strip()}\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


def bind_intake(target: str, iid: str, as_stage: str = "", root: str | None = None) -> dict:
    """Tautkan satu intake ke target: tulis kartu konteks + indeks CONTEXT.md."""
    data = intake_lib.load(iid)
    runs_dir = os.path.join(_root(root), "runs", target)
    docs_dir = os.path.join(runs_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    when = now_iso()
    doc = os.path.join(docs_dir, f"intake-{data['id']}.md")
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write(_intake_doc(target, data, when))
    rel_doc = os.path.relpath(doc, _root(root))
    ctx = _update_context(runs_dir, data["id"], rel_doc, f"{data['meta'].get('scen', '—')}", when)
    seeded = None
    if as_stage:
        req_name = INTAKE_AS.get(as_stage)
        if req_name:
            seeded = _seed_requirements(runs_dir, target, data, rel_doc, when)
    return {
        "target": target,
        "intake": data["id"],
        "dir": data["dir"],
        "doc": doc,
        "doc_rel": rel_doc,
        "context": ctx,
        "files_total": len(data["files"]),
        "files_present": sum(1 for f in data["files"] if f["exists"]),
        "as_stage": as_stage or "",
        "requirements_seeded": seeded,
        "requirements_skipped": bool(as_stage and not seeded),
        "brief_chars": len(data["brief"]),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Runner 16 tahap berbasis bukti")
    ap.add_argument("target", nargs="?", help="slug target (mis. sdb-local-demo)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--require-all", action="store_true",
                    help="exit 1 bila ada tahap MISSING (dipakai gerbang)")
    ap.add_argument("--list-stages", action="store_true")
    ap.add_argument("--intake", default="", metavar="ID",
                    help="tautkan kiriman Intake Command Deck ke target (ID atau 'latest')")
    ap.add_argument("--as", dest="as_stage", default="", metavar="STAGE",
                    help="isi juga artefak tahap dari brief (khusus 01 -> requirements.md)")
    ap.add_argument("--list-intakes", action="store_true", help="daftar kiriman Intake di disk")
    ap.add_argument("--root", default="", help="akar repo alternatif (uji/CI hermetik)")
    args = ap.parse_args(argv)

    if args.list_stages:
        for code, name, _p, tool in STAGES:
            print(f"{code:>4}  {name:<32} tool={tool}")
        return 0
    if args.list_intakes:
        ids = intake_lib.list_ids()
        if not ids:
            print(f"Belum ada kiriman Intake di {intake_lib.root()}")
            return 0
        for iid in ids[:40]:
            try:
                d = intake_lib.load(iid)
            except (ValueError, FileNotFoundError) as exc:
                print(f"{iid}  (gagal dibaca: {exc})")
                continue
            m = d["meta"]
            judul = (m.get("title") or m.get("text") or "").replace("\n", " ")[:60]
            print(f"{iid}  scen={m.get('scen') or '—':<3} stage={(m.get('stage') or '—'):<4} "
                  f"file={len(d['files']):<2} {judul}")
        return 0
    if not args.target:
        ap.error("target wajib (atau pakai --list-stages / --list-intakes)")
    if args.as_stage and args.as_stage not in INTAKE_AS:
        ap.error(f"--as hanya mendukung {', '.join(sorted(INTAKE_AS))}: "
                 "brief bukan pengganti ADR/plan/review/tes")

    try:
        target = validate_slug(args.target)
    except ValueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2
    root = _root(args.root or None)
    if not os.path.isdir(os.path.join(root, "runs", target)) and not os.path.isdir(os.path.join(root, "targets", target)):
        print(f"FATAL: target '{target}' tidak dikenal (tidak ada runs/{target} atau targets/{target})",
              file=sys.stderr)
        return 2

    if args.intake:
        iid = args.intake.strip()
        if iid.lower() == "latest":
            iid = intake_lib.latest() or ""
            if not iid:
                print("FATAL: belum ada kiriman Intake di disk", file=sys.stderr)
                return 2
        try:
            bound = bind_intake(target, iid, args.as_stage, args.root or None)
        except (ValueError, FileNotFoundError) as exc:
            print(f"FATAL: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps({"target": target, "intake": bound, "checked_at": now_iso()},
                             indent=2, ensure_ascii=False))
        else:
            print(f"Intake {bound['intake']} -> target {target}")
            print(f"  konteks  : {bound['doc_rel']}")
            print(f"  CONTEXT  : {os.path.relpath(bound['context'], _root(args.root or None))}")
            print(f"  lampiran : {bound['files_present']}/{bound['files_total']} ada di disk")
            print(f"  brief    : {bound['brief_chars']} karakter")
            if args.as_stage:
                if bound["requirements_seeded"]:
                    print(f"  tahap {args.as_stage} : requirements.md DIBUAT dari brief "
                          "— belum ditinjau manusia")
                else:
                    print(f"  tahap {args.as_stage} : dilewati (requirements.md sudah ada, "
                          "tidak ditimpa)")
        return 0

    rows = evaluate(target, args.root or None)
    summary = summarize(rows)
    if args.json:
        print(json.dumps({"target": target, "checked_at": now_iso(), "stages": rows,
                          "summary": summary}, indent=2, ensure_ascii=False))
    else:
        print(f"Workflow 16 tahap — target: {target}")
        print(f"{'tahap':<5} {'nama':<32} {'status':<8} {'tool':<16} bukti")
        for r in rows:
            ev = r["evidence"][0] if r["evidence"] else "—"
            print(f"{r['stage']:<5} {r['name']:<32} {r['status']:<8} {r['tool']:<16} {ev}")
        print()
        print(f"OK {summary['stages_ok']}/{summary['stages_total']} | "
              f"MISSING {summary['stages_missing']}")
        if summary["missing"]:
            print("Belum ada bukti:")
            for m in summary["missing"]:
                print(f"  - {m}")
        print(summary["note"])
    return 1 if (args.require_all and summary["stages_missing"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
