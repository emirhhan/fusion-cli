"""Kuruluş MCP'si: CLI/REPL kaldırma yolu (#274).

Belge: code.claude.com/docs/en/managed-mcp. Sunucular `managed` kapsamına taşınınca
`fusion mcp remove` / `/mcp remove` onları aday saymıyor ve "yok" diyordu; Claude
"provided by your organization" iletisiyle reddeder.
"""

from __future__ import annotations

import pytest

from fusion_cli.config import mcp_policy
from fusion_cli.config.models import (
    McpScope,
    McpServerConfig,
    McpTransport,
)
from fusion_cli.core.errors import ConfigError

from .fakes import make_config


def _kurum() -> McpServerConfig:
    return McpServerConfig(
        name="kurum",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://mcp.kurum.example/mcp",
        scope=McpScope.MANAGED,
    )


@pytest.fixture
def ev(tmp_path, monkeypatch):
    for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    monkeypatch.setattr(mcp_policy, "managed_dir", lambda: tmp_path / "yonetim-yok")
    return tmp_path


@pytest.mark.parametrize("kapsam", [None, "managed"])
def test_remove_named_managed_kapsamli_sunucuyu_kurulus_iletisiyle_reddeder(ev, kapsam):
    from fusion_cli.cli.mcp_manage import remove_named

    config = make_config(mcp_servers=(_kurum(),))

    with pytest.raises(ConfigError, match="provided by your organization"):
        remove_named(config, ev, "kurum", kapsam)


def test_get_ipucu_managed_icin_kaldirma_komutu_onermez():
    from fusion_cli.cli.mcp_manage import remove_hint

    assert remove_hint(_kurum()) is None
    kullanici = McpServerConfig(name="benim", command="npx", scope=McpScope.USER)
    assert remove_hint(kullanici) == 'fusion mcp remove "benim" -s user'
