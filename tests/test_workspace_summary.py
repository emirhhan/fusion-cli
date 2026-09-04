"""Çalışma alanının TÜRÜ modele söylenmeli."""

from __future__ import annotations

from fusion_cli.engines.agent.project_instructions import workspace_summary


def test_godot_projesi_tanitilir(tmp_path):
    """Ölçüldü: içinde `project.godot` olan bir klasörde, 'platform oyunu yap'
    denince model HTML/JS oyunu yazdı.

    Klasör açıkça bir Godot projesiydi ve Fusion bunu zaten hesaplıyordu
    (`project_kinds`), ama modele hiç söylemiyordu. Model `list_dir` ile tahmin
    etmek zorunda kaldı ve yanlış yığınla yeni bir proje kurdu.
    """
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")

    ozet = workspace_summary(tmp_path)

    assert "godot" in ozet.lower()
    assert "project.godot" in ozet


def test_birden_cok_tur_birlikte_bildirilir(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    ozet = workspace_summary(tmp_path)

    assert "node" in ozet.lower() and "python" in ozet.lower()


def test_taninmayan_dizinde_bos_doner(tmp_path):
    """Uydurma bir tanı, modeli yanlış yığına iter; bilinmiyorsa susmak doğrudur."""
    assert workspace_summary(tmp_path) == ""


def test_ozet_proje_talimatiyla_birlikte_verilir(tmp_path):
    from fusion_cli.engines.agent.project_instructions import read_all_instructions

    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")

    metin = read_all_instructions(tmp_path, None)

    assert "godot" in metin.lower()
