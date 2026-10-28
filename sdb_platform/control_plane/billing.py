"""Billing SDB — prabayar, satuan micro-USD bulat, ledger append-only ber-rantai hash.

Kenapa integer micro-USD: uang tidak boleh float. 1 μUSD = 1e-6 USD, jadi $2,00/1 juta token = 2_000_000.
Kenapa append-only + hash rantai: tagihan harus bisa diaudit tanpa mempercayai kode yang menulisnya —
setiap baris memuat hash baris sebelumnya, sehingga penghapusan/penyuntingan diam-diam terdeteksi.

Model akuntansi (satu akun kredit per tenant, tanpa angka negatif):
- `topup`     : +kredit
- `hold`      : -kredit, +held (uang dipesan untuk job berjalan)
- `charge`    : -held, 0 kredit (uang benar-benar dibelanjakan)
- `release`   : +kredit, -held (job gagal/batal: pesanan dikembalikan)
- `refund`    : +kredit (koreksi/kompensasi)
- `adjust`    : ±kredit (koreksi manual admin, wajib memo)

Invarian yang diuji: credit == sum(amount) dan held == sum(hold - charge - release) per tenant.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import uuid

MICRO = 1_000_000  # μUSD per USD

# Harga per 1 juta token (μUSD). Sumber: docs/ARSITEKTUR_SAAS.md §unit economics.
PLAN_PRICE_PER_MTOK = {
    "starter": 2_000_000,      # $2,00 / 1 juta token
    "pro": 1_600_000,          # $1,60
    "team": 1_200_000,         # $1,20
    "enterprise": 1_000_000,   # $1,00 (kontrak volume)
}

# Kredit uji saat tenant dibuat (μUSD) — cukup untuk puluhan job kecil, habis lalu harus topup.
TRIAL_CREDIT = {
    "starter": 5 * MICRO,
    "pro": 25 * MICRO,
    "team": 100 * MICRO,
    "enterprise": 0,
}

KINDS = ("topup", "hold", "charge", "release", "refund", "adjust")
GENESIS = "0" * 64


class BillingError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message

    def as_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def price_tokens(tokens: int, plan: str) -> int:
    """Harga token dalam μUSD, dibulatkan KE ATAS supaya tidak ada token gratis karena pembulatan."""
    if tokens <= 0:
        return 0
    rate = PLAN_PRICE_PER_MTOK.get(plan)
    if rate is None:
        raise BillingError(400, "unknown_plan", f"plan tidak dikenal: {plan}")
    return -(-tokens * rate // 1_000_000)


def _hash(prev: str, tenant_id: str, kind: str, amount: int, balance_after: int,
          held_after: int, job_id: str | None, ts: str) -> str:
    payload = f"{prev}|{tenant_id}|{kind}|{amount}|{balance_after}|{held_after}|{job_id or ''}|{ts}"
    return hashlib.sha256(payload.encode()).hexdigest()


class Billing:
    """Semua metode menulis memakai transaksi `BEGIN IMMEDIATE`: baca-saldo lalu tulis tidak boleh balapan."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.migrate()

    # ------------------------------------------------------------------ skema
    def migrate(self) -> None:
        cur = self.db.cursor()
        cols = {r[1] for r in cur.execute("PRAGMA table_info(tenants)")}
        if "credit_microusd" not in cols:
            cur.execute("ALTER TABLE tenants ADD COLUMN credit_microusd INTEGER NOT NULL DEFAULT 0")
        if "credit_held_microusd" not in cols:
            cur.execute("ALTER TABLE tenants ADD COLUMN credit_held_microusd INTEGER NOT NULL DEFAULT 0")
        jcols = {r[1] for r in cur.execute("PRAGMA table_info(jobs)")}
        for col, ddl in (("lease_owner", "TEXT"), ("lease_until", "TEXT"),
                         ("attempts", "INTEGER NOT NULL DEFAULT 0"),
                         ("last_error", "TEXT"), ("cancel_requested", "INTEGER NOT NULL DEFAULT 0"),
                         ("hold_microusd", "INTEGER NOT NULL DEFAULT 0")):
            if col not in jcols:
                cur.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS ledger (
              entry_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              ts TEXT NOT NULL,
              kind TEXT NOT NULL,
              amount INTEGER NOT NULL,
              balance_after INTEGER NOT NULL,
              held_after INTEGER NOT NULL,
              job_id TEXT,
              memo TEXT,
              prev_hash TEXT NOT NULL,
              hash TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ledger_tenant ON ledger(tenant_id, ts);
            CREATE TABLE IF NOT EXISTS job_charges (
              job_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              micro_usd INTEGER NOT NULL,
              tokens_used INTEGER NOT NULL,
              plan TEXT NOT NULL,
              ts TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoices (
              invoice_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              period_start TEXT NOT NULL,
              period_end TEXT NOT NULL,
              total_microusd INTEGER NOT NULL,
              jobs INTEGER NOT NULL,
              status TEXT NOT NULL,
              snapshot TEXT NOT NULL,
              prev_hash TEXT NOT NULL,
              hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE (tenant_id, period_start, period_end)
            );
            """
        )
        self.db.commit()

    # ------------------------------------------------------------------ saldo
    def _tenant(self, tenant_id: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,)).fetchone()
        if row is None:
            raise BillingError(404, "tenant_not_found", "tenant tidak ada")
        return row

    def balance(self, tenant_id: str) -> dict:
        row = self._tenant(tenant_id)
        return {
            "tenant_id": tenant_id,
            "plan": row["plan"],
            "credit_microusd": row["credit_microusd"],
            "held_microusd": row["credit_held_microusd"],
            "available_microusd": row["credit_microusd"],
            "price_per_mtok_microusd": PLAN_PRICE_PER_MTOK[row["plan"]],
        }

    def _append(self, tenant_id: str, kind: str, amount: int, job_id: str | None, memo: str) -> dict:
        if kind not in KINDS:
            raise BillingError(400, "invalid_kind", f"kind harus salah satu {KINDS}")
        row = self._tenant(tenant_id)
        balance = row["credit_microusd"] + amount
        held = row["credit_held_microusd"]
        if kind == "hold":
            held += -amount
        elif kind == "release":
            held -= amount
        # charge hanya memindahkan uang yang sudah dipesan menjadi pendapatan; held tidak berubah.
        if balance < 0:
            raise BillingError(402, "insufficient_credit", "kredit tidak cukup")
        if held < 0:
            raise BillingError(409, "held_underflow", "pesanan kredit tidak konsisten")
        prev = self.db.execute("SELECT hash FROM ledger WHERE tenant_id = ? ORDER BY rowid DESC LIMIT 1",
                               (tenant_id,)).fetchone()
        prev_hash = prev["hash"] if prev else GENESIS
        ts = now()
        h = _hash(prev_hash, tenant_id, kind, amount, balance, held, job_id, ts)
        self.db.execute(
            "INSERT INTO ledger (entry_id, tenant_id, ts, kind, amount, balance_after, held_after,"
            " job_id, memo, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"l_{uuid.uuid4().hex[:26]}", tenant_id, ts, kind, amount, balance, held, job_id,
             memo, prev_hash, h),
        )
        self.db.execute("UPDATE tenants SET credit_microusd = ?, credit_held_microusd = ? WHERE tenant_id = ?",
                        (balance, held, tenant_id))
        return {"entry_id": f"l_{h[:8]}", "kind": kind, "amount": amount, "balance_after": balance,
                "held_after": held, "hash": h}

    # ------------------------------------------------------------------ operasi
    def grant_trial(self, tenant_id: str, amount_microusd: int, memo: str = "trial credit") -> dict:
        """Kredit uji dicatat sebagai entri ledger, bukan angka awal diam-diam — agar saldo bisa diaudit."""
        if amount_microusd <= 0:
            return {"skipped": True}
        self.db.execute("BEGIN IMMEDIATE")
        try:
            entry = self._append(tenant_id, "adjust", amount_microusd, None, memo)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return entry

    def topup(self, tenant_id: str, amount_microusd: int, memo: str = "topup") -> dict:
        if not isinstance(amount_microusd, int) or amount_microusd <= 0:
            raise BillingError(400, "invalid_amount", "topup harus int > 0")
        if amount_microusd > 1_000_000 * MICRO:
            raise BillingError(400, "invalid_amount", "topup melebihi $1.000.000 per transaksi")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            entry = self._append(tenant_id, "topup", amount_microusd, None, memo)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return entry

    def reserve(self, tenant_id: str, job_id: str, amount_microusd: int, memo: str = "hold job") -> dict:
        """Pesan kredit untuk job. Dipanggil di dalam transaksi pembuatan job (tanpa commit sendiri)."""
        row = self._tenant(tenant_id)
        if row["credit_microusd"] < amount_microusd:
            raise BillingError(
                402, "insufficient_credit",
                f"kredit {row['credit_microusd']} μUSD < perkiraan biaya {amount_microusd} μUSD; lakukan topup")
        return self._append(tenant_id, "hold", -amount_microusd, job_id, memo)

    def settle(self, tenant_id: str, job_id: str, tokens_used: int, plan: str,
               hold_microusd: int) -> dict:
        """Tutup job: lepas pesanan, tagih pemakaian nyata (tidak pernah melebihi pesanan)."""
        existing = self.db.execute("SELECT * FROM job_charges WHERE job_id = ?", (job_id,)).fetchone()
        if existing:
            return {"job_id": job_id, "micro_usd": existing["micro_usd"], "replayed": True,
                    "tokens_used": existing["tokens_used"]}
        charge = min(price_tokens(tokens_used, plan), hold_microusd)
        self._append(tenant_id, "release", hold_microusd, job_id, "lepas pesanan")
        if charge:
            self._append(tenant_id, "charge", -charge, job_id, f"{tokens_used} token @ {plan}")
        self.db.execute("INSERT INTO job_charges VALUES (?,?,?,?,?,?)",
                        (job_id, tenant_id, charge, tokens_used, plan, now()))
        return {"job_id": job_id, "micro_usd": charge, "tokens_used": tokens_used, "replayed": False}

    def release(self, tenant_id: str, job_id: str, hold_microusd: int, reason: str = "job tidak dijalankan") -> dict:
        existing = self.db.execute("SELECT 1 FROM job_charges WHERE job_id = ?", (job_id,)).fetchone()
        if existing:
            return {"job_id": job_id, "released": False, "reason": "sudah diselesaikan"}
        self._append(tenant_id, "release", hold_microusd, job_id, reason)
        self.db.execute("INSERT INTO job_charges VALUES (?,?,?,?,?,?)",
                        (job_id, tenant_id, 0, 0, self._tenant(tenant_id)["plan"], now()))
        return {"job_id": job_id, "released": True, "micro_usd": hold_microusd}

    def refund(self, tenant_id: str, amount_microusd: int, memo: str) -> dict:
        if amount_microusd <= 0:
            raise BillingError(400, "invalid_amount", "refund harus > 0")
        return self._append(tenant_id, "refund", amount_microusd, None, memo)

    def ledger(self, tenant_id: str, limit: int = 100) -> list[dict]:
        self._tenant(tenant_id)
        rows = self.db.execute(
            "SELECT entry_id, ts, kind, amount, balance_after, held_after, job_id, memo, hash"
            " FROM ledger WHERE tenant_id = ? ORDER BY rowid DESC LIMIT ?",
            (tenant_id, max(1, min(limit, 500)))).fetchall()
        return [dict(r) for r in rows]

    def verify_chain(self, tenant_id: str) -> dict:
        """Hitung ulang seluruh rantai hash. Gagal = ledger pernah disunting di luar aplikasi."""
        rows = self.db.execute(
            "SELECT * FROM ledger WHERE tenant_id = ? ORDER BY rowid", (tenant_id,)).fetchall()
        prev = GENESIS
        balance = held = 0
        for r in rows:
            expected = _hash(prev, r["tenant_id"], r["kind"], r["amount"], r["balance_after"],
                             r["held_after"], r["job_id"], r["ts"])
            if r["prev_hash"] != prev or r["hash"] != expected:
                return {"ok": False, "broken_at": r["entry_id"], "entries": len(rows)}
            balance += r["amount"]
            if r["kind"] == "hold":
                held += -r["amount"]
            elif r["kind"] == "release":
                held -= r["amount"]
            prev = r["hash"]
        tenant = self._tenant(tenant_id)
        return {"ok": balance == tenant["credit_microusd"] and held == tenant["credit_held_microusd"],
                "entries": len(rows), "balance": balance, "held": held}

    # ------------------------------------------------------------------ tagihan
    def issue_invoice(self, tenant_id: str, period_start: str, period_end: str) -> dict:
        """Tagihan periode = jumlah `charge` pada rentang. Idempoten per (tenant, periode)."""
        self._tenant(tenant_id)
        existing = self.db.execute(
            "SELECT * FROM invoices WHERE tenant_id = ? AND period_start = ? AND period_end = ?",
            (tenant_id, period_start, period_end)).fetchone()
        if existing:
            return {**dict(existing), "replayed": True}
        rows = self.db.execute(
            "SELECT job_id, micro_usd, tokens_used FROM job_charges WHERE tenant_id = ? AND ts >= ? AND ts < ?"
            " ORDER BY ts", (tenant_id, period_start, period_end)).fetchall()
        lines = [{"job_id": r["job_id"], "micro_usd": r["micro_usd"], "tokens": r["tokens_used"]} for r in rows]
        total = sum(line["micro_usd"] for line in lines)
        snapshot = json.dumps({"tenant_id": tenant_id, "period_start": period_start,
                               "period_end": period_end, "lines": lines, "total_microusd": total},
                              sort_keys=True, separators=(",", ":"))
        prev = self.db.execute("SELECT hash FROM invoices WHERE tenant_id = ? ORDER BY rowid DESC LIMIT 1",
                               (tenant_id,)).fetchone()
        prev_hash = prev["hash"] if prev else GENESIS
        h = hashlib.sha256(f"{prev_hash}|{snapshot}".encode()).hexdigest()
        iid = f"inv_{uuid.uuid4().hex[:20]}"
        self.db.execute(
            "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (iid, tenant_id, period_start, period_end, total, len(lines), "issued", snapshot,
             prev_hash, h, now()))
        self.db.commit()
        return {"invoice_id": iid, "tenant_id": tenant_id, "period_start": period_start,
                "period_end": period_end, "total_microusd": total, "jobs": len(lines),
                "status": "issued", "hash": h, "lines": lines, "replayed": False}

    def invoices(self, tenant_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT invoice_id, period_start, period_end, total_microusd, jobs, status, hash, created_at"
            " FROM invoices WHERE tenant_id = ? ORDER BY rowid DESC", (tenant_id,)).fetchall()
        return [dict(r) for r in rows]

    def verify_invoice(self, invoice_id: str) -> dict:
        row = self.db.execute("SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,)).fetchone()
        if row is None:
            raise BillingError(404, "invoice_not_found", "invoice tidak ada")
        expected = hashlib.sha256(f"{row['prev_hash']}|{row['snapshot']}".encode()).hexdigest()
        snap = json.loads(row["snapshot"])
        # Kolom ringkasan harus sama dengan isi snapshot: kalau total diubah langsung di DB, ini gagal.
        consistent = (snap["total_microusd"] == row["total_microusd"]
                      and len(snap["lines"]) == row["jobs"])
        return {"ok": expected == row["hash"] and consistent, "invoice_id": invoice_id,
                "total_microusd": row["total_microusd"]}

    def revenue(self) -> dict:
        row = self.db.execute("SELECT COALESCE(SUM(micro_usd),0) s, COUNT(*) n FROM job_charges").fetchone()
        return {"charged_microusd": row["s"], "jobs": row["n"]}
