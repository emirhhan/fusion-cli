from __future__ import annotations

from fusion_cli.appserver.hosted_connectors import hosted_provider_rows
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

    async def verify(self, config):
        # Uzak OAuth sunucusu yoklamada "giriş gerekli" döner; yerel sunucu bağlanır.
        if config.transport.value == "streamable_http" and not config.token_env:
            self.status = McpConnectionStatus(server=config.name, state="giris_gerekli")
            return self.status
        return await self.test(config)

    def start_login(self, config):
        # Gerçek servis gibi: giriş arka planda başlar, durum "bekleniyor" olur.
        self.started.append(config.name)
        self.status = McpConnectionStatus(server=config.name, state="giris_bekleniyor")
        return self.status

    def login_status(self, name):
        return self.status

    async def logout(self, config):
        self.logged_out.append(config.name)
        self.status = McpConnectionStatus(server=config.name, state="kapali")
        return self.status

    def invalidate(self, name):
        self.status = McpConnectionStatus(server=name, state="kapali")

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


async def test_stdio_baglanti_sirlarini_sifreli_depo_ve_ortama_yazar(tmp_path, monkeypatch):
    session, _fake = _session(tmp_path)
    monkeypatch.setattr("fusion_cli.appserver.connectors.write_mcp_servers", lambda _config: None)
    # Test makinenin PATH'ine bağlı kalmasın: komut "kurulu" sayılır.
    monkeypatch.setattr(
        "fusion_cli.appserver.connectors.shutil.which", lambda c, path=None: f"/bin/{c}"
    )
    stored: dict[str, str] = {}

    class _Store:
        available = True

        def set(self, name, value):
            stored[name] = value

        def get(self, name):
            return stored.get(name)

        def delete(self, name):
            stored.pop(name, None)

    session._secret_store = _Store()

    result = await session._dispatch(
        Request(
            "secret",
            "baglanti.ekle",
            {
                "ad": "brave",
                "komut": "npx -y server-brave",
                "ortam": {"BRAVE_API_KEY": "gizli-deger"},
            },
        )
    )

    assert result["ok"] is True
    assert stored == {"BRAVE_API_KEY": "gizli-deger"}
    assert session._state.config.mcp_servers[0].env_names == ("BRAVE_API_KEY",)


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
        "hata_turu": None,
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


async def test_tokenli_http_baglanti_giris_penceresi_acmaz(tmp_path, monkeypatch):
    """Token verilmişse OAuth akışı yerine doğrudan bağlantı denenir.

    Ölçüldü (mcp.facebook.com/ads): sunucu dinamik kaydı reddettiği için giriş
    penceresi hiç açılmıyor ve kullanıcı sonsuza dek "giriş bekleniyor" görüyordu.
    """
    session, fake = _session(tmp_path)
    monkeypatch.setattr("fusion_cli.appserver.connectors.write_mcp_servers", lambda _config: None)
    stored: dict[str, str] = {}

    class _Store:
        available = True

        def set(self, name, value):
            stored[name] = value

        def get(self, name):
            return stored.get(name)

        def delete(self, name):
            stored.pop(name, None)

    session._secret_store = _Store()

    result = await session._dispatch(
        Request(
            "1",
            "baglanti.ekle",
            {
                "ad": "Meta Ads",
                "tasima": "streamable_http",
                "url": "https://mcp.example.com/ads",
                "token": "gizli-token",
            },
        )
    )

    assert result["ok"] is True
    assert result["durum"] == "bagli"
    assert fake.started == []
    assert stored == {"FUSION_MCP_TOKEN_META_ADS": "gizli-token"}
    sunucu = session._state.config.mcp_servers[0]
    assert sunucu.token_env == "FUSION_MCP_TOKEN_META_ADS"


async def test_yoklamasi_basarisiz_baglanti_kaydedilmez(tmp_path, monkeypatch):
    """Var olmayan alan adı "eklendi" olmamalı: yoklama düşerse hiçbir şey yazılmaz."""
    session, fake = _session(tmp_path)
    yazilan: list[object] = []
    monkeypatch.setattr("fusion_cli.appserver.connectors.write_mcp_servers", yazilan.append)

    async def _dusen(config):
        return McpConnectionStatus(server=config.name, state="hata", message="Alan adı çözülemedi.")

    fake.verify = _dusen

    result = await session._dispatch(
        Request(
            "1",
            "baglanti.ekle",
            {"ad": "bozuk", "tasima": "streamable_http", "url": "https://yok.example.invalid/mcp"},
        )
    )

    assert result["ok"] is False
    assert "çözülemedi" in result["metin"]
    assert yazilan == []
    assert all(server.name != "bozuk" for server in session._state.config.mcp_servers)
    assert fake.started == []


async def test_arac_katalogu_rpc_kaynak_degismisse_eski_sonucu_gostermez(tmp_path, monkeypatch):
    from dataclasses import replace

    session, _fake = _session(tmp_path)
    server = McpServerConfig(name="one", command="fake")
    session._state.config = replace(session._state.config, mcp_servers=(server,))

    async def catalog(config, **_kwargs):
        assert config is server
        session._state.config = replace(session._state.config, mcp_servers=())
        return {"ok": True, "tools": [{"name": "old-account-tool"}]}

    monkeypatch.setattr("fusion_cli.appserver.session.list_tool_catalog", catalog)
    result = await session._dispatch(Request("catalog", "baglanti.araclar", {"ad": "one"}))
    assert result["ok"] is False
    assert "old-account-tool" not in str(result)


