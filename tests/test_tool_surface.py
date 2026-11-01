"""Modele göre araç yüzeyi (T1-63) ve MCP araç sayısı sınırı (M1-12).

Ölçüldü (30 Ekim): yerleşik 41+ şema ve MCP araçları (WordPress 63, GitHub 90+) küçük
bağlamlı modele aynen gidiyordu; araç sayısı için hiçbir üst sınır ya da seçim yoktu.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.config.loader import ConfigError, _build_mcp_servers, load_config
from fusion_cli.config.models import McpServerConfig, RuntimeConfig
from fusion_cli.core.tools import Tool, ToolResult
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy, policy_for
from fusion_cli.engines.agent.loop import _permitted
from fusion_cli.engines.agent.tool_surface import uses_compact_surface
from fusion_cli.mcp_bridge.client import McpClient
from fusion_cli.tools import ToolRegistry, build_registry

from .fakes import make_config


async def _noop(args, context):
    return ToolResult("ok")


def _registry_with_remote(count: int) -> ToolRegistry:
    registry = build_registry()
    for index in range(count):
        registry.register_or_replace(
            Tool(name=f"srv__arac{index}", description="d", parameters={}, run=_noop)
        )
    return registry


def _compact() -> ExecutionPolicy:
    return ExecutionPolicy(is_web=False, compact_tool_surface=True, max_external_tools=3)


def test_siki_yuzeyde_masaustu_ve_chrome_ailesi_gizlenir():
    registry = build_registry()

    tam = _permitted(None, registry, ExecutionPolicy(is_web=False))
    siki = _permitted(None, registry, _compact())

    assert {"desktop_click", "desktop_apps", "chrome_page", "chrome_action"} <= tam
    assert not any(name.startswith(("desktop_", "chrome_")) for name in siki)
    assert {"read_file", "edit_file", "run_shell", "todo_write"} <= siki
    assert len(siki) < len(tam)


def test_masaustu_istegi_sıki_yuzeyde_bile_masaustu_araclarini_acar():
    registry = build_registry()

    acik = _permitted(None, registry, _compact(), {"masaustu"})

    assert {"desktop_click", "chrome_page"} <= acik


def test_acikca_istenen_arac_sıki_yuzeyde_gizlenmez():
    registry = build_registry()

    izinli = _permitted({"chrome_page", "read_file"}, registry, _compact())

    assert "chrome_page" in izinli and "desktop_click" not in izinli


def test_siki_yuzeyde_mcp_araclari_sinirlanir_yerlesikler_kalir():
    registry = _registry_with_remote(8)

    siki = _permitted(None, registry, _compact())

    uzak = sorted(name for name in siki if name.startswith("srv__"))
    assert uzak == ["srv__arac0", "srv__arac1", "srv__arac2"]
    assert "read_file" in siki


def test_genis_yuzeyde_mcp_araclari_sinirlanmaz():
    registry = _registry_with_remote(8)

    tam = _permitted(None, registry, ExecutionPolicy(is_web=False))

    assert len([name for name in tam if name.startswith("srv__")]) == 8


def test_klonlanan_kayit_defteri_uzak_isaretini_korur():
    from fusion_cli.engines.agent.engine_tools import _clone

    klon = _clone(_registry_with_remote(2))

    assert klon.is_remote("srv__arac0") and not klon.is_remote("read_file")


def test_kucuk_pencereli_model_siki_yuzey_alir(monkeypatch):
    monkeypatch.setattr(
        "fusion_cli.engines.agent.context_budget.input_window_tokens", lambda model: 8192
    )
    config = make_config()
    politika = policy_for(config, ModelSpec(name="agent", model="yerel/kucuk"), "kodu duzelt")

    assert politika.compact_tool_surface
    assert politika.max_external_tools == config.runtime.compact_external_tools


def test_buyuk_pencereli_model_tam_yuzey_alir(monkeypatch):
    monkeypatch.setattr(
        "fusion_cli.engines.agent.context_budget.input_window_tokens", lambda model: 200_000
    )
    politika = policy_for(make_config(), ModelSpec(name="agent", model="x/buyuk"), "kodu duzelt")

    assert not politika.compact_tool_surface and politika.max_external_tools is None


def test_bilinmeyen_pencere_tam_yuzey_acik_etiket_siki_yuzey(monkeypatch):
    monkeypatch.setattr(
        "fusion_cli.engines.agent.context_budget.input_window_tokens", lambda model: None
    )
    config = make_config()

    assert not uses_compact_surface(config, ModelSpec("agent", "x/y"), mutation_ok=True)
    assert uses_compact_surface(
        config, ModelSpec("agent", "x/y", tags=("Compact",)), mutation_ok=True
    )
    assert uses_compact_surface(config, ModelSpec("agent", "x/y"), mutation_ok=False)


def test_esik_sifirsa_pencereye_bakilmaz(monkeypatch):
    monkeypatch.setattr(
        "fusion_cli.engines.agent.context_budget.input_window_tokens", lambda model: 4096
    )
    config = make_config()
    config = replace(config, runtime=replace(config.runtime, compact_tools_window_tokens=0))

    assert not uses_compact_surface(config, ModelSpec("agent", "x/y"), mutation_ok=True)


def test_varsayilanlar_kodla_tutarli():
    runtime = load_config().runtime
    alanlar = RuntimeConfig.__dataclass_fields__

    assert runtime.compact_tools_window_tokens == alanlar["compact_tools_window_tokens"].default
    assert runtime.compact_external_tools == alanlar["compact_external_tools"].default


# --- M1-12: sunucu başına izin listesi / max_tools ------------------------------------


class _Oturum:
    """`list_tools` ile belirli adlarda araç dönen sahte MCP oturumu."""

    def __init__(self, *adlar: str) -> None:
        self._adlar = adlar

    async def list_tools(self, cursor=None):
        from mcp.types import ListToolsResult
        from mcp.types import Tool as McpTool

        return ListToolsResult(
            tools=[McpTool(name=ad, inputSchema={"type": "object"}) for ad in self._adlar]
        )


async def _kaydet(config: McpServerConfig, *adlar: str) -> list[str]:
    client = McpClient((config,))
    client._sessions[config.name] = _Oturum(*adlar)
    registry = ToolRegistry()
    await client.register_into(registry)
    return sorted(registry.names())


async def test_izin_listesi_yalniz_secilen_araclari_kaydeder():
    config = McpServerConfig("wp", allowed_tools=("posts_list", "posts_get"))

    kayitli = await _kaydet(config, "posts_list", "posts_get", "users_delete", "options_update")

    assert kayitli == ["mcp__wp__posts_get", "mcp__wp__posts_list"]


async def test_max_tools_sunucu_sirasiyla_ilk_n_araci_tutar():
    config = McpServerConfig("gh", max_tools=2)

    kayitli = await _kaydet(config, "a", "b", "c", "d")

    assert kayitli == ["mcp__gh__a", "mcp__gh__b"]


async def test_izin_listesi_sonra_max_tools_uygulanir():
    config = McpServerConfig("gh", allowed_tools=("b", "c", "d"), max_tools=2)

    assert await _kaydet(config, "a", "b", "c", "d") == ["mcp__gh__b", "mcp__gh__c"]


async def test_ayar_yoksa_hepsi_kaydedilir_ve_guven_ozeti_tum_tanimlardan_alinir():
    config = McpServerConfig("gh", allowed_tools=("a",))
    client = McpClient((config,))
    client._sessions["gh"] = _Oturum("a", "b", "c")
    await client.register_into(ToolRegistry())
    daraltilmis = client._tool_digests["gh"]

    ayarsiz = McpClient((McpServerConfig("gh"),))
    ayarsiz._sessions["gh"] = _Oturum("a", "b", "c")
    await ayarsiz.register_into(ToolRegistry())

    assert daraltilmis == ayarsiz._tool_digests["gh"]


def test_yukleyici_yeni_alanlari_okur_ve_gecersiz_siniri_reddeder():
    sunucu = _build_mcp_servers([{"name": "wp", "allowed_tools": ["a", "b"], "max_tools": 5}])[0]

    assert sunucu.allowed_tools == ("a", "b") and sunucu.max_tools == 5
    with pytest.raises(ConfigError):
        _build_mcp_servers([{"name": "wp", "max_tools": 0}])


def test_yazici_yeni_alanlari_diske_yazar_ve_geri_okunur(tmp_path):
    from fusion_cli.config.writer import write_mcp_servers

    sunucu = McpServerConfig("wp", command="x", allowed_tools=("a",), max_tools=4)
    config = replace(make_config(), mcp_servers=(sunucu,))
    hedef = write_mcp_servers(config, tmp_path / "config.yaml")

    import yaml

    yazilan = yaml.safe_load(hedef.read_text(encoding="utf-8"))["mcp_servers"][0]
    assert yazilan["allowed_tools"] == ["a"] and yazilan["max_tools"] == 4
    assert _build_mcp_servers([yazilan])[0].max_tools == 4


@pytest.mark.parametrize("seed", range(20))
def test_ilgi_secimi_kirk_aracta_kayit_sirasindan_bagimsizdir(seed):
    import random

    from fusion_cli.engines.agent.tool_surface import narrow_to_compact_surface

    tools = [
        Tool(name=f"srv__noise{index}", description="calendar event", parameters={}, run=_noop)
        for index in range(38)
    ] + [
        Tool(name="srv__symbol", description="python symbol references", parameters={}, run=_noop),
        Tool(
            name="srv__forbidden", description="python symbol references", parameters={}, run=_noop
        ),
    ]
    random.Random(seed).shuffle(tools)
    registry = ToolRegistry()
    for tool in tools:
        registry.register_or_replace(tool)
    permitted = set(registry.names()) - {"srv__forbidden"}
    selected = narrow_to_compact_surface(
        permitted,
        registry,
        max_external_tools=1,
        task_kinds=(),
        explicit=("srv__noise0", "srv__forbidden"),
        external_tool_selection="relevance",
        task="python symbol",
        phase="references",
    )
    assert selected == {"srv__symbol", "srv__noise0"}
    assert permitted == set(registry.names()) - {"srv__forbidden"}


def test_ilgi_secimi_bos_gorevde_deterministiktir_ve_gecersiz_stratejiyi_reddeder():
    from fusion_cli.engines.agent.tool_surface import narrow_to_compact_surface

    registry = _registry_with_remote(5)
    arguments = {"max_external_tools": 2, "task_kinds": (), "explicit": ()}
    assert narrow_to_compact_surface(set(registry.names()), registry, **arguments) >= {
        "srv__arac0",
        "srv__arac1",
    }
    with pytest.raises(ValueError):
        narrow_to_compact_surface(
            set(registry.names()), registry, **arguments, external_tool_selection="unknown"
        )
