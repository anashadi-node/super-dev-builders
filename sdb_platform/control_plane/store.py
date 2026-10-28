"""Domain control plane SDB — tenancy, kuota, job, artefak. Stdlib + SQLite, tanpa dependensi.

Kenapa SQLite: Fase 2 harus membuktikan *kontrak* (isolasi tenant, pagar biaya, idempotensi) bekerja
sebelum memilih Postgres/queue. Skema sengaja dekat dengan platform/schemas/*.schema.json supaya
migrasi ke Postgres nanti hanya soal driver, bukan model data.

Aturan yang ditegakkan di sini (bukan di UI):
- setiap query menyertakan tenant_id  -> isolasi tidak bergantung disiplin programmer
- job wajib punya budget              -> biaya tidak bisa tumbuh tanpa batas
- idempotency_key unik per tenant     -> retry tidak menggandakan pekerjaan
- artefak wajib redaction_status      -> tidak ada publikasi artefak yang belum diredaksi
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time

PLANS = ("starter", "pro", "team", "enterprise")
ISOLATION = ("pool", "bridge", "silo")
JOB_TYPES = ("recon", "build", "review", "qa", "security", "docs", "release")
JOB_STATUS = ("queued", "running", "succeeded", "failed", "blocked", "budget_exceeded", "cancelled")
ARTIFACT_KINDS = ("evidence", "capture", "report", "log", "sarif", "sbom", "diff", "dataset")
REDACTION = ("clean", "redacted", "blocked")
MAX_TOKENS = 2_000_000
MAX_SECONDS = 14_400
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")

PLAN_LIMITS = {
    "starter": {"jobs_per_month": 50, "tokens_per_month": 2_000_000, "storage_gb": 5},
    "pro": {"jobs_per_month": 250, "tokens_per_month": 12_000_000, "storage_gb": 50},
    "team": {"jobs_per_month": 1500, "tokens_per_month": 80_000_000, "storage_gb": 250},
    "enterprise": {"jobs_per_month": 100_000, "tokens_per_month": 2_000_000_000, "storage_gb": 5000},
}


class ControlPlaneError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message

    def as_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


def new_id(prefix: str) -> str:
    """ULID-like: 26 karakter Crockford base32, sortable berdasarkan waktu (ms) + 80 bit acak."""
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    ms = int(time.time() * 1000)
    ts = ""
    for _ in range(10):
        ts = alphabet[ms % 32] + ts
        ms //= 32
    body = "".join(secrets.choice(alphabet) for _ in range(16))
    return f"{prefix}_{ts}{body}"


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _require(cond: bool, status: int, code: str, msg: str) -> None:
    if not cond:
        raise ControlPlaneError(status, code, msg)


class Store:
    def __init__(self, path: str = ":memory:"):
        self.path = path
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        # timeout=15: beberapa worker/proses boleh mengantre pada lock penulis (BEGIN IMMEDIATE),
        # bukan langsung gagal "database is locked" saat antrean sedang padat.
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.isolation_level = None  # transaksi eksplisit: BEGIN IMMEDIATE di jalur uang/kuota
        self.db.execute("PRAGMA foreign_keys = ON")
        self.migrate()
        from .billing import Billing  # impor lokal: hindari siklus modul
        self.billing = Billing(self.db)

    # ------------------------------------------------------------------ skema
    def migrate(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenants (
              tenant_id TEXT PRIMARY KEY,
              name TEXT,
              plan TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',
              isolation TEXT NOT NULL DEFAULT 'pool',
              jobs_per_month INTEGER NOT NULL,
              tokens_per_month INTEGER NOT NULL,
              storage_gb INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS api_keys (
              key_hash TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
              job_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
              type TEXT NOT NULL,
              pack_id TEXT NOT NULL,
              pack_version TEXT NOT NULL,
              target_ref TEXT NOT NULL,
              budget_tokens INTEGER NOT NULL,
              budget_seconds INTEGER NOT NULL,
              idempotency_key TEXT NOT NULL,
              status TEXT NOT NULL,
              tokens_used INTEGER NOT NULL DEFAULT 0,
              gate_verdict TEXT,
              hold_microusd INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              finished_at TEXT,
              UNIQUE (tenant_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS artifacts (
              artifact_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
              job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
              kind TEXT NOT NULL,
              sha256 TEXT NOT NULL,
              size INTEGER NOT NULL,
              redaction_status TEXT NOT NULL,
              retention_until TEXT NOT NULL,
              uri TEXT NOT NULL,
              media_type TEXT,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_tenant ON jobs(tenant_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_artifacts_tenant ON artifacts(tenant_id, job_id);
            """
        )
        self.db.commit()

    # ----------------------------------------------------------------- tenant
    def create_tenant(self, plan: str, name: str | None = None, isolation: str = "pool",
                      limits: dict | None = None, tenant_id: str | None = None) -> dict:
        _require(plan in PLANS, 400, "invalid_plan", f"plan harus salah satu {PLANS}")
        _require(isolation in ISOLATION, 400, "invalid_isolation", f"isolation harus salah satu {ISOLATION}")
        tid = tenant_id or new_id("t")
        _require(bool(ULID_RE.match(tid.split("_", 1)[-1])), 400, "invalid_tenant_id", "tenant_id harus ULID")
        base = dict(PLAN_LIMITS[plan])
        if limits:
            for k in ("jobs_per_month", "tokens_per_month", "storage_gb"):
                if k in limits:
                    _require(isinstance(limits[k], int) and limits[k] > 0, 400, "invalid_limits", f"{k} harus int > 0")
                    base[k] = limits[k]
        from .billing import TRIAL_CREDIT
        self.db.execute(
            "INSERT INTO tenants (tenant_id, name, plan, status, isolation, jobs_per_month,"
            " tokens_per_month, storage_gb, created_at, credit_microusd, credit_held_microusd)"
            " VALUES (?,?,?,?,?,?,?,?,?,0,0)",
            (tid, name, plan, "active", isolation, base["jobs_per_month"],
             base["tokens_per_month"], base["storage_gb"], utcnow()),
        )
        self.db.commit()
        if TRIAL_CREDIT[plan]:
            self.billing.grant_trial(tid, TRIAL_CREDIT[plan], f"kredit uji paket {plan}")
        return self.get_tenant(tid)

    def get_tenant(self, tenant_id: str) -> dict:
        row = self.db.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,)).fetchone()
        _require(row is not None, 404, "tenant_not_found", "tenant tidak ada")
        return dict(row)

    def set_status(self, tenant_id: str, status: str) -> dict:
        _require(status in ("active", "suspended", "deleted"), 400, "invalid_status", "status tidak sah")
        self.get_tenant(tenant_id)
        self.db.execute("UPDATE tenants SET status = ? WHERE tenant_id = ?", (status, tenant_id))
        self.db.commit()
        return self.get_tenant(tenant_id)

    def add_api_key(self, tenant_id: str, key: str | None = None) -> str:
        self.get_tenant(tenant_id)
        raw = key or secrets.token_urlsafe(32)
        _require(len(raw) >= 24, 400, "weak_key", "API key minimal 24 karakter")
        self.db.execute("INSERT OR REPLACE INTO api_keys VALUES (?,?,?)",
                        (hashlib.sha256(raw.encode()).hexdigest(), tenant_id, utcnow()))
        self.db.commit()
        return raw

    def tenant_for_key(self, key: str) -> str:
        row = self.db.execute("SELECT tenant_id FROM api_keys WHERE key_hash = ?",
                              (hashlib.sha256(key.encode()).hexdigest(),)).fetchone()
        _require(row is not None, 401, "unauthorized", "API key tidak dikenal")
        tenant = self.get_tenant(row["tenant_id"])
        _require(tenant["status"] == "active", 403, "tenant_inactive", "tenant tidak aktif")
        return tenant["tenant_id"]

    # -------------------------------------------------------------------- job
    def _month_start(self) -> str:
        return dt.datetime.now(dt.timezone.utc).replace(day=1, hour=0, minute=0, second=0,
                                                        microsecond=0).isoformat(timespec="seconds")

    def usage(self, tenant_id: str) -> dict:
        tenant = self.get_tenant(tenant_id)
        # Token yang sudah DIPAKAI + token yang masih DIPESAN job berjalan sama-sama mengurangi sisa kuota.
        # Tanpa ini, tenant bisa mengantre 1.000 job ber-budget 2 juta tanpa pernah menyentuh pagar.
        row = self.db.execute(
            "SELECT COUNT(*) n,"
            " COALESCE(SUM(tokens_used),0) used,"
            " COALESCE(SUM(CASE WHEN status IN ('queued','running') THEN budget_tokens ELSE tokens_used END),0) committed"
            " FROM jobs WHERE tenant_id = ? AND created_at >= ?",
            (tenant_id, self._month_start()),
        ).fetchone()
        storage = self.db.execute("SELECT COALESCE(SUM(size),0) s FROM artifacts WHERE tenant_id = ?",
                                  (tenant_id,)).fetchone()["s"]
        return {
            "tenant_id": tenant_id,
            "plan": tenant["plan"],
            "jobs_used": row["n"],
            "jobs_limit": tenant["jobs_per_month"],
            "tokens_used": row["used"],
            "tokens_committed": row["committed"],
            "tokens_limit": tenant["tokens_per_month"],
            "tokens_remaining": max(0, tenant["tokens_per_month"] - row["committed"]),
            "storage_bytes": storage,
            "storage_limit_bytes": tenant["storage_gb"] * 1024 ** 3,
        }

    def create_job(self, tenant_id: str, type: str, pack: dict, target_ref: str,
                   budget: dict, idempotency_key: str) -> tuple[dict, bool]:
        tenant = self.get_tenant(tenant_id)
        _require(tenant["status"] == "active", 403, "tenant_inactive", "tenant tidak aktif")
        _require(type in JOB_TYPES, 400, "invalid_type", f"type harus salah satu {JOB_TYPES}")
        _require(bool(re.match(r"^[a-z][a-z0-9-]{1,40}$", str(pack.get("id", "")))), 400,
                 "invalid_pack", "pack.id tidak sah")
        _require(bool(re.match(r"^\d+\.\d+\.\d+$", str(pack.get("version", "")))), 400,
                 "invalid_pack", "pack.version harus semver")
        _require(bool(re.match(r"^(artifact|git|upload)://", target_ref or "")), 400,
                 "invalid_target", "target_ref harus artifact:// git:// atau upload://")
        _require(isinstance(idempotency_key, str) and len(idempotency_key) >= 8, 400,
                 "invalid_idempotency_key", "idempotency_key minimal 8 karakter")
        tokens = budget.get("tokens")
        seconds = budget.get("seconds")
        _require(isinstance(tokens, int) and 1000 <= tokens <= MAX_TOKENS, 400, "invalid_budget",
                 f"budget.tokens harus 1000..{MAX_TOKENS}")
        _require(isinstance(seconds, int) and 60 <= seconds <= MAX_SECONDS, 400, "invalid_budget",
                 f"budget.seconds harus 60..{MAX_SECONDS}")

        existing = self.db.execute(
            "SELECT * FROM jobs WHERE tenant_id = ? AND idempotency_key = ?",
            (tenant_id, idempotency_key)).fetchone()
        if existing:
            return self._job_dict(existing), True

        use = self.usage(tenant_id)
        _require(use["jobs_used"] < use["jobs_limit"], 402, "quota_jobs_exceeded",
                 f"kuota job bulan ini habis ({use['jobs_used']}/{use['jobs_limit']})")
        _require(use["tokens_remaining"] >= tokens, 402, "quota_tokens_exceeded",
                 f"sisa token {use['tokens_remaining']} < budget {tokens}")

        from .billing import price_tokens
        hold = price_tokens(tokens, tenant["plan"])
        jid = new_id("j")
        # Satu transaksi: batas kuota, baris job, dan pesanan kredit harus terlihat bersama atau tidak sama sekali.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT INTO jobs (job_id, tenant_id, type, pack_id, pack_version, target_ref, budget_tokens,"
                " budget_seconds, idempotency_key, status, tokens_used, hold_microusd, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?)",
                (jid, tenant_id, type, pack["id"], pack["version"], target_ref, tokens, seconds,
                 idempotency_key, "queued", hold, utcnow()),
            )
            self.billing.reserve(tenant_id, jid, hold, f"hold {tokens} token @ {tenant['plan']}")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_job(tenant_id, jid), False

    def _job_dict(self, row) -> dict:
        return {
            "job_id": row["job_id"], "tenant_id": row["tenant_id"], "type": row["type"],
            "pack": {"id": row["pack_id"], "version": row["pack_version"]},
            "target_ref": row["target_ref"],
            "budget": {"tokens": row["budget_tokens"], "seconds": row["budget_seconds"]},
            "idempotency_key": row["idempotency_key"], "status": row["status"],
            "tokens_used": row["tokens_used"], "gate_verdict": row["gate_verdict"],
            "created_at": row["created_at"], "finished_at": row["finished_at"],
            "attempts": row["attempts"] if "attempts" in row.keys() else 0,
            "lease_owner": row["lease_owner"] if "lease_owner" in row.keys() else None,
            "cancel_requested": bool(row["cancel_requested"]) if "cancel_requested" in row.keys() else False,
        }

    def get_job(self, tenant_id: str, job_id: str) -> dict:
        row = self.db.execute("SELECT * FROM jobs WHERE job_id = ? AND tenant_id = ?",
                              (job_id, tenant_id)).fetchone()
        # 404 (bukan 403) supaya keberadaan job tenant lain tidak bocor
        _require(row is not None, 404, "job_not_found", "job tidak ditemukan")
        return self._job_dict(row)

    def finish_job(self, tenant_id: str, job_id: str, status: str, tokens_used: int,
                   gate_verdict: str | None = None, error: str | None = None) -> dict:
        _require(status in JOB_STATUS, 400, "invalid_status", "status tidak sah")
        _require(isinstance(tokens_used, int) and tokens_used >= 0, 400, "invalid_tokens",
                 "tokens_used harus int >= 0")
        job = self.get_job(tenant_id, job_id)
        _require(job["status"] in ("queued", "running"), 409, "job_closed", "job sudah selesai")
        final = "budget_exceeded" if tokens_used > job["budget"]["tokens"] else status
        row = self.db.execute("SELECT hold_microusd FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        hold = row["hold_microusd"] if row else 0
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "UPDATE jobs SET status = ?, tokens_used = ?, gate_verdict = ?, finished_at = ?,"
                " lease_owner = NULL, lease_until = NULL, last_error = ?"
                " WHERE job_id = ? AND tenant_id = ?",
                (final, tokens_used, gate_verdict, utcnow(), error, job_id, tenant_id),
            )
            tenant = self.get_tenant(tenant_id)
            if final in ("succeeded", "budget_exceeded"):
                self.billing.settle(tenant_id, job_id, tokens_used, tenant["plan"], hold)
            else:
                self.billing.release(tenant_id, job_id, hold, f"job {final}")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_job(tenant_id, job_id)

    # --------------------------------------------------------------- artefak
    def register_artifact(self, tenant_id: str, job_id: str, kind: str, sha256: str, size: int,
                          redaction_status: str, retention_until: str, uri: str,
                          media_type: str | None = None) -> dict:
        self.get_job(tenant_id, job_id)
        _require(kind in ARTIFACT_KINDS, 400, "invalid_kind", f"kind harus salah satu {ARTIFACT_KINDS}")
        _require(bool(SHA_RE.match(sha256 or "")), 400, "invalid_sha256", "sha256 harus 64 hex huruf kecil")
        _require(isinstance(size, int) and size >= 0, 400, "invalid_size", "size harus int >= 0")
        _require(redaction_status in REDACTION, 400, "invalid_redaction",
                 "redaction_status wajib clean|redacted|blocked")
        _require(redaction_status != "blocked", 422, "artifact_blocked",
                 "artefak berstatus blocked tidak boleh didaftarkan")
        _require(isinstance(retention_until, str) and len(retention_until) >= 10, 400,
                 "invalid_retention", "retention_until wajib ISO-8601")
        _require(bool(re.match(r"^(s3|artifact)://", uri or "")), 400, "invalid_uri",
                 "uri harus s3:// atau artifact://")
        use = self.usage(tenant_id)
        _require(use["storage_bytes"] + size <= use["storage_limit_bytes"], 402,
                 "quota_storage_exceeded", "kuota penyimpanan habis")
        aid = new_id("a")
        self.db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, tenant_id, job_id, kind, sha256, size, redaction_status,
                         retention_until, uri, media_type, utcnow()))
        self.db.commit()
        return {"artifact_id": aid, "tenant_id": tenant_id, "job_id": job_id, "kind": kind,
                "sha256": sha256, "size": size, "redaction_status": redaction_status,
                "retention_until": retention_until, "uri": uri, "media_type": media_type}

    def list_artifacts(self, tenant_id: str, job_id: str) -> list[dict]:
        self.get_job(tenant_id, job_id)
        rows = self.db.execute("SELECT * FROM artifacts WHERE tenant_id = ? AND job_id = ?"
                              " ORDER BY created_at", (tenant_id, job_id)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------- lease & antrean
    def _lease_until(self, seconds: int) -> str:
        return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)).isoformat(timespec="seconds")

    def claim_next_job(self, worker_id: str, lease_seconds: int = 120) -> dict | None:
        """Ambil satu job antrean secara atomik. Dua worker tidak mungkin mendapat job yang sama."""
        _require(isinstance(worker_id, str) and len(worker_id) >= 4, 400, "invalid_worker", "worker_id tidak sah")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT tenant_id, job_id FROM jobs WHERE status = 'queued' AND cancel_requested = 0"
                " ORDER BY created_at, job_id LIMIT 1").fetchone()
            if row is None:
                self.db.commit()
                return None
            cur = self.db.execute(
                "UPDATE jobs SET status = 'running', lease_owner = ?, lease_until = ?, attempts = attempts + 1"
                " WHERE job_id = ? AND status = 'queued'",
                (worker_id, self._lease_until(lease_seconds), row["job_id"]))
            if cur.rowcount != 1:  # kalah balapan: biarkan worker lain memilikinya
                self.db.rollback()
                return None
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_job(row["tenant_id"], row["job_id"])

    def heartbeat(self, worker_id: str, job_id: str, lease_seconds: int = 120) -> dict:
        cur = self.db.execute(
            "UPDATE jobs SET lease_until = ? WHERE job_id = ? AND lease_owner = ? AND status = 'running'",
            (self._lease_until(lease_seconds), job_id, worker_id))
        self.db.commit()
        _require(cur.rowcount == 1, 409, "lease_lost", "lease bukan milik worker ini atau job sudah selesai")
        row = self.db.execute("SELECT tenant_id FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self.get_job(row["tenant_id"], job_id)

    def reap_expired_leases(self, max_attempts: int = 3) -> list[dict]:
        """Worker mati -> job dikembalikan ke antrean; setelah max_attempts -> failed + kredit dilepas."""
        now = utcnow()
        self.db.execute("BEGIN IMMEDIATE")
        out: list[dict] = []
        try:
            rows = self.db.execute(
                "SELECT job_id, tenant_id, attempts, hold_microusd FROM jobs"
                " WHERE status = 'running' AND lease_until IS NOT NULL AND lease_until < ?", (now,)).fetchall()
            for r in rows:
                if r["attempts"] >= max_attempts:
                    self.db.execute(
                        "UPDATE jobs SET status = 'failed', last_error = 'lease_expired', finished_at = ?,"
                        " lease_owner = NULL, lease_until = NULL WHERE job_id = ?", (now, r["job_id"]))
                    self.billing.release(r["tenant_id"], r["job_id"], r["hold_microusd"], "lease_expired")
                    out.append({"job_id": r["job_id"], "result": "failed"})
                else:
                    self.db.execute(
                        "UPDATE jobs SET status = 'queued', lease_owner = NULL, lease_until = NULL,"
                        " last_error = 'lease_expired_requeue' WHERE job_id = ?", (r["job_id"],))
                    out.append({"job_id": r["job_id"], "result": "requeued"})
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return out

    def request_cancel(self, tenant_id: str, job_id: str) -> dict:
        """Batal: job antrean langsung ditutup; job berjalan ditandai agar worker menutup sebagai cancelled."""
        job = self.get_job(tenant_id, job_id)
        if job["status"] == "queued":
            return self.finish_job(tenant_id, job_id, "cancelled", 0, None, "cancelled_by_tenant")
        _require(job["status"] == "running", 409, "job_closed", "job sudah selesai")
        self.db.execute("UPDATE jobs SET cancel_requested = 1 WHERE job_id = ? AND tenant_id = ?",
                        (job_id, tenant_id))
        self.db.commit()
        return self.get_job(tenant_id, job_id)

    def dump_tenant(self, tenant_id: str) -> str:
        """Ekspor penuh satu tenant (untuk uji isolasi & migrasi pool->silo)."""
        self.get_tenant(tenant_id)
        jobs = [self._job_dict(r) for r in self.db.execute(
            "SELECT * FROM jobs WHERE tenant_id = ? ORDER BY created_at", (tenant_id,))]
        arts = [dict(r) for r in self.db.execute(
            "SELECT * FROM artifacts WHERE tenant_id = ? ORDER BY created_at", (tenant_id,))]
        return json.dumps({"tenant": self.get_tenant(tenant_id), "jobs": jobs,
                           "artifacts": arts, "usage": self.usage(tenant_id)},
                          indent=1, ensure_ascii=False)
