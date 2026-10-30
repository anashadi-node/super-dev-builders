"""Audit log append-only berantai hash (PRD #1 bagian 7).

Setiap entri mencatat: waktu UTC, aktor, alat, target, aksi, hasil, detail,
hash entri sebelumnya (prev_hash) dan hash isinya sendiri (hash). Rantai
diverifikasi ulang; satu baris diubah/dihapus = GAGAL (fail-closed).

Kode keluar: 0 = OK, 1 = rantai rusak / tidak valid, 2 = alat/berkas bermasalah.

Pemakaian:
  python3 tools/audit-log.py append --log audit/audit-log.jsonl \
      --actor D1 --tool rea --target e1-app --action analyze --result ok
  python3 tools/audit-log.py verify --log audit/audit-log.jsonl
"""

import argparse
import datetime
import hashlib
import json
import pathlib
import sys

GENESIS = "0" * 64


def _hash_line(obj: dict) -> str:
    payload = {k: v for k, v in obj.items() if k != "hash"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def append(log: pathlib.Path, entry: dict) -> dict:
    prev = GENESIS
    if log.exists():
        lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines:
            last = json.loads(lines[-1])  # JSON rusak -> exception -> keluar 2
            if _hash_line(last) != last.get("hash"):
                raise ValueError("entri terakhir tidak valid — append ditolak (fail-closed)")
            prev = last["hash"]
    record = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              **entry, "prev_hash": prev}
    record["hash"] = _hash_line(record)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return record


def verify(log: pathlib.Path):
    if not log.exists():
        return False, "berkas log tidak ada"
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return False, "log kosong"
    prev = GENESIS
    for i, ln in enumerate(lines, 1):
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError as exc:
            return False, f"baris {i}: JSON rusak ({exc})"
        if obj.get("prev_hash") != prev:
            return False, f"baris {i}: prev_hash tidak cocok (rantai terputus)"
        if _hash_line(obj) != obj.get("hash"):
            return False, f"baris {i}: hash isi tidak cocok (baris diubah)"
        prev = obj["hash"]
    return True, f"{len(lines)} entri, rantai utuh"


def main() -> int:
    ap = argparse.ArgumentParser(description="audit log append-only berantai hash")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap_ = sub.add_parser("append")
    ap_.add_argument("--log", required=True)
    ap_.add_argument("--actor", required=True)
    ap_.add_argument("--tool", required=True)
    ap_.add_argument("--target", required=True)
    ap_.add_argument("--action", required=True)
    ap_.add_argument("--result", required=True)
    ap_.add_argument("--detail", default="")
    apv = sub.add_parser("verify")
    apv.add_argument("--log", required=True)
    a = ap.parse_args()

    log = pathlib.Path(a.log)
    try:
        if a.cmd == "append":
            rec = append(log, {"actor": a.actor, "tool": a.tool, "target": a.target,
                               "action": a.action, "result": a.result, "detail": a.detail})
            print(f"AUDIT ditambahkan: {rec['hash'][:16]} -> {log}")
            return 0
        ok, msg = verify(log)
        print(f"AUDIT {'OK' if ok else 'GAGAL'}: {msg}")
        return 0 if ok else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"AUDIT TIDAK DIVERIFIKASI: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
