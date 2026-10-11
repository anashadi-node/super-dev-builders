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
