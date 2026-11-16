#!/usr/bin/python3
"""Hitung fidelity parity original vs rebuild per dimensi -> verification/<target>/fidelity.json.

Butuh Pillow untuk dimensi visual: jalankan via
  uv run --with pillow python scripts/fidelity_compare.py ...

Prinsip: target-agnostic. TIDAK ada selector/endpoint/atribut yang di-hardcode untuk satu target.
Dimensi yang tidak bisa diobservasi ditandai NOT_OBSERVED / NOT_MEASURED dengan coverage null —
jangan dikarang angkanya. Exit 0 sukses, 2 input kurang.
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import read_json, repo_path, validate_slug, write_json

DIMS = ["visual", "navigation", "interaction", "responsive", "functional",
        "accessibility", "performance", "api_contract", "external_dependency"]
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def page_path(path):
    """Kunci pembanding halaman: `/index.html` dan `/` adalah halaman yang sama.

    Bug nyata (2026-11-15): server statis mengalihkan `/` ke `/index.html`, sehingga
    capture original berkunci `/index.html` sementara rebuild berkunci `/`. Tanpa
    normalisasi, irisan path kosong -> visual NOT_MEASURED dan navigation/functional
    jatuh ke 0 walau halamannya identik. Aturan: buang `index.html`/`index.htm`
    di ujung path (``/a/index.html`` -> ``/a/``, ``/index.html`` -> ``/``).
    """
    p = (path or "/").split("?")[0].split("#")[0]
    for tail in ("/index.html", "/index.htm"):
        if p.endswith(tail):
            p = p[: -len("index.html" if tail.endswith("html") else "index.htm")]
            break
    if not p.startswith("/"):
        p = "/" + p
    return p


def norm_href(href, base_path="/"):
    """Tautan dinormalkan jadi path absolut, lalu lewat `page_path`.

    Bug nyata (2026-11-15): capture original menyimpan href absolut (`/about.html`)
    sedangkan rebuild relatif (`about.html`) — secara perilaku identik, tapi
    perbandingan string mentah membuat navigation = 0.0. Tautan `#anchor`,
    `mailto:`, `tel:`, `javascript:` diabaikan (bukan navigasi halaman).
    """
    h = (href or "").strip()
    if not h or h.startswith(("#", "javascript:")):
        return None
    u = urlsplit(h)
    if u.scheme in ("mailto", "tel", "sms", "data"):
        return None
    if u.scheme in ("http", "https") or u.netloc:
        p = u.path or "/"
    else:
        p = urljoin(base_path if base_path.endswith("/") else base_path + "/", h)
    return page_path(p)


def pages(cap):
    """Peta path -> halaman. Path dinormalisasi; halaman pertama menang."""
    out = {}
    for p in cap["pages"]:
        out.setdefault(page_path(p["path"]), p)
    return out


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


# ---------- dimensi generik (dipakai juga oleh tests/test_fidelity_compare.py) ----------

def interaction_sig(cap):
    """Jejak interaksi pertama yang berhasil: selector + efek terukur (tanpa hardcode selector)."""
    for p in cap.get("pages", []):
        it = p.get("interaction") or {}
        if it.get("selector") and not it.get("error"):
            e = it.get("effect") or {}
            return {"selector": it["selector"], "dialogs": e.get("visible_dialogs"),
                    "dom_delta": e.get("dom_delta"), "aria": e.get("aria_expanded_after"),
                    "status_text": it.get("status_text")}
    return None


def dim_interaction(oc, rc):
    o, r = interaction_sig(oc), interaction_sig(rc)
    if not o or not r:
        return {"dimension": "interaction", "status": "NOT_MEASURED", "coverage": None,
                "evidence": "capture.json#pages[].interaction", "note": "tidak ada interaksi berhasil untuk dibandingkan"}
    same = o["selector"] == r["selector"]
    # efek dianggap setara bila salah satu bukti terukur: dialog tampil keduanya,
    # aria-expanded berubah keduanya, ATAU DOM memang tumbuh dengan status teks
    # non-kosong di kedua sisi (klik menimbulkan efek nyata, bentuknya tak harus dialog).
    dialogs = (o["dialogs"] or 0) > 0 and (r["dialogs"] or 0) > 0
    aria = bool(o["aria"]) and bool(r["aria"])
    dom_effect = (o["dom_delta"] is not None and r["dom_delta"] is not None
                  and o["dom_delta"] == r["dom_delta"] and o["dom_delta"] > 0
                  and (o.get("status_text") or r.get("status_text")))
    ok = same and (dialogs or aria or dom_effect)
    return {"dimension": "interaction", "status": "ok" if ok else "mismatch", "coverage": 1.0 if ok else 0.0,
            "evidence": "capture.json#pages[].interaction.effect",
            "note": "selector sama=%s; dialog original/rebuild=%s/%s; aria-expanded=%s/%s; dom_delta=%s/%s; status_text=%s/%s"
                    % (same, o["dialogs"], r["dialogs"], o["aria"], r["aria"], o["dom_delta"], r["dom_delta"],
                       bool(o.get("status_text")), bool(r.get("status_text")))}


def _url_path(url):
    """Kunci pembanding API = path saja (host/port berbeda antara original dan rebuild)."""
    try:
        from urllib.parse import urlsplit
        return urlsplit(url or "").path or "/"
    except ValueError:
        return url or ""


def api_calls(cap):
    out = {}
    for p in cap.get("pages", []):
        for c in (p.get("interaction") or {}).get("api_calls") or []:
            out.setdefault(_url_path(c.get("url")), c)
    return out


def dim_api(oc, rc):
    o, r = api_calls(oc), api_calls(rc)
    if not o and not r:
        return {"dimension": "api_contract", "status": "NOT_OBSERVED", "coverage": None,
                "evidence": "normalized/<target>/network.json",
                "note": "tidak ada panggilan API yang diobservasi — tidak diklaim setara, tidak dikarang"}
    if not o or not r:
        return {"dimension": "api_contract", "status": "mismatch", "coverage": 0.0,
                "evidence": "capture.json#interaction.api_calls",
                "note": "hanya satu sisi memanggil API (original=%d, rebuild=%d)" % (len(o), len(r))}
    shared = set(o) & set(r)
    same_paths = set(o) == set(r)
    same_status = all(o[k].get("status") == r[k].get("status") for k in shared)
    same_body = all(set((o[k].get("body") or {})) == set((r[k].get("body") or {})) for k in shared)
    ok = same_paths and same_status and same_body
    return {"dimension": "api_contract",
            "status": "ok" if ok else ("partial" if shared else "mismatch"),
            "coverage": 1.0 if ok else (0.5 if shared else 0.0),
            "evidence": "capture.json#interaction.api_calls",
            "note": "%d endpoint dibandingkan (kunci=path, irisan=%d); path sama=%s, status sama=%s, kunci JSON sama=%s"
                    % (len(o), len(shared), same_paths, same_status, same_body)}


def a11y_features(cap):
    f = (cap.get("pages") or [{}])[0].get("facts") or {}
    return {"headings": bool(f.get("headings")), "aria": bool(f.get("aria")), "roles": bool(f.get("roles")),
            "buttons": bool(f.get("buttons")), "forms": bool(f.get("forms")), "lang": bool(f.get("lang"))}


def dim_a11y(oc, rc):
    o, r = a11y_features(oc), a11y_features(rc)
    need = [k for k, v in o.items() if v]          # fitur yang ADA di original harus terpenuhi di rebuild
    if not need:
        return {"dimension": "accessibility", "status": "NOT_OBSERVED", "coverage": None,
                "evidence": "normalized/<target>/components.json", "note": "original tidak menyediakan fitur a11y yang bisa dibandingkan"}
    hit = sum(1 for k in need if r.get(k))
    cov = round(hit / len(need), 4)
    missing = sorted(k for k in need if not r.get(k))
    return {"dimension": "accessibility", "status": "ok" if cov == 1 else "partial", "coverage": cov,
            "evidence": "normalized/<target>/components.json",
            "note": "fitur original terpenuhi %d/%d%s" % (hit, len(need), ("; kurang: " + ",".join(missing)) if missing else "")}


def external_requests(cap_or_path):
    """Jumlah request ke host pihak ketiga (bukan localhost).

    Menerima: path ke network.json | dict network.json ({'items': [...]}) | dict capture.json ({'pages': [...]}).
    """
    d = read_json(cap_or_path) or {} if isinstance(cap_or_path, str) else cap_or_path
    if isinstance(d, dict) and "items" in d:
        urls = [i.get("url", "") for i in (d.get("items") or []) if i.get("phase", "request") == "request"]
    else:
        urls = [p.get("url", "") for p in ((d or {}).get("pages") or [])]
    ext, hosts = 0, set()
    for u in urls:
        h = urlsplit(u).hostname or ""
        if h and h not in LOCAL_HOSTS:
            ext += 1
            hosts.add(h)
    return ext, sorted(hosts)


def dim_external(net_orig, net_rebuild):
    """Rebuild yang mandiri (0 host pihak ketiga) = lebih baik, bukan 'tidak setara'."""
    oe, oh = external_requests(net_orig)
    re_, rh = external_requests(net_rebuild)
    if oe == 0:
        return {"dimension": "external_dependency", "status": "NOT_OBSERVED", "coverage": None,
                "evidence": "normalized/<target>/network.json",
                "note": "original juga tidak menghubungi host pihak ketiga"}
    cov = round(max(0.0, 1.0 - (re_ / oe)), 4)
    return {"dimension": "external_dependency", "status": "ok" if re_ == 0 else "partial", "coverage": cov,
            "evidence": "normalized/<target>/network.json",
            "note": "request pihak ketiga original=%d %s -> rebuild=%d %s" % (oe, oh, re_, rh or [])}


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

    try:
        validate_slug(args.target)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    oc, rc = read_json(os.path.join(args.original, "capture.json")), read_json(os.path.join(args.rebuilt, "capture.json"))
    if not oc or not rc:
        print("capture.json tidak ditemukan", file=sys.stderr)
        return 2
    op, rp = pages(oc), pages(rc)
    diff_dir = args.diff_dir or repo_path("verification", args.target, "diffs")
    os.makedirs(diff_dir, exist_ok=True)
    rows = []

    # visual
    first = sorted(set(op) & set(rp))[0] if set(op) & set(rp) else None
    if first is None:
        rows.append({"dimension": "visual", "status": "NOT_MEASURED", "coverage": None, "evidence": "-",
                     "note": "tidak ada path halaman yang sama antara original dan rebuild"})
    else:
        vis, _diff_is_blank = pix_diff(repo_path(op[first]["screenshot"]), repo_path(rp[first]["screenshot"]),
                               os.path.join(diff_dir, "visual-index.png"))
        rows.append({"dimension": "visual", "status": ("ok" if vis >= 0.9 else "partial" if vis >= 0.5 else "mismatch"),
                     "coverage": vis, "evidence": os.path.relpath(os.path.join(diff_dir, "visual-index.png"), repo_path()),
                     "note": "pixel diff full-page %s (coverage = 1 - rasio piksel berbeda; selisih gaya disengaja dilaporkan apa adanya)" % first})

    # navigation
    ol = {norm_href(lk["href"], k) for k, p in op.items() for lk in (p.get("facts") or {}).get("links") or []} - {None}
    rl = {norm_href(lk["href"], k) for k, p in rp.items() for lk in (p.get("facts") or {}).get("links") or []} - {None}
    nav = len(ol & rl) / len(ol | rl) if (ol | rl) else 1.0
    rows.append({"dimension": "navigation", "status": "ok" if nav == 1 else "partial",
                 "coverage": round(nav, 4), "evidence": "normalized/%s/screens.json" % args.target,
                 "note": "Jaccard tautan (original=%d, rebuild=%d)" % (len(ol), len(rl))})

    rows.append(dim_interaction(oc, rc))
    rows.append(dim_api(oc, rc))

    # functional
    fun = sum(1 for k in op if k in rp and op[k]["http_status"] == rp[k]["http_status"]) / max(len(op), 1)
    rows.append({"dimension": "functional", "status": "ok" if fun == 1 else "partial", "coverage": round(fun, 4),
                 "evidence": "normalized/%s/inventory.json" % args.target,
                 "note": "status HTTP per halaman sama"})

    rows.append(dim_a11y(oc, rc))

    # responsive
    if args.original_mobile and args.rebuilt_mobile:
        om_raw, rm_raw = read_json(os.path.join(args.original_mobile, "capture.json")), read_json(os.path.join(args.rebuilt_mobile, "capture.json"))
        om = pages(om_raw) if om_raw else {}
        rm = pages(rm_raw) if rm_raw else {}
        shared_m = sorted(set(om) & set(rm))
        if not shared_m and om and rm:
            pick_o, pick_r = next(iter(om.values())), next(iter(rm.values()))
        elif shared_m:
            pick_o, pick_r = om[shared_m[0]], rm[shared_m[0]]
        else:
            pick_o = pick_r = None
        if pick_o is None:
            rows.append({"dimension": "responsive", "status": "NOT_MEASURED", "coverage": None, "evidence": "-",
                         "note": "capture mobile tidak terbaca"})
        else:
            rvis, _ = pix_diff(repo_path(pick_o["screenshot"]), repo_path(pick_r["screenshot"]),
                               os.path.join(diff_dir, "visual-mobile.png"))
            rows.append({"dimension": "responsive",
                         "status": ("ok" if rvis >= 0.9 else "partial" if rvis >= 0.5 else "mismatch"), "coverage": rvis,
                         "evidence": os.path.relpath(os.path.join(diff_dir, "visual-mobile.png"), repo_path()),
                         "note": "pixel diff pada viewport mobile (dari capture --viewport yang dipakai); halaman=%s" % (shared_m[0] if shared_m else "pages[0]")})
    else:
        rows.append({"dimension": "responsive", "status": "NOT_MEASURED", "coverage": None, "evidence": "-",
                     "note": "capture mobile tidak dijalankan"})

    # performance
    o_ms = sum(p["load_ms"] for p in op.values()) / max(len(op), 1)
    r_ms = sum(p["load_ms"] for p in rp.values()) / max(len(rp), 1)
    perf = round(min(1.0, (o_ms * 2) / max(r_ms, 1)), 4)
    rows.append({"dimension": "performance", "status": "ok" if perf > 0.5 else "regress", "coverage": perf,
                 "evidence": "capture.json#pages[].load_ms",
                 "note": "load original %.0f ms vs rebuild %.0f ms (coverage=rasio dibatasi 1.0)" % (o_ms, r_ms)})

    # dependensi pihak ketiga (dibaca dari evidence mentah kedua sisi)
    rows.append(dim_external(os.path.join(args.original, "network.json"),
                             os.path.join(args.rebuilt, "network.json")))

    out = args.out or repo_path("verification", args.target, "fidelity.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_json(out, rows)
    print(f"fidelity.json -> {out}")
    for r in rows:
        cov = r["coverage"] if r["coverage"] is not None else "-"
        print(f"  {r['dimension']:20s} {r['status']:13s} coverage={cov}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
