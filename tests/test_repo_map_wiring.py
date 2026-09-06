"""Depo haritası gerçekten modele ulaşır.

Denetlendi (6 Eylül): `core/repo_map.py` yazıldı ve test edildi ama hiçbir yerden
ÇAĞRILMIYORDU — yani model haritayı hiç görmüyordu. Modülün var olması, Fusion'ın
onu kullanabildiği anlamına gelmez.

Harita yalnız çok adımlı işlerde ve KÖKTE kod varsa eklenir: "merhaba" sorusuna
sembol listesi iliştirmek bağlamı boşuna şişirir.
"""

from __future__ import annotations

from fusion_cli.engines.agent.classify import TaskKind
from fusion_cli.engines.agent.repo_context import repo_map_block


def _proje(tmp_path):
    (tmp_path / "hesap.py").write_text("def topla(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "rapor.py").write_text(
        "from hesap import topla\n\n\ndef ozet(x):\n    return topla(x, 1)\n", encoding="utf-8"
    )
    return tmp_path


def test_kod_iceren_projede_harita_eklenir(tmp_path):
    blok = repo_map_block(_proje(tmp_path), TaskKind.FEATURE)

    assert "hesap.py" in blok
    assert "topla" in blok


def test_basit_sohbette_harita_eklenmez(tmp_path):
    """Sohbet turu sembol listesi taşımamalı: bağlam bedava değil."""
    assert repo_map_block(_proje(tmp_path), TaskKind.GENERAL) == ""


def test_kod_yoksa_bos_doner(tmp_path):
    (tmp_path / "notlar.md").write_text("# not\n", encoding="utf-8")

    assert repo_map_block(tmp_path, TaskKind.FEATURE) == ""


def test_blok_baslikla_gelir(tmp_path):
    blok = repo_map_block(_proje(tmp_path), TaskKind.BUGFIX)

    assert blok.splitlines()[0].startswith("#")
