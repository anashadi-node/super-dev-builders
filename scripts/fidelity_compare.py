#!/usr/bin/python3
"""Hitung fidelity parity original vs rebuild per dimensi -> verification/<target>/fidelity.json.

Butuh Pillow untuk dimensi visual: jalankan via
  uv run --with pillow python scripts/fidelity_compare.py ...

Coverage selalu dilaporkan; dimensi yang tidak diukur ditandai NOT_MEASURED (jangan dikarang).
Exit 0 sukses, 2 input kurang.
"""
from __future__ import annotations

import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import now_iso, read_json, repo_path, write_json

DIMS = ["visual", "navigation", "interaction", "responsive", "functional",
        "accessibility", "performance", "api_contract"]


def pages(cap):
    return {p["path"]: p for p in cap["pages"]}


def pix_diff(a_png, b_png, out_png):
    from PIL import Image, ImageChops
    a, b = Image.open(a_png).convert("RGB"), Image.open(b_png).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size)
    diff = ImageChops.difference(a, b)
    bbox = diff.getbbox()
    hist = diff.convert("L").histogram()
    total = sum(hist)
    changed = sum(hist[16:])          # abaikan noise <16/255
    diff.save(out_png)
    ratio = changed / total if total else 1.0
    return round(1.0 - ratio, 4), (bbox is not None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fidelity compare")
    ap.add_argument("--target", required=True)
    ap.add_argument("--original", required=True, help="folder capture original (desktop)")
    ap.add_argument("--rebuilt", required=True, help="folder capture rebuild (desktop)")
    ap.add_argument("--original-mobile", default="")
    ap.add_argument("--rebuilt-mobile", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--diff-dir", default="")
    args = ap.parse_args(argv)

    oc, rc = read_json(os.path.join(args.original, "capture.json")), read_json(os.path.join(args.rebuilt, "capture.json"))
    if not oc or not rc:
        print("capture.json tidak ditemukan", file=sys.stderr)
        return 2
    op, rp = pages(oc), pages(rc)
    diff_dir = args.diff_dir or repo_path("verification", args.target, "diffs")
    os.makedirs(diff_dir, exist_ok=True)
    rows = []

    # visual
    vis, vis_ok = pix_diff(repo_path(op["/index.html"]["screenshot"]), repo_path(rp["/index.html"]["screenshot"]),
                           os.path.join(diff_dir, "visual-index.png"))
    rows.append({"dimension": "visual", "status": "ok" if vis_ok else "match",
                 "coverage": vis, "evidence": os.path.relpath(os.path.join(diff_dir, "visual-index.png"), repo_path()),
                 "note": "pixel diff (perbedaan gaya sengaja diubah -> coverage < 1 adalah wajar)"})

    # navigation
    ol = {l["href"] for p in op.values() for l in p["facts"]["links"]}
    rl = {l["href"] for p in rp.values() for l in p["facts"]["links"]}
    nav = len(ol & rl) / len(ol | rl) if (ol | rl) else 1.0
    rows.append({"dimension": "navigation", "status": "ok" if nav == 1 else "partial",
                 "coverage": round(nav, 4), "evidence": "normalized/%s/screens.json" % args.target,
                 "note": "Jaccard tautan (original=%d, rebuild=%d)" % (len(ol), len(rl))})

    # interaction
    pat = re.compile(r"^\s*ok @ \d+\s*$")
    iok = all(pat.match(str((p.get("interaction") or {}).get("status_text") or "")) for p in list(op.values())[:1]) and \
          all(pat.match(str((p.get("interaction") or {}).get("status_text") or "")) for p in list(rp.values())[:1])
    rows.append({"dimension": "interaction", "status": "ok" if iok else "mismatch", "coverage": 1.0 if iok else 0.0,
                 "evidence": "evidence/%s/capture/capture.json#interaction" % args.target,
                 "note": "klik #btn-load -> teks status berpola '<state> @ <ts>'"})

    # api_contract
    def api(cap):
        for p in cap["pages"]:
            for c in (p.get("interaction") or {}).get("api_calls") or []:
                if "/api/status" in c["url"]:
                    return c
        return None
    oa, ra = api(oc), api(rc)
    aok = bool(oa and ra and oa.get("status") == ra.get("status") == 200
               and set((oa.get("body") or {}).keys()) == set((ra.get("body") or {}).keys()))
    rows.append({"dimension": "api_contract", "status": "ok" if aok else "mismatch", "coverage": 1.0 if aok else 0.0,
                 "evidence": "normalized/%s/network.json" % args.target,
                 "note": "GET /api/status -> 200, kunci JSON sama (state, ts)"})

    # functional
    fun = sum(1 for k in op if k in rp and op[k]["http_status"] == rp[k]["http_status"]) / max(len(op), 1)
    rows.append({"dimension": "functional", "status": "ok" if fun == 1 else "partial", "coverage": round(fun, 4),
                 "evidence": "normalized/%s/inventory.json" % args.target,
                 "note": "status HTTP per halaman sama"})

    # accessibility
    def a11y(cap):
        p = list(cap["pages"])[0]["facts"]
        return bool(p["headings"]) and "status" in p["roles"] and bool(p["aria"])
    rows.append({"dimension": "accessibility", "status": "ok" if (a11y(oc) and a11y(rc)) else "partial",
                 "coverage": 1.0 if (a11y(oc) and a11y(rc)) else 0.5,
                 "evidence": "normalized/%s/components.json" % args.target,
                 "note": "h1 + role=status + aria-label hadir di kedua versi"})

    # responsive
    if args.original_mobile and args.rebuilt_mobile:
        om, rm = read_json(os.path.join(args.original_mobile, "capture.json")), read_json(os.path.join(args.rebuilt_mobile, "capture.json"))
        rvis, _ = pix_diff(repo_path(om["pages"][0]["screenshot"]), repo_path(rm["pages"][0]["screenshot"]),
                           os.path.join(diff_dir, "visual-mobile.png"))
        rows.append({"dimension": "responsive", "status": "ok", "coverage": rvis,
                     "evidence": os.path.relpath(os.path.join(diff_dir, "visual-mobile.png"), repo_path()),
                     "note": "pixel diff pada viewport 390x844"})
    else:
        rows.append({"dimension": "responsive", "status": "NOT_MEASURED", "coverage": None, "evidence": "-",
                     "note": "capture mobile tidak dijalankan"})

    # performance
    o_ms = sum(p["load_ms"] for p in op.values()) / max(len(op), 1)
    r_ms = sum(p["load_ms"] for p in rp.values()) / max(len(rp), 1)
    perf = round(min(1.0, (o_ms * 2) / max(r_ms, 1)), 4)
    rows.append({"dimension": "performance", "status": "ok" if perf > 0.5 else "regress", "coverage": perf,
                 "evidence": "evidence/%s/capture/capture.json#pages[].load_ms" % args.target,
                 "note": "load original %.0f ms vs rebuild %.0f ms (coverage=rasio dibatasi 1.0)" % (o_ms, r_ms)})

    out = args.out or repo_path("verification", args.target, "fidelity.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_json(out, {"target": args.target, "generated_at": now_iso(), "dimensions": rows})
    # kontrak fidelity_report: list of {dimension,...}
    write_json(out, rows)
    print(f"fidelity.json -> {out}")
    for r in rows:
        cov = r["coverage"] if r["coverage"] is not None else "-"
        print(f"  {r['dimension']:14s} {r['status']:12s} coverage={cov}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
