#!/usr/bin/python3
"""Capture web terkendali (Gate #0 wajib PASS) -> evidence mentah + draft normalized.

Dijalankan dengan playwright yang tersedia:
  uv run --with playwright==1.63.0 python scripts/capture_web.py --target <slug> --url http://127.0.0.1:8100/index.html \
      --pages /index.html,/about.html --out evidence/<slug>/capture

Aturan: hanya host di allowed_targets; tanpa login; rate-limit; timeout eksplisit; tanpa TLS interception.
Exit: 0 sukses, 2 argumen/target tidak sah, 3 gate #0 belum PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gate_check import allowed_urls, evaluate
from sdb_common import load_yaml, repo_path, write_json


def load_scope(target: str) -> dict:
    p = repo_path("evidence", target, "authorization.yaml")
    return load_yaml(p) or {}


def gate0_or_die(target: str, quiet: bool = False) -> int:
    """Fail-closed: capture jaringan hanya boleh jalan bila Gate #0 PASS.

    Aturan #1 repo: 'Tidak ada deep scan/capture tanpa authorization.yaml PASS'.
    Sebelumnya capture_web.py hanya mencocokkan daftar allowed_targets dan TIDAK
    pernah memanggil gate — manifest terisi tapi tidak disahkan pun tetap bisa
    capture. Sekarang: verdict harus PASS (exit 0), selain itu TOLAK.

    Mengembalikan 0 bila lolos, atau exit code 1/2 bila tidak (FAIL/BLOCKED).
    """
    p = repo_path("evidence", target, "authorization.yaml")
    if not os.path.exists(p):
        print(f"TOLAK: manifest tidak ada: {p} (jalankan scripts/init_target.py {target})", file=sys.stderr)
        return 2
    try:
        manifest = load_yaml(p) or {}
    except Exception as exc:
        print(f"TOLAK: manifest tidak bisa dibaca: {exc}", file=sys.stderr)
        return 1
    fail, blocked, warn = evaluate(manifest if isinstance(manifest, dict) else {})
    if fail or blocked:
        print("TOLAK: Gate #0 tidak PASS — capture jaringan dibatalkan.", file=sys.stderr)
        for label, items in (("FAIL", fail), ("BLOCKED", blocked)):
            for it in items:
                print(f"  {label}: {it}", file=sys.stderr)
        return 2 if blocked and not fail else 1
    if warn and not quiet:
        for w in warn:
            print(f"  WARN: {w}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Capture web terkendali")
    ap.add_argument("--target", required=True)
    ap.add_argument("--url", required=True, help="URL halaman pertama (harus di allowed_targets)")
    ap.add_argument("--pages", default="", help="path tambahan, dipisah koma")
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout-ms", type=int, default=15000)
    ap.add_argument("--settle-ms", type=int, default=400)
    ap.add_argument("--rate-delay-s", type=float, default=2.0)
    ap.add_argument("--click", default="", help="selector yang diklik setelah load (uji interaksi)")
    ap.add_argument("--viewport", default="1280x720", help="WxH")
    args = ap.parse_args(argv)

    scope = load_scope(args.target)
    rc = gate0_or_die(args.target)
    if rc != 0:
        return rc
    allowed = allowed_urls(scope.get("allowed_targets") or {})
    base = "{u.scheme}://{u.netloc}".format(u=urlparse(args.url))
    if not allowed:
        print("TOLAK: allowed_targets kosong di manifest", file=sys.stderr)
        return 2
    if not any(base.startswith(a.rstrip("/")) or a.rstrip("/").startswith(base) for a in allowed):
        print(f"TOLAK: {base} tidak ada di allowed_targets manifest", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright  # import di dalam agar pesan rapi

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pages = [urlparse(args.url).path or "/"] + [p for p in args.pages.split(",") if p]
    net = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        vw, vh = (int(x) for x in args.viewport.lower().split("x"))
        ctx = browser.new_context(viewport={"width": vw, "height": vh}, ignore_https_errors=False)
        page = ctx.new_page()
        page.on("request", lambda r: net.append({"phase": "request", "method": r.method, "url": r.url,
                                                 "resource_type": r.resource_type, "headers": r.headers}))
        page.on("response", lambda r: net.append({"phase": "response", "status": r.status, "url": r.url,
                                                  "headers": r.headers}))
        result = {"target": args.target, "url": args.url, "base": base, "captured_at": time.time(), "pages": []}
        for i, pth in enumerate(pages):
            url = base + pth
            t0 = time.time()
            resp = page.goto(url, wait_until="load", timeout=args.timeout_ms)
            page.wait_for_timeout(args.settle_ms)
            shot = out / f"shot{i}.png"
            page.screenshot(path=str(shot), full_page=True)
            dom = page.content()
            (out / f"dom{i}.html").write_text(dom, encoding="utf-8")
            facts = page.evaluate("""() => ({
                title: document.title,
                lang: document.documentElement.lang || null,
                links: [...document.querySelectorAll('a[href]')].map(a => ({text: a.textContent.trim(), href: a.getAttribute('href')})),
                forms: [...document.querySelectorAll('form')].map(f => ({action: f.getAttribute('action'), method: (f.getAttribute('method')||'get').toLowerCase(),
                        fields: [...f.querySelectorAll('input,select,textarea')].map(x => ({name: x.getAttribute('name'), type: (x.getAttribute('type')||x.tagName.toLowerCase())}))})),
                buttons: [...document.querySelectorAll('button')].map(b => ({text: b.textContent.trim(), testid: b.getAttribute('data-testid')})),
                headings: [...document.querySelectorAll('h1,h2,h3')].map(h => ({tag: h.tagName.toLowerCase(), text: h.textContent.trim()})),
                roles: [...document.querySelectorAll('[role]')].map(e => e.getAttribute('role')),
                aria: [...document.querySelectorAll('[aria-label]')].map(e => e.getAttribute('aria-label')),
                apiFetch: (window.__sdbApiCalls || null)
            })""")
            interaction = None
            if args.click:
                try:
                    el = page.query_selector(args.click)
                    if el:
                        net_len = len(net)
                        dom_before = len(dom)
                        aria_before = el.get_attribute("aria-expanded")
                        el.click()
                        page.wait_for_timeout(args.settle_ms * 2)
                        # efek generik: perubahan DOM + dialog/log yang benar-benar terlihat
                        dom_after = len(page.content())
                        visible_dialogs = page.evaluate("""() => [...document.querySelectorAll('[role=dialog],dialog')]
                            .filter(e => { const r = e.getBoundingClientRect();
                                           return r.width > 0 && r.height > 0 && getComputedStyle(e).display !== 'none'; }).length""")
                        status_txt = page.eval_on_selector("#status", "e => e.textContent") if page.query_selector("#status") else None
                        api = [e for e in net[net_len:] if e["phase"] == "response" and "/api/" in e["url"]]
                        bodies = []
                        for a in api:
                            try:
                                bodies.append({"url": a["url"], "status": a["status"],
                                               "body": page.request.get(a["url"]).json()})
                            except Exception as exc:
                                bodies.append({"url": a["url"], "status": a["status"], "error": str(exc)})
                        interaction = {"selector": args.click, "status_text": status_txt, "api_calls": bodies,
                                       "aria_expanded_before": aria_before, "effect": {"dom_len_before": dom_before, "dom_len_after": dom_after,
                                                  "dom_delta": dom_after - dom_before,
                                                  "visible_dialogs": visible_dialogs,
                                                  "aria_expanded_after": page.eval_on_selector(args.click, "e => e.getAttribute('aria-expanded')") if page.query_selector(args.click) else None}}
                except Exception as exc:
                    interaction = {"selector": args.click, "error": str(exc)}
            result["pages"].append({"path": pth, "url": url, "http_status": resp.status if resp else None,
                                    "interaction": interaction,
                                    "load_ms": int((time.time() - t0) * 1000),
                                    "screenshot": os.path.relpath(shot, repo_path()),
                                    "dom_sha256": hashlib.sha256(dom.encode()).hexdigest(),
                                    "facts": facts})
            if i + 1 < len(pages):
                time.sleep(args.rate_delay_s)
        ctx.close()
        browser.close()

    write_json(out / "network.json", {"target": args.target, "captured_at": result["captured_at"],
                                      "base": base, "items": net})
    write_json(out / "capture.json", result)
    write_json(out / "totals.json", {"pages": len(result["pages"]),
                                     "requests": sum(1 for e in net if e["phase"] == "request"),
                                     "responses": sum(1 for e in net if e["phase"] == "response")})
    print(f"capture selesai: {out} | halaman={len(result['pages'])} "
          f"request={sum(1 for e in net if e['phase']=='request')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
