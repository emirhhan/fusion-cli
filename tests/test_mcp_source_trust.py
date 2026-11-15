"""Güven, kurulu olma veya OAuth kapsamından türetilemez."""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.config.models import McpServerConfig, McpTransport, McpTrust
from fusion_cli.core.tools import ToolEffect
from fusion_cli.mcp_bridge.trust import effective_trust, review_identity, trusted_effect


def test_legacy_and_changed_source_are_unreviewed():
    config = McpServerConfig(
        "offline", transport=McpTransport.STREAMABLE_HTTP, url="https://offline.invalid/mcp"
    )
    assert effective_trust(config) is McpTrust.UNREVIEWED
    assert trusted_effect(config, ToolEffect.REMOTE_READ) is ToolEffect.REMOTE_WRITE
    reviewed = replace(config, trust=McpTrust.TRUSTED, reviewed_source=review_identity(config))
    assert effective_trust(reviewed) is McpTrust.TRUSTED
    assert (
        effective_trust(replace(reviewed, url="https://other.invalid/mcp")) is McpTrust.UNREVIEWED
    )
    assert effective_trust(replace(reviewed, trust=McpTrust.REVOKED)) is McpTrust.REVOKED


def test_unpinned_source_and_credential_url_cannot_be_reviewed():
    assert review_identity(McpServerConfig("offline", command="npx", args=("pkg@latest",))) is None
    assert review_identity(McpServerConfig("offline", command="npx", args=("pkg@1.2.3",)))
    assert (
        review_identity(
            McpServerConfig(
                "offline",
                transport=McpTransport.STREAMABLE_HTTP,
                url="https://offline.invalid/mcp?token=offline-fixture",
            )
        )
        is None
    )


async def test_unreviewed_discovery_cannot_register_read_exemption():
    from mcp.types import ListToolsResult, Tool, ToolAnnotations

    from fusion_cli.mcp_bridge.client import McpClient
    from fusion_cli.tools import ToolRegistry

    class OfflineSession:
        async def list_tools(self):
            return ListToolsResult(
                tools=[
                    Tool(
                        name="read",
                        inputSchema={"type": "object"},
                        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
                    )
                ]
            )

    config = McpServerConfig(
        "offline", transport=McpTransport.STREAMABLE_HTTP, url="https://offline.invalid/mcp"
    )
    client = McpClient((config,))
    client._sessions["offline"] = OfflineSession()
    registry = ToolRegistry()
    await client.register_into(registry)
    assert registry.get("mcp__offline__read").effect is ToolEffect.REMOTE_WRITE


def test_trust_review_is_bound_to_displayed_source(monkeypatch, tmp_path):
    from fusion_cli.appserver.connectors import review_connector
    from tests.fakes import make_config

    monkeypatch.setattr(
        "fusion_cli.appserver.connectors.write_mcp_servers", lambda config: tmp_path / "config.yaml"
    )
    server = McpServerConfig(
        "offline", transport=McpTransport.STREAMABLE_HTTP, url="https://offline.invalid/mcp"
    )
    config = replace(make_config(), mcp_servers=(server,))
    updated, receipt = review_connector(
        config, {"ad": "offline", "guven": "trusted", "inceleme_kimligi": "stale"}
    )
    assert updated is None and receipt["ok"] is False
    updated, receipt = review_connector(
        config, {"ad": "offline", "guven": "trusted", "inceleme_kimligi": review_identity(server)}
    )
    assert receipt["ok"] is True
    assert effective_trust(updated.mcp_servers[0]) is McpTrust.TRUSTED
    assert trusted_effect(updated.mcp_servers[0], ToolEffect.REMOTE_READ) is ToolEffect.REMOTE_READ
    assert (
        trusted_effect(updated.mcp_servers[0], ToolEffect.REMOTE_WRITE) is ToolEffect.REMOTE_WRITE
    )


def test_invalid_network_budgets_are_rejected_by_config_loader():
    import pytest

    from fusion_cli.config.loader import _build_mcp_servers
    from fusion_cli.core.errors import ConfigError

    for value in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ConfigError):
            _build_mcp_servers([{"name": "offline", "call_timeout_s": value}])


# M1-16 — Ölçüldü (30 Ekim): güven kaydı yalnız KAYNAK kimliğine (adres/paket) bağlıydı. Aynı
# adresteki sunucu inceleme sonrası araç tanımlarını (açıklama, şema, readOnlyHint) değiştirirse
# eski "güvenilir" kaydı sürüyor ve değişen araç okuma muafiyeti alabiliyordu.
def _http_config(**fields):
    return McpServerConfig(
        "offline",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://offline.invalid/mcp",
        **fields,
    )


def _sdk_tool(name="read", description="Okur", read_only=True):
    from mcp.types import Tool, ToolAnnotations

    return Tool(
        name=name,
        description=description,
        inputSchema={"type": "object"},
        annotations=ToolAnnotations(readOnlyHint=read_only, destructiveHint=False),
    )


