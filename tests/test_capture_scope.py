"""Regresi F-01 (ronde-3): allowlist capture_web harus cocok origin EKSAK, bukan prefiks string."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from capture_web import origin_allowed, safe_page_path

ALLOWED = ["https://example.com", "http://localhost:3000/app"]


@pytest.mark.parametrize("base", ["https://example.com", "https://EXAMPLE.com", "https://example.com:443",
                                  "http://localhost:3000"])
def test_exact_origin_allowed(base):
    assert origin_allowed(base, ALLOWED)


@pytest.mark.parametrize("base", [
    "https://example.com.evil.test",   # lolos startswith lama
    "https://example.co",              # lolos prefiks-terbalik lama
    "http://example.com",              # skema beda
    "https://example.com:8443",        # port beda
    "https://user@example.com",        # userinfo
    "https://evil.test@example.com",
    "ftp://example.com", "javascript:alert(1)", "", "https://",
    "http://localhost:3001"])
def test_lookalike_origin_rejected(base):
    assert not origin_allowed(base, ALLOWED)


def test_old_prefix_logic_was_bypassable():
    old = lambda base, allowed: any(base.startswith(a.rstrip("/")) or a.rstrip("/").startswith(base) for a in allowed)  # noqa: E731
    assert old("https://example.com.evil.test", ALLOWED) and old("https://example.co", ALLOWED)


@pytest.mark.parametrize("p", ["/", "/a/b?x=1", "/api/v1"])
def test_safe_pages_ok(p):
    assert safe_page_path(p)


@pytest.mark.parametrize("p", ["@evil.test/x", "//evil.test", "https://evil.test", "a/b", "/a b", "/a\\b", "/x@y", ""])
def test_unsafe_pages_rejected(p):
    assert not safe_page_path(p)


# Penutup mutan M9: origin_allowed() benar saja tidak cukup — pemanggilnya di
# dalam loop capture juga harus menolak. Disimulasikan dengan browser palsu yang
# mendarat di origin di luar allowed_targets (redirect).
class _Resp:
    status = 200


class _Page:
    def __init__(self, landing: str):
        self._landing = landing
        self.url = "about:blank"

    def on(self, *_a, **_k):
        return None

    def goto(self, url, **_k):
        self.url = self._landing
        return _Resp()

    def wait_for_timeout(self, _ms):
        return None

    def screenshot(self, path, **_k):
        Path(path).write_bytes(b"png")

    def content(self):
        return "<html><body>redirected</body></html>"

    def evaluate(self, _js):
        return {}


class _Context:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page

    def close(self):
        return None


class _Browser:
    def __init__(self, page):
        self._page = page

    def new_context(self, **_k):
        return _Context(self._page)

    def close(self):
        return None


class _Chromium:
    def __init__(self, page):
        self._page = page

    def launch(self, **_k):
        return _Browser(self._page)


class _Playwright:
    def __init__(self, page):
        self.chromium = _Chromium(page)


def _install_fake_playwright(monkeypatch, landing: str):
    import types

    page = _Page(landing)
    mod = types.ModuleType("playwright.sync_api")

    class _Ctx:
        def __enter__(self):
            return _Playwright(page)

        def __exit__(self, *_exc):
            return False

    mod.sync_playwright = _Ctx
    pkg = types.ModuleType("playwright")
    pkg.sync_api = mod
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", mod)


def test_redirect_keluar_scope_membatalkan_capture(tmp_path, monkeypatch):
    import capture_web

    monkeypatch.setattr(capture_web, "load_scope",
                        lambda _t: {"allowed_targets": {"a": "https://example.com"}})
    monkeypatch.setattr(capture_web, "gate0_or_die", lambda _t, quiet=False: 0)
    monkeypatch.setattr(capture_web, "allowed_urls", lambda _d: ["https://example.com"])
    _install_fake_playwright(monkeypatch, "https://evil.test/landing")

    out = tmp_path / "capture"
    rc = capture_web.main(["--target", "demo", "--url", "https://example.com/", "--out", str(out)])
    assert rc == 2, "redirect ke origin di luar scope harus menghentikan capture"
    assert not (out / "capture.json").exists(), "tidak boleh ada artefak bukti dari halaman di luar scope"
