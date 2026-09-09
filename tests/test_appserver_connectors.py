from __future__ import annotations

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge.client import McpConnectionStatus


class FakeConnections:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.logged_out: list[str] = []
        self.status = McpConnectionStatus(server="meta", state="giris_bekleniyor")

    @property
    def statuses(self):
        return {self.status.server: self.status}

    async def test(self, config):
        self.status = McpConnectionStatus(server=config.name, state="bagli", tool_count=5)
        return self.status

    def start_login(self, config):
        self.started.append(config.name)
        return self.status

    def login_status(self, name):
        return self.status

    async def logout(self, config):
        self.logged_out.append(config.name)
        self.status = McpConnectionStatus(server=config.name, state="kapali")
        return self.status

    async def close(self):
        return None


def _session(tmp_path):
    session = AppSession([].append, root=tmp_path, home=tmp_path / "home")
    fake = FakeConnections()
    session._mcp_connections = fake
    return session, fake


async def test_http_baglanti_eklenince_giris_arka_planda_baslar(tmp_path, monkeypatch):
    session, fake = _session(tmp_path)
    monkeypatch.setattr("fusion_cli.appserver.connectors.write_mcp_servers", lambda _config: None)

    result = await session._dispatch(
        Request(
            "1",
            "baglanti.ekle",
            {
                "ad": "meta",
                "tasima": "streamable_http",
                "url": "https://mcp.example.com/mcp",
            },
        )
    )

    assert result["ok"] is True
    assert result["durum"] == "giris_bekleniyor"
    assert fake.started == ["meta"]


async def test_baglanti_dogrula_arac_sayisini_dondurur(tmp_path):
    session, _fake = _session(tmp_path)
    session._state.config = __import__("dataclasses").replace(
        session._state.config,
        mcp_servers=(McpServerConfig(name="godot", command="npx"),),
    )

    result = await session._dispatch(Request("2", "baglanti.dogrula", {"ad": "godot"}))

    assert result == {
        "ok": True,
        "ad": "godot",
        "durum": "bagli",
        "arac_sayisi": 5,
        "gecikme_ms": 0,
        "mesaj": None,
    }


async def test_baglanti_cikis_token_deposunu_temizler(tmp_path):
    session, fake = _session(tmp_path)
    session._state.config = __import__("dataclasses").replace(
        session._state.config,
        mcp_servers=(
            McpServerConfig(
                name="meta",
                transport=McpTransport.STREAMABLE_HTTP,
                url="https://mcp.example.com/mcp",
            ),
        ),
    )

    result = await session._dispatch(Request("3", "baglanti.cikis", {"ad": "meta"}))

    assert result["durum"] == "kapali"
    assert fake.logged_out == ["meta"]
