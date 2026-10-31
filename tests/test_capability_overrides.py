"""`capabilities.overrides` — beceri görünürlüğü (Claude Code `skillOverrides`; P-051).

Ölçüldü (31 Ekim): yalnız `capabilities.disabled` vardı; bir beceriyi dizinden çıkarıp yalnız
`/ad` ile çağrılır bırakmak ya da açıklamasını dizinden düşürmek için yol yoktu.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.appserver.capabilities import catalog
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.config.models import SkillVisibility
from fusion_cli.core.errors import ConfigError
from fusion_cli.engines.agent.skill_index import skill_index_block
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools.capabilities import CapabilityRegistry


def _skill(folder: Path, name: str, description: str = "uzun açıklama metni") -> None:
    (folder / name).mkdir(parents=True, exist_ok=True)
    (folder / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nGövde", encoding="utf-8"
    )


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    for name in ("olagan", "adli", "elle", "kapali"):
        _skill(home / ".claude" / "skills", name, description=f"{name} açıklaması")
    return home, root


def _state(tmp_path: Path, home: Path, root: Path, body: str) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text(body, encoding="utf-8")
    return ReplState(config=load_config(source), memory=null_memory(), root=root, home=home)


def test_turkce_ve_ingilizce_gorunurluk_adlari_okunur(tmp_path: Path, dirs: tuple[Path, Path]):
    state = _state(
        tmp_path,
        *dirs,
        "capabilities:\n  overrides:\n    adli: yalniz-ad\n    elle: user-invocable-only\n"
        "    kapali: kapalı\n",
    )

    assert state.config.capabilities.overrides == {
        "adli": SkillVisibility.NAME_ONLY,
        "elle": SkillVisibility.USER_INVOCABLE_ONLY,
        "kapali": SkillVisibility.OFF,
    }


def test_gecersiz_gorunurluk_yuklemede_reddedilir(tmp_path: Path):
    source = tmp_path / "config.yaml"
    source.write_text("capabilities:\n  overrides:\n    x: gizli\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r"overrides\.x"):
        load_config(source)


def test_gorunurluk_dizin_slash_ve_kataloga_uygulanir(tmp_path: Path, dirs: tuple[Path, Path]):
    state = _state(
        tmp_path,
        *dirs,
        "capabilities:\n  overrides:\n    adli: name-only\n    elle: user-invocable-only\n"
        "    kapali: off\n",
    )
    registry = state.capabilities
    assert registry is not None

    index = skill_index_block(registry, budget=4_000)
    commands = build_registry(state.home, skills=lambda: state.capabilities)

    assert "- olagan — olagan açıklaması" in index
    assert "- adli\n" in index + "\n" and "adli açıklaması" not in index
    assert "elle" not in index  # model dizinde görmez…
    assert commands.get("elle") is not None  # …ama kullanıcı /elle ile çağırır
    assert registry.get_skill("kapali") is None and commands.get("kapali") is None

    payload = catalog(
        CapabilityRegistry(*dirs),
        state.config,
        state.root,
        disabled_skills=set(),
        disabled_agents=set(),
        disabled_mcp=set(),
    )
    by_name = {item["ad"]: item for item in payload["beceriler"]}
    assert by_name["adli"]["ayarlar"]["gorunurluk"] == "dizinde yalnız ad"
    assert by_name["kapali"]["etkin"] is False
    assert "gorunurluk" not in by_name["olagan"]["ayarlar"]


def test_nitelikli_kimlik_duz_addan_once_gelir(tmp_path: Path, dirs: tuple[Path, Path]):
    home, root = dirs
    qualified = CapabilityRegistry(home, root).get_skill("adli").qualified_name  # type: ignore[union-attr]
    registry = CapabilityRegistry(
        home, root, overrides={qualified: SkillVisibility.ON, "adli": SkillVisibility.OFF}
    )

    assert registry.get_skill("adli") is not None
    assert registry.with_extra_roots(()).get_skill("adli") is not None
