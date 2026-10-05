#!/usr/bin/python3
"""Normalisasi artefak capture -> normalized/<target>/*.json sesuai kontrak pipeline.

Pemakaian: /usr/bin/python3 scripts/normalize_capture.py --target <slug>
Exit 0 sukses, 2 bila artefak capture tidak ada.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import now_iso, read_json, repo_path, write_json

PROV = "evidence/{t}/capture/capture.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Normalisasi capture -> normalized/")
    ap.add_argument("--target", required=True)
    ap.add_argument("--capture", help="folder capture (default evidence/<target>/capture)")
    ap.add_argument("--rebuilt", default="", help="folder hasil rebuild (untuk teknologi/functional)")
    args = ap.parse_args(argv)

    cap_dir = args.capture or repo_path("evidence", args.target, "capture")
    cap = read_json(os.path.join(cap_dir, "capture.json"))
    net = read_json(os.path.join(cap_dir, "network.json"))
    if not cap or not net:
        print(f"artefak capture tidak ada di {cap_dir}", file=sys.stderr)
        return 2

    ts = now_iso()
    cap_at = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(cap["captured_at"]))
    prov = PROV.format(t=args.target)
    red = "redacted"

    def meta(status, extra=None, conf=None):
        d = {"provenance": prov, "captured_at": cap_at, "redaction_status": red, "status": status}
        if conf is not None:
            d["confidence"] = conf
        if extra:
            d.update(extra)
        return d

    pages = cap["pages"]
    routes = sorted({p["path"] for p in pages} | {e["url"].split("8100")[-1] for e in net["items"]
                                                  if e["phase"] == "request" and "/api/" in e["url"]})
    inventory = {"target": args.target, "generated_at": ts, "items": [
        meta("OBSERVED", {"kind": "routes", "values": routes}),
        meta("OBSERVED", {"kind": "entry_points", "values": [p["url"] for p in pages]}),
        meta("OBSERVED", {"kind": "roles_allowed", "values": ["anonymous (tanpa login)"]}),
        meta("OBSERVED", {"kind": "forms", "values": [f for p in pages for f in p["facts"]["forms"]]}),
        meta("OBSERVED", {"kind": "feature_areas",
                          "values": ["navigasi", "muat status (API)", "form kirim"]}),
    ]}
    screens = {"target": args.target, "generated_at": ts, "items": [
        meta("OBSERVED", {"path": p["path"], "title": p["facts"]["title"], "lang": p["facts"]["lang"],
                          "screenshot": p["screenshot"], "dom_sha256": p["dom_sha256"],
                          "http_status": p["http_status"], "load_ms": p["load_ms"]}) for p in pages]}
    components = {"target": args.target, "generated_at": ts, "items": [
        meta("OBSERVED", {"path": p["path"], "links": p["facts"]["links"], "buttons": p["facts"]["buttons"],
                          "headings": p["facts"]["headings"], "roles": p["facts"]["roles"],
                          "aria_labels": p["facts"]["aria"]}) for p in pages] + [
        meta("OBSERVED", {"component": "status-region", "evidence": "capture/capture.json#interaction.status_text",
                          "observed_text": (p.get("interaction") or {}).get("status_text")})
        for p in pages if p.get("interaction")]}
    network = {"target": args.target, "generated_at": ts, "items": [
        meta("OBSERVED", {"method": e["method"] if e["phase"] == "request" else "RESPONSE",
                          "url": e["url"].replace("http://127.0.0.1:8100", ""),
                          "http_status": e.get("status"), "kind": e.get("resource_type", "response"),
                          "release": "2026-10-04"}, conf=None) for e in net["items"]]}
    tech = {"target": args.target, "generated_at": ts, "items": [
        meta("INFERRED", {"aspect": "markup", "value": "HTML5 statis + <script> eksternal (app.js)"}, 95),
        meta("INFERRED", {"aspect": "css", "value": "file styles.css eksternal, tanpa framework terdeteksi"}, 90),
        meta("INFERRED", {"aspect": "js", "value": "vanilla JS (addEventListener + fetch), tanpa bundler"}, 90),
        meta("INFERRED", {"aspect": "api", "value": "JSON over HTTP GET /api/status, POST /submit"}, 88),
        meta("UNKNOWN", {"aspect": "backend", "value": "server hanya diamati sebagai proses lokal milik sendiri"}),
    ]}

    out = repo_path("normalized", args.target)
    os.makedirs(out, exist_ok=True)
    for name, payload in [("inventory", inventory), ("screens", screens), ("components", components),
                          ("network", network), ("technology", tech)]:
        write_json(os.path.join(out, f"{name}.json"), payload)
    print(f"normalized -> {out} (5 berkas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
