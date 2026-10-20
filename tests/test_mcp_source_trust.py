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
    assert registry.get("offline__read").effect is ToolEffect.REMOTE_WRITE


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