def test_tools_digest_degisen_tanimda_degisir_sirada_degismez():
    from fusion_cli.mcp_bridge.trust import tools_digest

    a, b = _sdk_tool("a"), _sdk_tool("b")
    assert tools_digest([a, b]) == tools_digest([b, a])
    assert tools_digest([a, b]) != tools_digest([a])
    assert tools_digest([a]) != tools_digest([_sdk_tool("a", description="Başka")])
    assert tools_digest([a]) != tools_digest([_sdk_tool("a", read_only=False)])


def test_arac_tanimi_degisince_guven_dusar_kayitsiz_eski_guven_korunur():
    from fusion_cli.mcp_bridge.trust import tools_digest

    base = _http_config()
    reviewed = replace(base, trust=McpTrust.TRUSTED, reviewed_source=review_identity(base))
    pinned = replace(reviewed, reviewed_tools=tools_digest([_sdk_tool()]))
    same, changed = tools_digest([_sdk_tool()]), tools_digest([_sdk_tool(description="Yeni")])

    assert effective_trust(pinned, same) is McpTrust.TRUSTED
    assert effective_trust(pinned, None) is McpTrust.TRUSTED  # henüz keşfedilmedi
    assert effective_trust(pinned, changed) is McpTrust.UNREVIEWED
    assert trusted_effect(pinned, ToolEffect.REMOTE_READ, changed) is ToolEffect.REMOTE_WRITE
    assert trusted_effect(pinned, ToolEffect.REMOTE_READ, same) is ToolEffect.REMOTE_READ
    # Araç özeti kaydı olmayan eski güven kayıtları yeniden onay istemez.
    assert effective_trust(reviewed, changed) is McpTrust.TRUSTED


async def test_degisen_arac_tanimi_okuma_muafiyeti_alamaz():
    from mcp.types import ListToolsResult

    from fusion_cli.mcp_bridge.client import McpClient
    from fusion_cli.mcp_bridge.trust import tools_digest
    from fusion_cli.tools import ToolRegistry

    class Session:
        def __init__(self, tool):
            self._tool = tool

        async def list_tools(self):
            return ListToolsResult(tools=[self._tool])

    base = _http_config()
    pinned = replace(
        base,
        trust=McpTrust.TRUSTED,
        reviewed_source=review_identity(base),
        reviewed_tools=tools_digest([_sdk_tool()]),
    )
    for tool, expected in (
        (_sdk_tool(), ToolEffect.REMOTE_READ),
        (_sdk_tool(description="Artık dosya siler"), ToolEffect.REMOTE_WRITE),
    ):
        client = McpClient((pinned,))
        client._sessions["offline"] = Session(tool)
        registry = ToolRegistry()
        await client.register_into(registry)
        assert registry.get("mcp__offline__read").effect is expected


def test_guven_karari_arac_ozetini_kaydeder_geri_cekince_siler(monkeypatch, tmp_path):
    from fusion_cli.appserver.connectors import review_connector
    from tests.fakes import make_config

    monkeypatch.setattr(
        "fusion_cli.appserver.connectors.write_mcp_servers", lambda config: tmp_path / "config.yaml"
    )
    server = _http_config()
    config = replace(make_config(), mcp_servers=(server,))
    data = {"ad": "offline", "guven": "trusted", "inceleme_kimligi": review_identity(server)}

    updated, _ = review_connector(config, {**data, "arac_ozeti": "abc123"})
    assert updated.mcp_servers[0].reviewed_tools == "abc123"
    updated, _ = review_connector(updated, {**data, "guven": "revoked"})
    assert updated.mcp_servers[0].reviewed_tools == ""
    # Özet verilmezse (sunucuya ulaşılamadı) boş kalır: eski davranış.
    updated, _ = review_connector(config, data)
    assert updated.mcp_servers[0].reviewed_tools == ""


def test_arac_ozeti_yapilandirmada_saklanir():
    from fusion_cli.config.loader import _build_mcp_servers

    (server,) = _build_mcp_servers([{"name": "offline", "reviewed_tools": "abc"}])
    assert server.reviewed_tools == "abc"


def test_liste_degisen_arac_tanimini_incelenmemis_gosterir():
    from fusion_cli.appserver.connectors import list_connectors
    from fusion_cli.mcp_bridge.types import McpConnectionStatus
    from tests.fakes import make_config

    base = _http_config()
    pinned = replace(
        base, trust=McpTrust.TRUSTED, reviewed_source=review_identity(base), reviewed_tools="abc"
    )
    config = replace(make_config(), mcp_servers=(pinned,))

    def trust_for(digest: str) -> str:
        status = McpConnectionStatus("offline", "bagli", tools_digest=digest)
        return list_connectors(config, {"offline": status})["sunucular"][0]["guven"]

    assert trust_for("abc") == "trusted"
    assert trust_for("") == "trusted"  # keşif yok: yalnız kaynak denetlenir
    assert trust_for("degisti") == "unreviewed"


async def test_ulasilamayan_sunucuda_arac_ozeti_bos_doner():
    from fusion_cli.appserver.mcp_catalog import pin_tools_digest

    assert await pin_tools_digest(_http_config(), timeout=0.05) == ""
