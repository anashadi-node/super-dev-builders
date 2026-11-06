#!/usr/bin/python3
"""DID suite — jalankan semua benchmark yang punya label, dengan ambang gagal jelas.

Kenapa alat terpisah, bukan satu perintah `did-bench` berulang: skor yang hanya
dibaca manusia tidak mencegah kemunduran. Suite ini memberi exit code, jadi CI
bisa menolak PR yang menurunkan recall atau memunculkan klaim tanpa bukti.

Sumber handoff (urut prioritas):
  1. benchmarks/<target>/handoff.json  — snapshot beku, ikut git, dipakai CI
  2. runs/<target>/did/handoff.json    — hasil kerja lokal (gitignored)

Pemakaian: python3 scripts/did_suite.py [--min-recall 0.9] [--min-precision 0.9]
Exit: 0 semua lolos, 1 ada target gagal, 2 tidak ada benchmark.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import did_validate  # noqa: E402


def handoff_for(target: str, root: str = ROOT) -> str | None:
    beku = os.path.join(root, "benchmarks", target, "handoff.json")
    if os.path.isfile(beku):
        return beku
    lokal = os.path.join(root, "runs", target, "did", "handoff.json")
    return lokal if os.path.isfile(lokal) else None


def jalankan(min_recall: float, min_precision: float, root: str = ROOT) -> dict:
    hasil, gagal = [], 0
    for truth_path in sorted(glob.glob(os.path.join(root, "benchmarks", "*", "ground_truth.json"))):
        target = os.path.basename(os.path.dirname(truth_path))
        handoff = handoff_for(target, root)
        if not handoff:
            hasil.append({"target": target, "status": "SKIP", "reason": "handoff tidak ada"})
            continue
        truth = json.load(open(truth_path, encoding="utf-8"))
        hand = json.load(open(handoff, encoding="utf-8"))
        skor = did_validate.bench(hand, truth)
        alasan = []
        if skor["hallucination_rate"] > 0:
            alasan.append(f"halusinasi {skor['hallucination_rate']:.3f} > 0")
        if skor["recall"] < min_recall:
            alasan.append(f"recall {skor['recall']:.3f} < {min_recall}")
        if skor["precision"] < min_precision:
            alasan.append(f"presisi {skor['precision']:.3f} < {min_precision}")
        status = "FAIL" if alasan else "PASS"
        if alasan:
            gagal += 1
        rel = os.path.relpath(handoff, root)
        hasil.append({"target": target, "status": status, "handoff": rel,
                      "precision": skor["precision"], "recall": skor["recall"], "f1": skor["f1"],
                      "extras": len(skor["extras"]), "hallucinated": len(skor["hallucinated"]),
                      "alasan": alasan})
    return {"results": hasil, "failed": gagal, "min_recall": min_recall, "min_precision": min_precision}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DID benchmark suite")
    ap.add_argument("--min-recall", type=float, default=0.9)
    ap.add_argument("--min-precision", type=float, default=0.9)
    ap.add_argument("--json-out", default=os.path.join(ROOT, "reports", "did-suite.json"))
    args = ap.parse_args(argv)

    data = jalankan(args.min_recall, args.min_precision)
    kalau = [r for r in data["results"] if r["status"] != "SKIP"]
    if not kalau:
        print("DID suite: tidak ada benchmark dengan label di benchmarks/*/ground_truth.json")
        return 2

    os.makedirs(os.path.dirname(args.json_out), exist_ok=True)
    with open(args.json_out, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1, ensure_ascii=False)

    print(f"{'target':<15}{'status':<8}{'P':>7}{'R':>7}{'F1':>7}{'extras':>8}{'halusinasi':>11}")
    for row in data["results"]:
        if row["status"] == "SKIP":
            print(f"{row['target']:<15}{'SKIP':<8}  {row['reason']}")
            continue
        print(f"{row['target']:<15}{row['status']:<8}{row['precision']:>7.3f}{row['recall']:>7.3f}"
              f"{row['f1']:>7.3f}{row['extras']:>8}{row['hallucinated']:>11}")
        for alasan in row["alasan"]:
            print(f"  - {alasan}")
    print(f"ambang: recall >= {args.min_recall}, presisi >= {args.min_precision}, halusinasi = 0"
          f" | gagal {data['failed']}/{len(kalau)}")
    return 0 if data["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
