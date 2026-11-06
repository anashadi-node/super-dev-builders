"""Uji penyusun probe DID: matriks peran x halaman harus diturunkan dari sumber target.

Regresi yang dijaga: parser regex lama berhenti di blok MappingProxyType pertama
(``PAGE_ROLE_BY_CANONICAL``) sehingga PAGE_ROLES terbaca kosong — probe izin jadi 0
dan handoff menulis klaim "0 halaman" tanpa satu pun error.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import did_probe_config as dpc

SUMBER = '''
ALL_ROLES = ROLES

PAGE_ROLE_BY_CANONICAL: Mapping[str, str] = MappingProxyType(
    {
        "owner": "owner",
        "gm": "gm",
        "reservation_agent": "reservation",
    }
)

PAGE_ROLES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "command_center": ALL_ROLES,
        "cases": ("reservation", "operations", "owner", "auditor", "gm"),
        "finance": ("finance", "owner", "gm"),
        "audit": ("owner", "auditor", "gm"),
        "case_detail": ("reservation", "operations", "owner", "auditor", "gm"),
        "error": ALL_ROLES,
    }
)

NAV: tuple[tuple[str, str], ...] = (
    ("command_center", "/"),
    ("cases", "/cases"),
    ("finance", "/finance"),
    ("audit", "/audit"),
)
'''


@pytest.fixture()
def sumber(tmp_path: Path) -> Path:
    root = tmp_path / "target"
    (root / "src").mkdir(parents=True)
    (root / "src" / "dashboard.py").write_text(SUMBER, encoding="utf-8")
    return root


def test_matriks_dibaca_dari_page_roles_bukan_blok_lain(sumber: Path):
    peta, rute = dpc.baca_matriks(str(sumber))

    assert set(peta) == {"command_center", "cases", "finance", "audit", "case_detail", "error"}
    assert peta["finance"] == ["finance", "owner", "gm"]
    assert len(peta["command_center"]) == 6  # ALL_ROLES diekspansi ke 6 peran
    assert rute == {"command_center": "/", "cases": "/cases",
                    "finance": "/finance", "audit": "/audit"}


def test_susun_mencakup_seluruh_pasangan_peran_rute(sumber: Path):
    peta, rute = dpc.baca_matriks(str(sumber))
    ports = {p: 8300 + i for i, p in enumerate(dpc.PERAN)}
    cfg = dpc.susun(peta, rute, ports, {p: f"tok-{p}" for p in dpc.PERAN}, None, "uji")

    izin = sum(len(r["pages"]) for r in cfg["roles"])
    tolak = sum(len(r["denied"]) for r in cfg["roles"])
    pasangan = len(dpc.PERAN) * len(rute)

    assert izin + tolak == pasangan, "setiap pasangan peran x rute harus diprobe sekali"
    assert tolak == pasangan - izin
    assert cfg["roles"][0]["auth"]["value"].startswith("Bearer tok-")


def test_halaman_tanpa_rute_tidak_menggelembungkan_izin(sumber: Path):
    peta, rute = dpc.baca_matriks(str(sumber))
    ports = {p: 8300 + i for i, p in enumerate(dpc.PERAN)}
    cfg = dpc.susun(peta, rute, ports, {p: "t" for p in dpc.PERAN}, "demo_case_1", "uji")

    owner = next(r for r in cfg["roles"] if r["name"] == "owner")
    # case_detail tidak punya rute NAV, jadi hanya muncul lewat --case-id
    assert "/cases/demo_case_1" in owner["pages"]
    assert "/cases" in owner["pages"]
    assert all(p.startswith("/") for r in cfg["roles"] for p in r["pages"])


def test_case_id_hanya_ditambahkan_untuk_peran_berhak(sumber: Path):
    peta, rute = dpc.baca_matriks(str(sumber))
    ports = {p: 8300 + i for i, p in enumerate(dpc.PERAN)}
    cfg = dpc.susun(peta, rute, ports, {p: "t" for p in dpc.PERAN}, "demo_case_1", "uji")

    finance = next(r for r in cfg["roles"] if r["name"] == "finance")
    assert "/cases/demo_case_1" not in finance["pages"]


def test_config_hasil_ditulis_dan_dapat_dibaca(tmp_path: Path, sumber: Path):
    out = tmp_path / "probes.json"
    kode = dpc.main([
        "--source", str(sumber), "--out", str(out), "--label", "uji",
        "--ports", "8300-8305", "--token-env-prefix", "UJI_TOK_",
    ])
    assert kode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["roles"]) == 6
    assert data["empty_markers"]
    assert data["anon"][0]["expect_status"] == 401
