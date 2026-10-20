"""Repoyu yetenek olarak kurma ve skill ek dosyalarını okuma (ağ yok: git sahtelenir)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.tools import capability_install
from fusion_cli.tools.capabilities import CapabilityRegistry, skill_file, skill_files
from fusion_cli.tools.capability_install import CapabilityInstallError, install, parse_repo


@pytest.mark.parametrize(
    "adres",
    [
        "http://github.com/a/b",
        "https://gitlab.com/a/b",
        "https://github.com/a",
        "https://github.com/a/b/tree/main",
        "file:///etc",
        "https://github.com/a/b; rm -rf ~",
    ],
)
def test_yalniz_github_repo_adresi_kabul_edilir(adres):
    with pytest.raises(CapabilityInstallError):
        parse_repo(adres)


def test_github_adresi_ayrisir():
    assert parse_repo("https://github.com/kaomei/stickman-video-director.git") == (
        "kaomei",
        "stickman-video-director",
    )


def _sahte_git(monkeypatch):
    cagrilar: list[list[str]] = []

    def _git(args, *, cwd, timeout):
        cagrilar.append(args)
        if args[0] == "clone":
            hedef = Path(args[-1])
            skill = hedef / "skills" / "yonet"
            (skill / "references").mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: yonet\ndescription: video yönet\n---\nÖnce references/a.md oku.",
                encoding="utf-8",
            )
            (skill / "references" / "a.md").write_text("ek bilgi", encoding="utf-8")
            (skill / "references" / "resim.png").write_bytes(b"\x89PNG")
            (hedef / "setup.sh").write_text("rm -rf ~", encoding="utf-8")
            return ""
        return "abc123def456\n"

    monkeypatch.setattr(capability_install, "_git", _git)
    return cagrilar


def test_kurulum_betik_calistirmaz_commiti_kaydeder_ve_skill_kesfedilir(tmp_path, monkeypatch):
    cagrilar = _sahte_git(monkeypatch)
    monkeypatch.setattr("fusion_cli.tools.capabilities.capabilities_dir", lambda: tmp_path)

    kurulan = install("https://github.com/kaomei/video", tmp_path)

    assert [arg[0] for arg in cagrilar] == ["clone", "rev-parse"]
    assert kurulan.commit == "abc123def456"
    assert kurulan.skills == ("skills/yonet",)
    skill = CapabilityRegistry(tmp_path / "ev", tmp_path / "kok").get_skill("yonet")
    assert skill is not None and skill.source == "kurulu"


def test_ayni_yetenek_iki_kez_kurulmaz(tmp_path, monkeypatch):
    _sahte_git(monkeypatch)
    install("https://github.com/kaomei/video", tmp_path)

    with pytest.raises(CapabilityInstallError, match="zaten kurulu"):
        install("https://github.com/kaomei/video", tmp_path)


def test_skill_ek_dosyalari_listelenir_ikili_ve_disari_kacis_verilmez(tmp_path, monkeypatch):
    _sahte_git(monkeypatch)
    kurulan = install("https://github.com/kaomei/video", tmp_path)
    skill_md = kurulan.path / "skills" / "yonet" / "SKILL.md"

    assert skill_files(skill_md) == ["references/a.md"]
    assert skill_file(skill_md, "references/a.md") is not None
    assert skill_file(skill_md, "references/resim.png") is None
    assert skill_file(skill_md, "../../setup.sh") is None
