"""MCP köprüsü — sunucu + istemci uçtan uca (gerçek stdio alt-süreç).

Fusion'ın KENDİ MCP sunucusunu bir alt-süreç olarak başlatır ve McpClient ile bağlanır:
tek testte HEM sunucu (araçları dışa açar) HEM istemci (bağlanıp kullanır) doğrulanır.
Ağ yok; her şey yerel stdio.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from mcp.types import (
    AudioContent,
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    ResourceLink,
    TextContent,
    TextResourceContents,
)

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.core.types import Message
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.mcp_bridge.client import McpClient
from fusion_cli.mcp_bridge.server import build_server
from fusion_cli.mcp_bridge.transport import resolve_stdio_args

from .fakes import make_config


def _server_config(root):
    # Fusion'ın MCP sunucusunu venv python'uyla alt-süreç olarak başlat.
    return McpServerConfig(
        name="fusion",
        command=sys.executable,
        args=("-m", "fusion_cli.mcp_bridge.server", str(root)),
    )


def test_stdio_gizli_argumani_yapilandirmaya_yazmadan_cozer():
    config = McpServerConfig(
        name="postgres",
        command="server-postgres",
        args=("__FUSION_SECRET__:POSTGRES_URL",),
        env_names=("POSTGRES_URL",),
    )

    assert resolve_stdio_args(
        config,
        environ={"POSTGRES_URL": "postgresql://user:secret@localhost/db"},
    ) == ["postgresql://user:secret@localhost/db"]


def test_stdio_gizli_arguman_eksikse_acik_hata_verir():
    config = McpServerConfig(
        name="postgres",
        command="server-postgres",
        args=("__FUSION_SECRET__:POSTGRES_URL",),
        env_names=("POSTGRES_URL",),
    )

    with pytest.raises(ValueError, match="POSTGRES_URL"):
        resolve_stdio_args(config, environ={})


# --- sunucu (birim) -------------------------------------------------------- #


def test_sunucu_kurulur():
    server = build_server(root=".")  # type: ignore[arg-type]
    assert server.name == "fusion"


# --- uçtan uca: sunucu + istemci ------------------------------------------- #


async def test_ustten_uca_baglan_listele_cagir(tmp_path):
    (tmp_path / "ornek.txt").write_text("selam", encoding="utf-8")

    async with McpClient([_server_config(tmp_path)]) as client:
        tools = await client.list_tools("fusion")
        adlar = {t.name for t in tools}
        # Salt-okunur araçlar açılır; değiştirici araçlar (write_file) AÇILMAZ.
        assert "list_dir" in adlar
        assert "read_file" in adlar
        assert "write_file" not in adlar

        # Uzak aracı gerçekten çağır. `call` metnin YANINDA hata bayrağını da
        # döndürür; bayrağı atmak uzak hataları başarı gibi gösteriyordu.
        sonuc = await client.call("fusion", "list_dir", {"path": "."})
        assert "ornek.txt" in sonuc.output
        assert sonuc.ok is True


async def test_register_into_araclari_kayit_defterine_ekler(tmp_path):
    from fusion_cli.tools import ToolRegistry

    registry = ToolRegistry()
    async with McpClient([_server_config(tmp_path)]) as client:
        eklenen = await client.register_into(registry)

    # Araçlar <sunucu>__<araç> biçiminde ve mutating (onay akışına girsin) eklenir.
    assert any(name.startswith("fusion__") for name in eklenen)
    tool = registry.get("fusion__list_dir")
    assert tool is not None
    assert tool.mutating is True


async def test_bozuk_bir_sunucu_saglam_sunucunun_araclarini_dusurmez(tmp_path):
    from fusion_cli.tools import ToolRegistry

    bozuk = McpServerConfig(
        name="bozuk",
        transport=McpTransport.STDIO,
        command="kesinlikle-bulunmayan-fusion-komutu",
    )
    registry = ToolRegistry()

    async with McpClient((bozuk, _server_config(tmp_path)), timeout_seconds=3) as client:
        eklenen = await client.register_into(registry)
        durumlar = client.statuses

    assert any(name.startswith("fusion__") for name in eklenen)
    assert durumlar["bozuk"].state == "hata"
    assert durumlar["fusion"].state == "bagli"
    assert "kesinlikle-bulunmayan" not in (durumlar["bozuk"].message or "")


# --- fusion agent (tek-atış CLI) MCP'ye bağlanır ---------------------------- #


async def test_fusion_agent_yapilandirilmis_mcp_araclarini_gorev_oncesi_baglar(
    monkeypatch, tmp_path
):
    """`fusion agent` (tek-atış) yolu, REPL gibi, dış MCP araçlarını modele sunmalı.

    Önceden yalnızca REPL (`cli/repl/loop.py`) MCP'ye bağlanıyordu; kullanıcı
    "şu MCP'yi kur" dedikten sonra `fusion agent` ile (ör. otomasyon betiğinde)
    görev verirse bağlı MCP'nin araçları modele HİÇ sunulmuyordu. Bu test gerçek
    bir MCP sunucusuna (Fusion'ın kendisi, stdio alt-süreç) bağlanıp aracın
    `run_agent`'a geçmeden ÖNCE kayıt defterinde göründüğünü doğrular.
    """
    from fusion_cli.cli import session

    gorulen_registry: list[object] = []

    async def fake_run_agent(_task, deps, **kwargs):
        del kwargs
        gorulen_registry.append(deps.base_registry)
        return AgentOutcome(final_text="tamam", messages=[Message("user", "görev")], ok=True)

    monkeypatch.setattr(session, "run_agent", fake_run_agent)

    class _Prompter:
        async def confirm(self, _request):
            return True

        async def ask(self, _question):
            return ""

    config = make_config(mcp_servers=(_server_config(tmp_path),), runtime={"lessons": False})

    await session.run_agent_task(
        "görev",
        config,
        sinks=(),
        prompter_factory=lambda _drain: _Prompter(),
        root=tmp_path,
        interactive=False,
    )

    assert len(gorulen_registry) == 1
    assert gorulen_registry[0].get("fusion__list_dir") is not None


# --- uzak araç hatasının taşınması ----------------------------------------- #


class _SahteBlok:
    """MCP metin bloğu."""

    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _SahteSonuc:
    def __init__(self, metin: str, hata: bool) -> None:
        self.content = [_SahteBlok(metin)]
        self.isError = hata


class _SahteArac:
    def __init__(self, ad: str) -> None:
        self.name = ad
        self.description = "sahte"
        self.inputSchema = {"type": "object", "properties": {}}


class _SahteOturum:
    """`call_tool` sözleşmesinin en dar hâli."""

    def __init__(self, ad: str, metin: str, hata: bool) -> None:
        self._arac = _SahteArac(ad)
        self._metin = metin
        self._hata = hata

    async def list_tools(self):
        return SimpleNamespace(tools=[self._arac])

    async def call_tool(self, name, args):
        del name, args
        return _SahteSonuc(self._metin, self._hata)


class _SdkSonucOturumu:
    """Gerçek MCP SDK sonuç nesnesini istemci sınırına verir."""

    def __init__(self, result: CallToolResult) -> None:
        self._result = result

    async def call_tool(self, name, args):
        del name, args
        return self._result


async def test_sdk_icerigi_kayipsiz_normalize_edilir():
    result = CallToolResult(
        content=[
            TextContent(type="text", text="inceleme tamamlandı"),
            ImageContent(type="image", data="aGVsbG8=", mimeType="image/png"),
            AudioContent(type="audio", data="c2Vz", mimeType="audio/wav"),
            ResourceLink(
                type="resource_link",
                name="rapor",
                title="Denetim raporu",
                uri="file:///tmp/rapor.json",
                description="Kaynak ayrıntıları",
                mimeType="application/json",
                size=42,
            ),
            EmbeddedResource(
                type="resource",
                resource=TextResourceContents(
                    uri="file:///tmp/not.txt", mimeType="text/plain", text="kaynak metni"
                ),
            ),
            EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(
                    uri="file:///tmp/veri.bin",
                    mimeType="application/octet-stream",
                    blob="YmluYXJ5",
                ),
            ),
        ],
        structuredContent={"score": 5, "valid": True},
        isError=False,
    )
    client = McpClient(())
    client._sessions["fixture"] = _SdkSonucOturumu(result)

    sonuc = await client.call("fixture", "inspect", {})

    assert sonuc.ok is True
    assert sonuc.images == ("data:image/png;base64,aGVsbG8=",)
    assert '"score": 5' in sonuc.output
    assert "file:///tmp/rapor.json" in sonuc.output
    assert "kaynak metni" in sonuc.output
    assert "application/octet-stream" in sonuc.output
    assert "YmluYXJ5" not in sonuc.output
    assert "c2Vz" not in sonuc.output
    assert {block.type.value for block in sonuc.content} >= {
        "text",
        "image",
        "audio",
        "resource_link",
        "resource_text",
        "resource_blob",
    }


async def test_yalniz_gorsel_sdk_sonucu_bos_basariya_donusmez():
    result = CallToolResult(
        content=[ImageContent(type="image", data="aGVsbG8=", mimeType="image/png")]
    )
    client = McpClient(())
    client._sessions["fixture"] = _SdkSonucOturumu(result)

    sonuc = await client.call("fixture", "inspect", {})

    assert sonuc.ok is True
    assert sonuc.output
    assert "Görsel" in sonuc.output
    assert "aGVsbG8=" not in sonuc.output


async def test_sdk_is_error_bayragi_icerikle_birlikte_korunur():
    result = CallToolResult(
        content=[TextContent(type="text", text="inceleme başarısız")],
        structuredContent={"score": 0},
        isError=True,
    )
    client = McpClient(())
    client._sessions["fixture"] = _SdkSonucOturumu(result)

    sonuc = await client.call("fixture", "inspect", {})

    assert sonuc.ok is False
    assert "inceleme başarısız" in sonuc.output
    assert '"score": 0' in sonuc.output


async def test_uzun_metin_structured_ve_kaynak_ozetini_gizlemez():
    result = CallToolResult(
        content=[
            TextContent(type="text", text="x" * 25_000),
            ResourceLink(
                type="resource_link",
                name="kritik-rapor",
                uri="file:///tmp/kritik.json",
            ),
        ],
        structuredContent={"needle": "KORUNMALI"},
    )
    client = McpClient(())
    client._sessions["fixture"] = _SdkSonucOturumu(result)

    sonuc = await client.call("fixture", "inspect", {})

    assert '"needle": "KORUNMALI"' in sonuc.output
    assert "file:///tmp/kritik.json" in sonuc.output
    assert "KIRPILDI" in sonuc.output


async def test_buyuk_structured_sonraki_kaynak_ozetini_gizlemez():
    result = CallToolResult(
        content=[
            ResourceLink(
                type="resource_link",
                name="kritik-rapor",
                uri="file:///tmp/critical",
            )
        ],
        structuredContent={"huge": "x" * 25_000},
    )
    client = McpClient(())
    client._sessions["fixture"] = _SdkSonucOturumu(result)

    sonuc = await client.call("fixture", "inspect", {})

    assert "file:///tmp/critical" in sonuc.output
    assert '"huge"' in sonuc.output
    assert "KIRPILDI" in sonuc.output


class _SayfaliOturum:
    def __init__(self, pages: dict[str | None, object]) -> None:
        self._pages = pages
        self.cursors: list[str | None] = []

    async def list_tools(self, cursor=None):
        self.cursors.append(cursor)
        return self._pages[cursor]


async def test_arac_listesi_butun_sayfalari_kaydeder():
    from fusion_cli.tools import ToolRegistry

    session = _SayfaliOturum(
        {
            None: SimpleNamespace(tools=[_SahteArac("bir")], nextCursor="ikinci"),
            "ikinci": SimpleNamespace(tools=[_SahteArac("iki")], nextCursor=None),
        }
    )
    client = McpClient(())
    client._sessions["fixture"] = session
    registry = ToolRegistry()

    eklenen = await client.register_into(registry)

    assert eklenen == ("fixture__bir", "fixture__iki")
    assert session.cursors == [None, "ikinci"]


async def test_yinelenen_cursor_sonsuz_dongu_olusturmaz():
    session = _SayfaliOturum(
        {
            None: SimpleNamespace(tools=[_SahteArac("bir")], nextCursor="ikinci"),
            "ikinci": SimpleNamespace(tools=[_SahteArac("iki")], nextCursor="ikinci"),
        }
    )
    client = McpClient(())
    client._sessions["fixture"] = session

    tools = await client.list_tools("fixture")

    assert [tool.name for tool in tools] == ["bir", "iki"]
    assert session.cursors == [None, "ikinci"]


async def _sahte_calistir(ad: str, metin: str, hata: bool):
    """Köprüyü sahte oturumla kur ve aracı bir kez çalıştır."""
    from fusion_cli.tools import ToolRegistry

    istemci = McpClient((McpServerConfig(name="godot", command="x"),))
    istemci._sessions["godot"] = _SahteOturum(ad, metin, hata)
    kayit = ToolRegistry()
    await istemci.register_into(kayit)
    arac = kayit.get(f"godot__{ad}")
    assert arac is not None
    return await arac.run({}, None)


async def test_uzak_arac_hatasi_basari_sayilmaz():
    """MCP'nin `isError` bayrağı `ToolResult`a taşınmalı.

    Ölçülen hata: köprü yalnız metni alıp `isError`'ı ATIYORDU. Uzak araç
    "Scene file does not exist" dediğinde Fusion bunu BAŞARI olarak modele
    veriyordu; model düzeltemiyor, aynı çağrıyı tekrarlıyor, tekrar koruması
    engelliyor ve tur yarım bitiyordu (gerçek koşuda 9 çağrının 3'ü böyleydi).
    """
    sonuc = await _sahte_calistir(
        "save_scene", "Scene file does not exist: res://main.tscn", hata=True
    )

    assert sonuc.ok is False, "uzak araç hatası başarı sayılmamalı"
    assert "does not exist" in sonuc.output


async def test_uzak_arac_basarisi_basari_kalir():
    sonuc = await _sahte_calistir("get_godot_version", "4.7.1", hata=False)

    assert sonuc.ok is True
    assert sonuc.output == "4.7.1"
