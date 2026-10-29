"""Metrik dan pembatas laju — stdlib saja, tanpa dependensi.

Diukur supaya operator bisa menjawab: berapa permintaan per status, berapa job dibuat/selesai, berapa
kali kuota atau laju menolak, dan berapa token yang ditagih. Format keluaran Prometheus (teks biasa),
jadi `prometheus.yml` hanya perlu satu target scrape — tidak perlu pustaka klien.

Batas yang disadari: penghitung disimpan di memori proses. Restart menghapusnya dan beberapa
proses/instance tidak saling menjumlah. Itu jujur untuk SQLite satu-node; begitu pindah ke Postgres
atau beberapa instance, metrik harus pindah ke penyimpanan bersama (lihat ADR-0008).
"""
from __future__ import annotations

import math
import threading
import time

DEFAULT_RATE_PER_MIN = 600  # 10 req/dtk per tenant; cukup untuk klien wajar, bukan untuk banjir
MAX_TRACKED_KEYS = 20_000  # pagar memori bila tenant dibuat massal


class Metrics:
    """Penghitung monotonik berlabel, dirender sebagai teks Prometheus."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._started = time.time()

    def inc(self, name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            items = sorted(self._counters.items())
        seen: set[str] = set()
        for (name, labels), value in items:
            if name not in seen:
                seen.add(name)
                lines.append(f"# TYPE {name} counter")
            label_text = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
            suffix = "{" + label_text + "}" if label_text else ""
            lines.append(f"{name}{suffix} {_num(value)}")
        lines.append("# TYPE sdb_uptime_seconds gauge")
        lines.append(f"sdb_uptime_seconds {_num(time.time() - self._started)}")
        return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.3f}"


class RateLimited(Exception):
    """Dilempar saat jatah laju tenant habis; `retry_after` dalam detik."""

    def __init__(self, retry_after: int):
        super().__init__("rate_limited")
        self.retry_after = max(1, int(retry_after))


class RateLimiter:
    """Token bucket per tenant.

    Kapasitas = 2x laju per detik (minimal 5) sehingga burst wajar (mis. klien membuka 20 job
    sekaligus) tetap dilayani, sementara banjir berkelanjutan ditahan. Memakai `monotonic`, jadi
    perubahan jam dinding tidak memberi jatah gratis.
    """

    def __init__(self, default_per_min: int = DEFAULT_RATE_PER_MIN) -> None:
        self.default_per_min = default_per_min
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._last_gc = time.monotonic()

    def check(self, key: str, per_min: int | None = None) -> None:
        rate = max(1, int(per_min or self.default_per_min)) / 60.0  # token per detik
        capacity = max(5.0, rate * 2)
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (capacity, now))
            tokens = min(capacity, tokens + (now - last) * rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                raise RateLimited(math.ceil((1.0 - tokens) / rate))
            self._buckets[key] = (tokens - 1.0, now)
            self._gc(now)

    def _gc(self, now: float) -> None:
        if len(self._buckets) < MAX_TRACKED_KEYS:
            return
        if now - self._last_gc < 60:
            return
        self._last_gc = now
        for key in [k for k, (_, last) in self._buckets.items() if now - last > 600]:
            del self._buckets[key]
