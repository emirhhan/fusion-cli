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
