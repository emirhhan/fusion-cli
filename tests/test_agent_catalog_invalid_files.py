"""Claude Code'un atladığı ajan dosyaları kataloğa girmez (#19, #41)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.tools.capabilities import CapabilityRegistry


def _write(root: Path, filename: str, text: str) -> None:
    folder = root / ".claude" / "agents"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_text(text, encoding="utf-8")


def _project_agents(root: Path) -> set[str]:
    registry = CapabilityRegistry(root / "ev", root)
    return {item.name for item in registry.agents() if item.source != "fusion"}


@pytest.mark.parametrize(
    "text",
    [
        "---\ndescription: adı yok\n---\nBelge.",
        "\n---\nname: bosluklu\ndescription: ilk satır boş\n---\nGövde.",
        "  ---\nname: girintili\ndescription: girintili açılış\n---\nGövde.",
        "---\nname: -tire\ndescription: tireyle başlar\n---\nGövde.",
        "---\nname: a:b\ndescription: iki nokta\n---\nGövde.",
        f"---\nname: {'x' * 257}\ndescription: çok uzun\n---\nGövde.",
        "---\nname: aciklamasiz\n---\nGövde.",
        "Düz belge, frontmatter yok.",
    ],
)
def test_gecersiz_ajan_dosyasi_atlanir(tmp_path: Path, text: str) -> None:
    _write(tmp_path, "ajan.md", text)

    assert _project_agents(tmp_path) == set()


def test_gecerli_ajan_dosya_adindan_degil_name_alanindan_kimlik_alir(tmp_path: Path) -> None:
    _write(tmp_path, "dosya-adi.md", "---\nname: denetci\ndescription: inceler\n---\nİncele.")

    assert _project_agents(tmp_path) == {"denetci"}


def test_ajan_dosyasinin_icerigi_degisince_katalog_yeniden_yuklenir(tmp_path: Path) -> None:
    import os

    _write(tmp_path, "denetci.md", "---\nname: denetci\ndescription: eski\n---\nİncele.")
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path)
    first = registry.get_agent("denetci")
    assert first is not None and first.description == "eski"
    path = tmp_path / ".claude" / "agents" / "denetci.md"
    folder_stat = path.parent.stat()

    path.write_text("---\nname: denetci\ndescription: yeni\n---\nİncele.", encoding="utf-8")
    later = folder_stat.st_mtime_ns + 5_000_000_000
    os.utime(path, ns=(later, later))
    # Dizin mtime'ı değişmedi: yalnız dosyanın kendi içeriği/mtime'ı değişti (#20).
    os.utime(path.parent, ns=(folder_stat.st_atime_ns, folder_stat.st_mtime_ns))

    second = registry.get_agent("denetci")
    assert second is not None and second.description == "yeni"


def test_codex_ve_kurulu_ajanlar_claude_kapsamini_belirsizlestirmez(tmp_path: Path) -> None:
    """Ek kaynaklar Claude kapsamlarının altındadır; aynı ad belirsizlik üretmez (#38)."""
    home = tmp_path / "ev"
    user = home / ".claude" / "agents"
    user.mkdir(parents=True)
    (user / "denetci.md").write_text(
        "---\nname: denetci\ndescription: kullanıcı\n---\nKullanıcı.", encoding="utf-8"
    )
    codex = home / ".codex" / "agents"
    codex.mkdir(parents=True)
    (codex / "denetci.md").write_text(
        "---\nname: denetci\ndescription: codex\n---\nCodex.", encoding="utf-8"
    )

    agent = CapabilityRegistry(home, tmp_path).get_agent("denetci")

    assert agent is not None and agent.description == "kullanıcı"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("orange", "turuncu"), ("purple", "mor"), ("cyan", "camgobegi"), ("mor", "mor"), ("gold", "")],
)
def test_color_claude_degerlerini_alir_gecersizi_duser(tmp_path: Path, value, expected) -> None:
    """Claude Code `color`: red, blue, green, yellow, purple, orange, pink, cyan (#25)."""
    _write(tmp_path, "renkli.md", f"---\nname: renkli\ndescription: d\ncolor: {value}\n---\nG.")

    agent = CapabilityRegistry(tmp_path / "ev", tmp_path).get_agent("renkli")

    assert agent is not None and agent.color == expected


def test_yerlesik_roller_claude_color_yazimini_kullanir() -> None:
    from fusion_cli.config.paths import bundled_roster_dir

    for path in bundled_roster_dir().glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "\nrenk:" not in text, path.name


def _extra_source_home(tmp_path: Path) -> Path:
    home = tmp_path / "ev"
    codex = home / ".codex" / "agents"
    codex.mkdir(parents=True)
    (codex / "codexci.md").write_text(
        "---\nname: codexci\ndescription: codex\n---\nCodex.", encoding="utf-8"
    )
    return home


def test_ek_ajan_kaynaklari_ayarla_tumden_kapatilir(tmp_path: Path) -> None:
    """`agent_launch.extra_agent_sources: false` yalnız Claude kapsamlarını bırakır (#38)."""
    home = _extra_source_home(tmp_path)

    acik = {item.name for item in CapabilityRegistry(home, tmp_path).agents()}
    kapali_registry = CapabilityRegistry(home, tmp_path, extra_agent_sources=False)
    kapali = {item.name for item in kapali_registry.agents()}

    assert "codexci" in acik and "kodcu" in acik
    assert "codexci" not in kapali and "kodcu" not in kapali
    assert {"explore", "plan", "general-purpose"} <= kapali
    assert kapali_registry.with_extra_roots(()).get_agent("codexci") is None


def test_ek_ajan_kaynaklari_ayari_yapilandirmadan_kataloga_gecer(tmp_path: Path) -> None:
    import dataclasses

    from fusion_cli.config.loader import load_config
    from fusion_cli.tools.capability_overrides import registry_from_config

    home = _extra_source_home(tmp_path)
    config = load_config()
    launch = dataclasses.replace(config.agent_launch, extra_agent_sources=False)
    config = dataclasses.replace(config, agent_launch=launch)

    registry = registry_from_config(config, home, tmp_path)

    assert registry.get_agent("codexci") is None
