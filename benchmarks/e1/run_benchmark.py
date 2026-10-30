"""Runner benchmark E1: jalankan uji buta pada 3 endpoint, hitung metrik, tulis JSON.

Pemakaian: python3 benchmarks/e1/run_benchmark.py \
    --target http://127.0.0.1:8110 --spec http://127.0.0.1:8111 --kontrol http://127.0.0.1:8112

Runner TIDAK menjalankan server (tanpa subprocess) — server dinyalakan terpisah,
supaya alat ini bebas dari permukaan eksekusi proses.
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import checks


def score(base):
    res = checks.run(base)
    passed = sum(1 for r in res if r["pass"])
    return {"base": base, "passed": passed, "total": len(res), "detail": res}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--kontrol", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    t = score(a.target)
    s = score(a.spec)
    k = score(a.kontrol)

    # Recall = perilaku target yang berhasil direproduksi replika ( terhadap total fitur target )
    recall = s["passed"] / t["total"] if t["total"] else 0.0
    # Presisi spesifikasi = klaim SPEC yang benar tentang target (uji target lulus / total klaim)
    presisi_spec = t["passed"] / t["total"] if t["total"] else 0.0
    delta = (s["passed"] - k["passed"]) / t["total"] if t["total"] else 0.0

    out = {
        "target": t, "replica_spec": s, "kontrol_naif": k,
        "metrik": {"recall_replika": round(recall, 4),
                   "presisi_spec": round(presisi_spec, 4),
                   "paritas_kontrol": round(k["passed"] / t["total"], 4) if t["total"] else 0,
                   "delta_spec_minus_kontrol": round(delta, 4)},
    }
    text = json.dumps(out, indent=1, ensure_ascii=False)
    if a.out:
        pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.out).write_text(text + "\n")
    print(text)
