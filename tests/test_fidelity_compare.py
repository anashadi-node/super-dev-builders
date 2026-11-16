#!/usr/bin/python3
"""Tes untuk logika generik fidelity_compare (tanpa Pillow, tanpa browser, tanpa jaringan).

Fokus: memastikan dimensi TIDAK di-hardcode ke satu target, dan dimensi yang tidak bisa
diobservasi ditandai NOT_OBSERVED/NOT_MEASURED dengan coverage null (bukan angka karangan).
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import fidelity_compare as fc


def cap(interaction=None, api=None, facts=None, status=200, load_ms=100, path="/index.html"):
    it = None
    if interaction is not None:
        it = interaction
    if api is not None:
        it = dict(it or {})
        it.setdefault("selector", ".x")
        it["api_calls"] = api
    page = {"path": path, "url": "http://127.0.0.1:1" + path, "http_status": status, "load_ms": load_ms,
            "interaction": it, "facts": facts or {}, "screenshot": "x.png"}
    return {"pages": [page]}


def inter(selector=".portfolio-link", dialogs=1, aria=None, dom_delta=5, error=None):
    d = {"selector": selector, "effect": {"visible_dialogs": dialogs, "aria_expanded_after": aria, "dom_delta": dom_delta}}
    if error:
        d["error"] = error
    return d


class TestPagePath(unittest.TestCase):
    """Regresi nyata 2026-11-15: `/index.html` vs `/` membuat visual NOT_MEASURED."""

    def test_index_html_sama_dengan_root(self):
        self.assertEqual(fc.page_path("/index.html"), "/")
        self.assertEqual(fc.page_path("/"), "/")
        self.assertEqual(fc.page_path("/index.htm"), "/")

    def test_index_html_dalam_subdir(self):
        self.assertEqual(fc.page_path("/blog/index.html"), "/blog/")
        self.assertEqual(fc.page_path("/blog/index.htm"), "/blog/")

    def test_query_dan_fragment_dibuang(self):
        self.assertEqual(fc.page_path("/about.html?a=1#x"), "/about.html")

    def test_pages_irisan_setelah_normalisasi(self):
        a, b = cap(path="/index.html")["pages"][0], dict(cap(path="/")["pages"][0])
        b["path"] = "/"
        op, rp = fc.pages({"pages": [a]}), fc.pages({"pages": [b]})
        self.assertEqual(set(op) & set(rp), {"/"})
        self.assertEqual(len(op), 1)


class TestNormHref(unittest.TestCase):
    """Regresi nyata 2026-11-15: href absolut vs relatif membuat navigation = 0.0."""

    def test_absolut_dan_relatif_identik(self):
        self.assertEqual(fc.norm_href("/about.html", "/"), fc.norm_href("about.html", "/"))

    def test_relatif_dari_subdir(self):
        self.assertEqual(fc.norm_href("detail.html", "/blog/"), "/blog/detail.html")
        self.assertEqual(fc.norm_href("../kontak.html", "/blog/"), "/kontak.html")

    def test_anchor_dan_skema_non_navigasi_diabaikan(self):
        for h in ("#top", "mailto:a@b.c", "tel:+620", "javascript:void(0)", ""):
            self.assertIsNone(fc.norm_href(h, "/"))

    def test_url_penuh_jadi_path(self):
        self.assertEqual(fc.norm_href("http://127.0.0.1:8100/index.html", "/"), "/")


class TestInteraction(unittest.TestCase):
    def test_dialog_di_kedua_sisi_ok(self):
        r = fc.dim_interaction(cap(inter(".portfolio-link")), cap(inter(".portfolio-link")))
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["coverage"], 1.0)

    def test_aria_expanded_di_kedua_sisi_ok(self):
        r = fc.dim_interaction(cap(inter(".navbar-toggler", dialogs=0, aria="true")),
                               cap(inter(".navbar-toggler", dialogs=0, aria="true")))
        self.assertEqual(r["status"], "ok")

    def test_efek_hilang_di_rebuild_mismatch(self):
        r = fc.dim_interaction(cap(inter()), cap(inter(dialogs=0, aria=None)))
        self.assertEqual(r["status"], "mismatch")
        self.assertEqual(r["coverage"], 0.0)

    def test_selector_berbeda_mismatch(self):
        r = fc.dim_interaction(cap(inter(".a")), cap(inter(".b")))
        self.assertEqual(r["status"], "mismatch")

    def test_tidak_ada_interaksi_not_measured(self):
        r = fc.dim_interaction(cap(inter(error="Timeout")), cap(inter()))
        self.assertEqual(r["status"], "NOT_MEASURED")
        self.assertIsNone(r["coverage"])


class TestApiContract(unittest.TestCase):
    def test_tanpa_api_not_observed_bukan_dikarang(self):
        r = fc.dim_api(cap(inter()), cap(inter()))
        self.assertEqual(r["status"], "NOT_OBSERVED")
        self.assertIsNone(r["coverage"])

    def test_status_dan_kunci_sama_ok(self):
        a = [{"url": "http://h/api/status", "status": 200, "body": {"state": "ok", "ts": 1}}]
        r = fc.dim_api(cap(api=a), cap(api=list(a)))
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["coverage"], 1.0)

    def test_kunci_berbeda_partial(self):
        a = [{"url": "http://h/api/status", "status": 200, "body": {"state": "ok"}}]
        b = [{"url": "http://h/api/status", "status": 200, "body": {"state": "ok", "extra": 1}}]
        r = fc.dim_api(cap(api=a), cap(api=b))
        self.assertEqual(r["status"], "partial")
        self.assertEqual(r["coverage"], 0.5)

    def test_hanya_satu_sisi_api_mismatch(self):
        a = [{"url": "http://h/api/x", "status": 200, "body": {}}]
        r = fc.dim_api(cap(api=a), cap(inter()))
        self.assertEqual(r["status"], "mismatch")

    def test_host_port_berbeda_tetap_dibandingkan(self):
        """Original di :8100 vs rebuild di :8101 — kunci pembanding harus path, bukan URL utuh."""
        a = [{"url": "http://127.0.0.1:8100/api/status", "status": 200, "body": {"state": "ok", "ts": 1}}]
        b = [{"url": "http://127.0.0.1:8101/api/status", "status": 200, "body": {"state": "ok", "ts": 2}}]
        r = fc.dim_api(cap(api=a), cap(api=b))
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["coverage"], 1.0)

    def test_path_api_sebagian_sama_partial(self):
        a = [{"url": "http://127.0.0.1:8100/api/status", "status": 200, "body": {}},
             {"url": "http://127.0.0.1:8100/api/extra", "status": 200, "body": {}}]
        b = [{"url": "http://127.0.0.1:8101/api/status", "status": 200, "body": {}}]
        r = fc.dim_api(cap(api=a), cap(api=b))
        self.assertEqual(r["status"], "partial")
        self.assertEqual(r["coverage"], 0.5)

    def test_path_api_beda_semua_mismatch(self):
        a = [{"url": "http://127.0.0.1:8100/api/status", "status": 200, "body": {}}]
        b = [{"url": "http://127.0.0.1:8101/api/health", "status": 200, "body": {}}]
        r = fc.dim_api(cap(api=a), cap(api=b))
        self.assertEqual(r["status"], "mismatch")
        self.assertEqual(r["coverage"], 0.0)


class TestA11y(unittest.TestCase):
    def test_semua_fitur_original_terpenuhi(self):
        o = cap(facts={"headings": [1], "aria": ["x"], "roles": ["dialog"], "buttons": [1], "forms": [1], "lang": "en"})
        r = cap(facts={"headings": [1], "aria": ["y"], "roles": [], "buttons": [1], "forms": [], "lang": "en"})
        res = fc.dim_a11y(o, r)
        self.assertEqual(res["status"], "partial")
        self.assertLess(res["coverage"], 1.0)
        self.assertIn("roles", res["note"])

    def test_fitur_penuh_cov_1(self):
        f = {"headings": [1], "aria": ["x"], "roles": ["dialog"], "buttons": [1], "forms": [1], "lang": "en"}
        self.assertEqual(fc.dim_a11y(cap(facts=f), cap(facts=dict(f)))["coverage"], 1.0)

    def test_original_tanpa_fitur_not_observed(self):
        res = fc.dim_a11y(cap(facts={}), cap(facts={}))
        self.assertEqual(res["status"], "NOT_OBSERVED")


class TestExternalDependency(unittest.TestCase):
    def _net(self, urls):
        return {"items": [{"phase": "request", "url": u} for u in urls]}

    def test_rebuild_mandiri_ok(self):
        d = fc.dim_external(self._net(["http://127.0.0.1:8200/a", "https://cdn.example.com/x"]),
                            self._net(["http://127.0.0.1:8201/a"]))
        self.assertEqual(d["status"], "ok")
        self.assertEqual(d["coverage"], 1.0)

    def test_original_tanpa_pihak_ketiga_not_observed(self):
        d = fc.dim_external(self._net(["http://127.0.0.1:8200/a"]), self._net(["http://127.0.0.1:8201/a"]))
        self.assertEqual(d["status"], "NOT_OBSERVED")

    def test_menghitung_host_pihak_ketiga(self):
        ext, hosts = fc.external_requests(self._net(["http://127.0.0.1:1/a", "https://cdn.example.com/x",
                                                     "https://fonts.example.net/y"]))
        self.assertEqual(ext, 2)
        self.assertEqual(hosts, ["cdn.example.com", "fonts.example.net"])

    def test_baca_dari_berkas_network_json(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "network.json")
            json.dump(self._net(["https://cdn.example.com/x"]), open(p, "w"))
            self.assertEqual(fc.external_requests(p)[0], 1)


class TestDimensiTidakHilang(unittest.TestCase):
    def test_daftar_dimensi_9_dan_stabil(self):
        self.assertEqual(len(fc.DIMS), 9)
        self.assertEqual(fc.DIMS[-1], "external_dependency")


if __name__ == "__main__":
    unittest.main()
