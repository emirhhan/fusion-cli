"""Gateway'in tarayıcı kaynaklı CSRF'e karşı korunması.

Gateway, kullanıcının sağlayıcı ANAHTARLARINI taşıyan yerel bir proxy'dir ve
kimlik doğrulaması yoktur. `127.0.0.1`'e bağlanmak tek başına koruma DEĞİLDİR:
kullanıcı gateway açıkken kötü niyetli bir sayfa ziyaret ederse, o sayfa
`text/plain` gibi "basit" bir içerik tipiyle POST atarak preflight'ı atlar ve
yan etkiyi tetikler — yanıtı okuyamasa bile. Ölçüldü: yabancı `Origin` ile
gönderilen istek 200 dönüyordu.

Kural: `Origin` başlığı VARSA yerel olmalı. Yoksa (curl, betik, IDE eklentisi)
istek serbesttir — tarayıcı dışı istemciler `Origin` göndermez.
"""

from __future__ import annotations

import httpx
import pytest

from fusion_cli.gateway.app import GatewayApp

from .fakes import FakeProvider, make_config


def _store(tmp_path):
    from fusion_cli.config.credentials import FernetSecretStore

    return FernetSecretStore(tmp_path / "s.enc", secret_key="k")


def _app(tmp_path):
    return GatewayApp(
        make_config(),
        provider_factory=lambda spec: FakeProvider("nvidia_nim/m", chunks=("cevap",)),
        secret_store=_store(tmp_path),
    )


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local")


DURUM_DEGISTIREN = (
    "/api/routing",
    "/api/model",
    "/api/fallback",
    "/api/keys",
    "/api/keys/delete",
    "/api/mcp_servers",
    "/api/health/reset",
)


@pytest.mark.parametrize("path", DURUM_DEGISTIREN)
async def test_yabanci_origin_durum_degistiremez(tmp_path, path):
    async with _client(_app(tmp_path)) as client:
        cevap = await client.post(
            path,
            content='{"strategy":"round_robin"}',
            headers={"content-type": "text/plain", "origin": "http://evil.example"},
        )

    assert cevap.status_code == 403, f"{path} yabancı origin'i kabul etti"


async def test_origin_yoksa_istek_gecer(tmp_path):
    """curl, betik ve IDE eklentileri `Origin` göndermez; onları kırmıyoruz."""
    async with _client(_app(tmp_path)) as client:
        cevap = await client.post("/api/routing", json={"strategy": "round_robin"})

    assert cevap.status_code == 200


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8787",
        "http://127.0.0.1:8787",
        "http://localhost:3000",
        "http://[::1]:8787",
    ],
)
async def test_yerel_origin_gecer(tmp_path, origin):
    """Panelin kendi istekleri hangi yerel adla açılmışsa o `Origin`'i taşır."""
    async with _client(_app(tmp_path)) as client:
        cevap = await client.post(
            "/api/routing", json={"strategy": "round_robin"}, headers={"origin": origin}
        )

    assert cevap.status_code == 200


async def test_yabanci_origin_model_cagrisi_yaptiramaz(tmp_path):
    """En pahalı uç: kotayı harcayan tamamlama isteği de korunmalı."""
    async with _client(_app(tmp_path)) as client:
        cevap = await client.post(
            "/v1/chat/completions",
            content='{"model":"auto","messages":[{"role":"user","content":"x"}]}',
            headers={"content-type": "text/plain", "origin": "http://evil.example"},
        )

    assert cevap.status_code == 403


async def test_okuma_uclari_origin_ile_engellenmez(tmp_path):
    """GET okuma uçları yan etki üretmez; gereksiz yere kırılmamalı."""
    async with _client(_app(tmp_path)) as client:
        cevap = await client.get("/health", headers={"origin": "http://evil.example"})

    assert cevap.status_code == 200
