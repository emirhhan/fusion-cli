"""Masaüstü yönetim yüzü: eşleştirme akışı, bind reddi, Telegram belirteç saklama."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fusion_cli.remote.controller import TELEGRAM_TOKEN_NAME, RemoteController
from tests.test_remote_service import FakeClock


class MemorySecrets:
    available = True

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> bool:
        return self.values.pop(name, None) is not None


@pytest.fixture
async def controller(tmp_path: Path) -> Any:
    secrets = MemorySecrets()
    instance = RemoteController(
        home=tmp_path,
        root=tmp_path,
        secrets=secrets,
        session_factory=lambda writer: object(),
        clock=FakeClock(),
    )
    instance.secrets = secrets  # type: ignore[attr-defined]
    yield instance
    await instance.aclose()


async def test_eslestirme_masaustu_akisi_ve_cihaz_listesi(controller: Any) -> None:
    started = await controller.dispatch("uzak.eslestir_baslat", {})
    assert started["ok"] and started["yuksekYetki"] == []
    elevated = await controller.dispatch(
        "uzak.eslestir_baslat", {"kapsamlar": ["project.read", "desktop.control"]}
    )
    assert elevated["yuksekYetki"] == ["desktop.control"]
    bad = await controller.dispatch("uzak.eslestir_baslat", {"kapsamlar": ["root.all"]})
    assert bad["ok"] is False
    early = await controller.dispatch("uzak.eslestir_onayla", {"kod": started["kod"]})
    assert early["ok"] is False  # cihaz henüz kod girmedi


async def test_internete_acik_bind_reddedilir(controller: Any) -> None:
    refused = await controller.dispatch("uzak.baslat", {"adres": "0.0.0.0"})
    assert refused["ok"] is False and "reddedildi" in refused["metin"]
    lan = await controller.dispatch("uzak.baslat", {"adres": "192.168.1.5", "yerelAg": True})
    assert lan["ok"] is False


async def test_telegram_belirteci_saklanir_ve_kesilince_silinir(controller: Any) -> None:
    missing = await controller.dispatch("uzak.telegram_baglan", {})
    assert missing["ok"] is False
    controller._secrets.set(TELEGRAM_TOKEN_NAME, "x")
    await controller.dispatch("uzak.telegram_kes", {})
    assert controller._secrets.get(TELEGRAM_TOKEN_NAME) is None


async def test_bilinmeyen_istek_ve_durum(controller: Any) -> None:
    assert (await controller.dispatch("uzak.yok", {}))["ok"] is False
    status = await controller.dispatch("uzak.durum", {})
    assert status["dinliyor"] is False and status["cihazSayisi"] == 0


async def test_masaustu_onayi_bekleyen_soruyu_tamamlar(tmp_path: Path) -> None:
    from tests.test_remote_service import FakeBackend

    controller = RemoteController(
        home=tmp_path,
        root=tmp_path,
        secrets=MemorySecrets(),
        session_factory=lambda writer: object(),
        clock=FakeClock(),
    )
    backend = FakeBackend()
    backend.ask = {"tur": "onay", "arac": "desktop_click", "baslik": "Tıkla", "hedef": "x"}
    controller._backend = backend  # type: ignore[assignment]
    controller._service._backend = backend
    device = controller._registry.add("T", "signed", frozenset({"agent.run", "project.read"}))
    await controller._service.call(device, "tasks.create", {"prompt": "yap"})
    import asyncio

    await asyncio.sleep(0.05)
    pending = await controller.dispatch("uzak.bekleyen", {})
    assert [item["soruId"] for item in pending["sorular"]] == ["q1"]
    done = await controller.dispatch("uzak.onay_cevapla", {"soruId": "q1", "secim": "once"})
    assert done["ok"] is True and backend.answers[0][1] == {"secim": "once"}
    assert (await controller.dispatch("uzak.bekleyen", {}))["sorular"] == []
    backend.release.set()
    await controller.aclose()


async def test_baslatma_port_ve_tls_girdilerini_dogrular(controller: Any, tmp_path: Path) -> None:
    bad_port = await controller.dispatch("uzak.baslat", {"port": 80})
    assert bad_port["ok"] is False and "Port" in bad_port["metin"]
    text_port = await controller.dispatch("uzak.baslat", {"port": "abc"})
    assert text_port["ok"] is False
    half = await controller.dispatch("uzak.baslat", {"sertifika": "/x.pem"})
    assert half["ok"] is False and "birlikte" in half["metin"]
    missing = await controller.dispatch(
        "uzak.baslat",
        {"sertifika": str(tmp_path / "yok.pem"), "anahtar": str(tmp_path / "yok.key")},
    )
    assert missing["ok"] is False and "bulunamadı" in missing["metin"]


async def test_durum_port_ve_yerel_ag_adreslerini_verir(controller: Any) -> None:
    status = await controller.dispatch("uzak.durum", {})
    assert status["port"] == 8791 and isinstance(status["agAdresleri"], list)
    assert all(not address.startswith("127.") for address in status["agAdresleri"])


async def test_tunel_ve_loopback_gercekten_dinler_ve_durdurulur(controller: Any) -> None:
    import httpx

    started = await controller.dispatch("uzak.baslat", {"port": 18791, "guvenilirTunel": True})
    assert started["ok"] is True and started["adres"] == "http://127.0.0.1:18791"
    import asyncio

    for _ in range(50):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://127.0.0.1:18791/")
            break
        except httpx.HTTPError:
            await asyncio.sleep(0.1)
    assert response.status_code == 200 and "Fusion" in response.text
    assert (await controller.dispatch("uzak.durum", {}))["dinliyor"] is True
    await controller.dispatch("uzak.durdur", {})
    assert (await controller.dispatch("uzak.durum", {}))["dinliyor"] is False
