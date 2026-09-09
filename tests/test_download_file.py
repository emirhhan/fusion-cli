"""İkili indirme gerçek baytları korur; başarısız indirme dosya bırakmaz."""

import asyncio
import hashlib

import httpx
import pytest

from fusion_cli.core.errors import PathAccessError
from fusion_cli.core.tools import ToolContext, ToolFamily, tool_family
from fusion_cli.tools import build_registry, download


def _network(monkeypatch, handler):
    client = httpx.AsyncClient
    monkeypatch.setattr(
        download.httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )


async def test_indirilen_ikili_dosya_kayitsiz_metin_donusumune_ugramaz(tmp_path, monkeypatch):
    content = b"\x89PNG\r\n\x1a\n\xff\x00binary"
    _network(monkeypatch, lambda request: httpx.Response(200, content=content))
    context = ToolContext(root=tmp_path)

    result = await download.download_file(
        {"url": "https://8.8.8.8/a.png", "path": "assets/a.png"}, context
    )

    path = tmp_path / "assets/a.png"
    assert result.ok
    assert path.read_bytes() == content
    assert hashlib.sha256(content).hexdigest() in result.output
    assert path in context.touched
    assert path in context.changes.paths
    context.changes.restore()
    assert not path.exists()


async def test_var_olan_asset_uzerine_yazmaz(tmp_path, monkeypatch):
    path = tmp_path / "a.png"
    path.write_bytes(b"onceki")
    _network(monkeypatch, lambda request: pytest.fail("ağa gidilmemeli"))
    result = await download.download_file(
        {"url": "https://8.8.8.8/a.png", "path": "a.png"}, ToolContext(root=tmp_path)
    )
    assert not result.ok
    assert path.read_bytes() == b"onceki"


@pytest.mark.parametrize("redirect", (False, True))
async def test_ozel_ag_hedefini_dogrudan_ve_yonlendirmede_engeller(tmp_path, monkeypatch, redirect):
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    _network(monkeypatch, handler)
    url = "https://8.8.8.8/a" if redirect else "http://127.0.0.1/secret"
    result = await download.download_file({"url": url, "path": "a.png"}, ToolContext(root=tmp_path))
    assert not result.ok
    assert len(requests) == int(redirect)
    assert not (tmp_path / "a.png").exists()


async def test_boyut_siniri_asildiginda_yarim_asset_birakmaz(tmp_path, monkeypatch):
    monkeypatch.setattr(download, "MAX_DOWNLOAD_BYTES", 8)
    _network(monkeypatch, lambda request: httpx.Response(200, content=b"x" * 9))
    context = ToolContext(root=tmp_path)
    result = await download.download_file({"url": "https://8.8.8.8/a", "path": "a.zip"}, context)
    assert not result.ok
    assert not context.changes.paths
    assert not list(tmp_path.iterdir())


async def test_kok_disina_indirme_erisim_politikasini_kullanir(tmp_path):
    with pytest.raises(PathAccessError):
        await download.download_file(
            {"url": "https://8.8.8.8/a", "path": "../a.zip"}, ToolContext(root=tmp_path)
        )


async def test_indirme_araci_yan_etkili_web_ailesindedir():
    tool = build_registry().get("download_file")
    assert tool is not None and tool.mutating
    assert tool_family(tool.name) is ToolFamily.WEB


async def test_iptal_edilen_indirme_sonradan_dosya_olusturmaz(tmp_path, monkeypatch):
    context = ToolContext(root=tmp_path)

    def handler(request):
        context.cancelled.set()
        return httpx.Response(200, content=b"asset")

    _network(monkeypatch, handler)
    result = await download.download_file({"url": "https://8.8.8.8/a", "path": "a.png"}, context)
    assert not result.ok
    assert not (tmp_path / "a.png").exists()
    assert not context.changes.paths


async def test_eszamanli_yazarin_dosyasi_basarisiz_indirme_geri_alinirken_silinmez(
    tmp_path, monkeypatch
):
    context = ToolContext(root=tmp_path)
    path = tmp_path / "a.png"
    _network(monkeypatch, lambda request: httpx.Response(200, content=b"asset"))

    def competing_write(source, target):
        target.write_bytes(b"kullanicinin dosyasi")
        raise FileExistsError()

    monkeypatch.setattr(download.os, "link", competing_write)
    result = await download.download_file({"url": "https://8.8.8.8/a", "path": "a.png"}, context)
    assert not result.ok
    context.changes.restore()
    assert path.read_bytes() == b"kullanicinin dosyasi"


async def test_gercek_arac_iptali_akisi_kapatir_ve_dosya_birakmaz(tmp_path, monkeypatch):
    started = asyncio.Event()
    closed = asyncio.Event()

    class WaitingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"ilk parca"
            started.set()
            await asyncio.Event().wait()

        async def aclose(self):
            closed.set()

    _network(monkeypatch, lambda request: httpx.Response(200, stream=WaitingStream()))
    context = ToolContext(root=tmp_path)
    task = asyncio.create_task(
        build_registry().execute(
            "download_file", {"url": "https://8.8.8.8/a", "path": "a.zip"}, context
        )
    )
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    assert not context.changes.paths
    assert not (tmp_path / "a.zip").exists()
