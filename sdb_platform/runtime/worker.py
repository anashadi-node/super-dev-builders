"""Worker SDB — klaim job atomik, eksekusi ber-budget, pemulihan lease, penyelesaian + tagihan.

Prinsip yang dipegang:
- **Klaim atomik**: satu job hanya bisa diklaim satu worker (SELECT+UPDATE di dalam `BEGIN IMMEDIATE`,
  `WHERE status='queued'` + cek rowcount). Tanpa ini, dua worker bisa menagih dua kali.
- **Lease, bukan lock selamanya**: worker mati -> lease kedaluwarsa -> job diantre ulang sampai
  `max_attempts`, lalu `failed` dan pesanan kredit dilepas.
- **Budget ditegakkan dua arah**: token (dipotong ke budget) dan waktu (diukur `monotonic`).
- **Kegagalan tidak menagih**: status failed/cancelled -> `release`, bukan `charge`.

Worker berjalan lintas tenant (peran sistem) — berbeda dari API tenant yang selalu ber-`tenant_id`.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable

from ..control_plane.store import ControlPlaneError, Store


@dataclass
class ExecutionResult:
    status: str = "succeeded"
    tokens_used: int = 0
    artifacts: list[dict] = field(default_factory=list)
    gate_verdict: str | None = None
    error: str | None = None


def echo_executor(job: dict) -> ExecutionResult:
    """Executor deterministik tanpa jaringan: cukup untuk menguji alur penuh & billing.

    Pemakaian token diturunkan dari panjang target_ref supaya uji bisa memprediksi biaya persis.
    """
    tokens = 1000 + 37 * len(job["target_ref"])
    return ExecutionResult(
        status="succeeded",
        tokens_used=min(tokens, job["budget"]["tokens"]),
        gate_verdict="PASS",
    )


def failing_executor(job: dict) -> ExecutionResult:
    raise RuntimeError("executor sengaja gagal (uji pemulihan)")


class Worker:
    def __init__(self, store: Store, executor: Callable[[dict], ExecutionResult],
                 worker_id: str | None = None, lease_seconds: int = 120, max_attempts: int = 3):
        if lease_seconds < 10:
            raise ValueError("lease_seconds minimal 10")
        if max_attempts < 1:
            raise ValueError("max_attempts minimal 1")
        self.store = store
        self.executor = executor
        self.worker_id = worker_id or f"w_{socket.gethostname()}_{os.getpid()}"
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts

    # ------------------------------------------------------------------ lease
    def reap_expired(self) -> list[dict]:
        return self.store.reap_expired_leases(self.max_attempts)

    def run_once(self) -> dict:
        job = self.store.claim_next_job(self.worker_id, self.lease_seconds)
        if job is None:
            return {"claimed": None, "worker_id": self.worker_id}
        started = time.monotonic()
        try:
            result = self.executor(job)
            if not isinstance(result, ExecutionResult):
                raise TypeError("executor harus mengembalikan ExecutionResult")
            elapsed = time.monotonic() - started
            status = result.status
            tokens = max(0, int(result.tokens_used))
            if tokens > job["budget"]["tokens"]:
                status, tokens = "budget_exceeded", job["budget"]["tokens"]
            fresh = self.store.get_job(job["tenant_id"], job["job_id"])
            if fresh["cancel_requested"]:
                status, tokens = "cancelled", 0
            if elapsed > job["budget"]["seconds"]:
                status, tokens = "budget_exceeded", min(tokens, job["budget"]["tokens"])
                result.error = f"wall-clock {elapsed:.1f}s > budget {job['budget']['seconds']}s"
            done = self.store.finish_job(job["tenant_id"], job["job_id"], status, tokens,
                                         result.gate_verdict, result.error)
            artifacts = 0
            for art in result.artifacts:
                self.store.register_artifact(
                    job["tenant_id"], job["job_id"], art["kind"], art["sha256"], art["size"],
                    art["redaction_status"], art["retention_until"], art["uri"], art.get("media_type"))
                artifacts += 1
            return {"claimed": job["job_id"], "status": done["status"], "tokens_used": tokens,
                    "artifacts": artifacts, "elapsed_s": round(elapsed, 3),
                    "worker_id": self.worker_id}
        except ControlPlaneError as exc:
            # Kegagalan domain (mis. artefak ditolak) tetap harus menutup job, jangan menggantung.
            err = f"{exc.code}: {exc.message}"
        except Exception as exc:  # executor apa pun tidak boleh mematikan worker
            err = f"{type(exc).__name__}: {exc}"
            traceback.print_exc(limit=3, file=sys.stderr)
        try:
            done = self.store.finish_job(job["tenant_id"], job["job_id"], "failed", 0, None, err[:500])
        except ControlPlaneError:
            done = {"status": "lease_lost", "job_id": job["job_id"]}
        return {"claimed": job["job_id"], "status": done["status"], "error": err,
                "worker_id": self.worker_id}

    def run_forever(self, poll_seconds: float = 2.0, max_jobs: int | None = None) -> None:
        done = 0
        while max_jobs is None or done < max_jobs:
            self.reap_expired()
            summary = self.run_once()
            if summary.get("claimed"):
                done += 1
                print(f"[{self.worker_id}] {summary}", flush=True)
            else:
                time.sleep(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SDB worker (Fase 2b)")
    ap.add_argument("--db", default=os.path.expanduser("~/super-dev-builders/data/control.db"))
    ap.add_argument("--once", action="store_true", help="kerjakan paling banyak satu job lalu keluar")
    ap.add_argument("--max-jobs", type=int, default=None)
    ap.add_argument("--poll", type=float, default=2.0)
    ap.add_argument("--lease-seconds", type=int, default=120)
    ap.add_argument("--worker-id", default=None)
    args = ap.parse_args(argv)
    worker = Worker(Store(args.db), echo_executor, args.worker_id, args.lease_seconds)
    if args.once:
        print(worker.run_once())
        return 0
    worker.run_forever(args.poll, args.max_jobs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
