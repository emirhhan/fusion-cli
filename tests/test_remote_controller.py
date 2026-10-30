"""Masaüstü yönetim yüzü: eşleştirme akışı, bind reddi, Telegram belirteç saklama."""

from __future__ import annotations

import json
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


async def test_port_doluysa_baslatma_hata_doner_ve_dongu_dusmez(controller: Any) -> None:
    import socket

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        port = busy.getsockname()[1]
        started = await controller.dispatch("uzak.baslat", {"port": port})
        assert started["ok"] is False and str(port) in started["metin"]
        status = await controller.dispatch("uzak.durum", {})
        assert status["dinliyor"] is False and status["adres"] == ""


async def test_durmayan_sunucu_zorla_kapatilir_ve_gorev_bitirilir(
    controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1-28. Ölçüldü (30 Ekim): 5 sn'de durmayan sunucu görev sürerken durum 'durdu' sayılıyor,
    port hâlâ bağlı kalabiliyordu; artık force_exit istenir ve görev iptal edilir."""
    import asyncio
    from types import SimpleNamespace

    monkeypatch.setattr("fusion_cli.remote.controller.SERVER_STOP_TIMEOUT_SECONDS", 0.05)
    server = SimpleNamespace(should_exit=False, force_exit=False)

    async def stubborn() -> None:
        while True:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                if server.force_exit:
                    raise

    task = asyncio.create_task(stubborn())
    controller._server, controller._server_task = server, task
    await controller.dispatch("uzak.durdur", {})
    assert server.should_exit and server.force_exit
    assert task.done()


async def test_telegram_http_istemcisi_kesilince_kapatilir(controller: Any) -> None:
    import httpx

    from fusion_cli.remote.telegram import HttpTelegramApi

    client = httpx.AsyncClient()
    controller._telegram_api = HttpTelegramApi("123:abc", client)
    await controller._stop_telegram()
    assert client.is_closed and controller._telegram_api is None


async def test_ayar_dosyasi_atomik_yazilir(controller: Any) -> None:
    result = await controller.dispatch("uzak.ayar", {"onayIste": True})
    assert result["ok"] is True
    path = controller._settings_path
    assert json.loads(path.read_text(encoding="utf-8")) == {"requireApproval": True}
    assert [p.name for p in path.parent.iterdir() if p.name.endswith(".tmp")] == []


# R1-25 — Ölçüldü (30 Ekim): `media.get` kökleri arasında `home` vardı ve üretimde
# `home=Path.home()` (kullanıcının TÜM ev dizini): eşleşmiş bir telefon `project.read` ile
# ~/Pictures altındaki her görseli okuyabiliyordu. Kökler artık Fusion'ın ürettiği klasörlerle
# ve bilinen proje köküyle sınırlı.
@pytest.fixture
async def media_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    data = tmp_path / "veri"
    monkeypatch.setattr("fusion_cli.config.paths.user_data_dir", lambda: data)
    home, root = tmp_path / "ev", tmp_path / "proje"
    for folder in (home / "Pictures", root, data / "gallery", data / "memory"):
        folder.mkdir(parents=True)
    instance = RemoteController(
        home=home,
        root=root,
        secrets=MemorySecrets(),
        session_factory=lambda writer: object(),
        clock=FakeClock(),
        data_dir=data / "remote",
    )
    yield instance, tmp_path
    await instance.aclose()


def _png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG....")
    return path


@pytest.mark.parametrize(
    "relative",
    ["proje/ekran.png", "veri/gallery/g.png", "veri/remote/uploads/abc-ek.png"],
)
async def test_telefon_fusionin_urettigi_ve_proje_gorsellerini_gorur(
    media_rig: Any, relative: str
) -> None:
    controller, base = media_rig
    image = _png(base / relative)

    media_type, data = controller._service._mobile._media.read(str(image))

    assert media_type == "image/png" and data.startswith(b"\x89PNG")


@pytest.mark.parametrize("relative", ["ev/Pictures/ozel.png", "veri/memory/x.png", "ev/x.png"])
async def test_telefon_ev_dizinindeki_ozel_gorselleri_goremez(
    media_rig: Any, relative: str
) -> None:
    from fusion_cli.remote.uploads import UploadError

    controller, base = media_rig
    image = _png(base / relative)

    with pytest.raises(UploadError):
        controller._service._mobile._media.read(str(image))


async def test_telefon_eslestirilmis_proje_kokunun_gorselini_gorur(media_rig: Any) -> None:
    controller, base = media_rig
    other = base / "baska-proje"
    _png(other / "sonuc.png")
    controller._projects.replace([{"id": "p_1", "name": "Diğer", "root": str(other)}], {})

    media_type, _ = controller._service._mobile._media.read(str(other / "sonuc.png"))

    assert media_type == "image/png"
