"""Depo haritası gerçekten modele ulaşır.

Denetlendi (6 Eylül): `core/repo_map.py` yazıldı ve test edildi ama hiçbir yerden
ÇAĞRILMIYORDU — yani model haritayı hiç görmüyordu. Modülün var olması, Fusion'ın
onu kullanabildiği anlamına gelmez.

Harita görev TÜRÜNE bakmaz (bkz. `repo_context.repo_map_block` docstring'i):
sohbet turunda hiç eklenmeme kararı `loop.py`'de (`chat_mode` kontrolü) verilir,
bu modülün sorumluluğu değildir; bkz.
`tests/test_single_loop_routing.py::test_depo_haritasi_gorev_turunden_bagimsiz_ve_sohbette_yok`.
"""

from __future__ import annotations

from fusion_cli.engines.agent.repo_context import repo_map_block


def _proje(tmp_path):
    (tmp_path / "hesap.py").write_text("def topla(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "rapor.py").write_text(
        "from hesap import topla\n\n\ndef ozet(x):\n    return topla(x, 1)\n", encoding="utf-8"
    )
    return tmp_path


def test_kod_iceren_projede_harita_eklenir(tmp_path):
    blok = repo_map_block(_proje(tmp_path))

    assert "hesap.py" in blok
    assert "topla" in blok


def test_kod_yoksa_bos_doner(tmp_path):
    (tmp_path / "notlar.md").write_text("# not\n", encoding="utf-8")

    assert repo_map_block(tmp_path) == ""


def test_blok_baslikla_gelir(tmp_path):
    blok = repo_map_block(_proje(tmp_path))

    assert blok.splitlines()[0].startswith("#")