def test_liste_ve_detay_argumana_gomulu_anahtari_gostermez(tmp_path):
    """Ölçüldü (30 Ekim, S1-28): `server.args` olduğu gibi listeye ve MCP detayına yazılıyordu."""
    from dataclasses import replace
    from pathlib import Path

    from fusion_cli.appserver import capabilities
    from fusion_cli.appserver.connectors import list_connectors
    from fusion_cli.config.loader import load_config

    kaynak = Path(tmp_path / "c.yaml")
    kaynak.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    sunucu = McpServerConfig(
        name="x", command="npx", args=("sunucu", "--api-key=sk-gizli-deger-1234567890")
    )
    config = replace(load_config(kaynak), mcp_servers=(sunucu,))

    satir = list_connectors(config)["sunucular"][0]
    ayrinti = capabilities.detail(None, config, tmp_path, {"tur": "mcp", "ad": "x"})

    assert "sk-gizli-deger-1234567890" not in " ".join(satir["argumanlar"])
    assert "sk-gizli-deger-1234567890" not in ayrinti["icerik"]
    assert satir["argumanlar"][0] == "sunucu"


def test_kapsamlar_liste_gelirse_bozulmaz_ve_bozuk_durum_sayisi_listeyi_dusurmez():
    """Ölçüldü (30 Ekim, S1-50): liste `str(list).split()` ile bozuk kapsam üretiyor;
    `int("x")` durum satırını düşürüyordu."""
    from fusion_cli.appserver.connectors import _count, _scopes

    assert _scopes(["read", "write"]) == ("read", "write")
    assert _scopes("read write") == ("read", "write")
    assert _count("x") == 0 and _count(None) == 0 and _count("7") == 7


async def test_connector_paneli_hatasi_okunur_ve_kayit_temizlenir(tmp_path, monkeypatch, caplog):
    """Ölçüldü (30 Ekim, S2-56): panel görevinin istisnası hiç okunmuyor ("Task exception was
    never retrieved") ve `_panel_tasks` yalnız `close()`'da temizleniyordu."""
    import asyncio

    from fusion_cli.providers import web_browser

    async def bozuk(*_a, **_k):
        raise RuntimeError("tarayıcı yok")

    monkeypatch.setattr(web_browser, "open_login_browser", bozuk)
    oturum = AppSession(lambda _l: None, root=tmp_path, home=tmp_path / "ev")
    saglayici = hosted_provider_rows(oturum._state.config)[0]["id"]

    with caplog.at_level("ERROR"):
        sonuc = await oturum._open_connector_panel({"saglayici": saglayici})
        await asyncio.sleep(0.05)

    assert sonuc["ok"] is True
    assert oturum._panel_tasks == {}
    assert "RuntimeError" in caplog.text


async def test_basarisiz_baglanti_eklemesi_ortamdaki_eski_sirri_silmez(tmp_path, monkeypatch):
    """Ölçüldü (30 Ekim, S2-57): başarısız eklemede `os.environ.pop` önceki değeri geri
    koymak yerine siliyordu."""
    session, _fake = _session(tmp_path)
    monkeypatch.setattr(
        "fusion_cli.appserver.connectors.shutil.which", lambda c, path=None: f"/bin/{c}"
    )
    monkeypatch.setenv("BRAVE_API_KEY", "eski-deger")

    class _Store:
        available = True

        def set(self, name, value):
            pass

        def get(self, name):
            return None

        def delete(self, name):
            pass

    session._secret_store = _Store()

    async def reddet(_config, _data, *, probe):
        return None, {"ok": False, "metin": "bağlanamadı"}

    monkeypatch.setattr("fusion_cli.appserver.session.add_connector_verified", reddet)

    sonuc = await session._dispatch(
        Request(
            "x",
            "baglanti.ekle",
            {"ad": "brave", "komut": "npx -y s", "ortam": {"BRAVE_API_KEY": "yeni-deger"}},
        )
    )

    assert sonuc["ok"] is False
    import os

    assert os.environ["BRAVE_API_KEY"] == "eski-deger"


async def test_baglanti_yeniden_baglan_sunucuyu_yeniler_ve_turkce_metin_doner(tmp_path):
    """Masaüstü 'Yeniden bağlan' düğmesinin ucu (P-049): sonuç bildirime yazılabilsin."""
    session, fake = _session(tmp_path)
    yenilenen: list[str] = []

    async def _reconnect(config):
        yenilenen.append(config.name)
        return McpConnectionStatus(server=config.name, state="bagli", tool_count=3)

    fake.reconnect = _reconnect
    session._state.config = __import__("dataclasses").replace(
        session._state.config,
        mcp_servers=(McpServerConfig(name="godot", command="npx"),),
    )

    result = await session._dispatch(Request("3", "baglanti.yeniden_baglan", {"ad": "godot"}))
    yok = await session._dispatch(Request("4", "baglanti.yeniden_baglan", {"ad": "yok"}))

    assert yenilenen == ["godot"]
    assert result["ok"] is True and result["sunucular"][0]["arac_sayisi"] == 3
    assert "godot" in result["metin"]
    assert yok == {"ok": False, "metin": "Bağlantı bulunamadı."}
