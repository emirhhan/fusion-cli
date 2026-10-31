"""`fusion remote-control` ve REPL `/rc` yüzeyi (P-039): terminal çıktısı, onay sorusu, kapanış."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import remote_control as cli_rc
from fusion_cli.cli.repl import remote_control as repl_rc
from fusion_cli.cli.repl.commands import ASYNC_COMMANDS, build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.memory.factory import null_memory
from fusion_cli.remote.host import (
    CHANNEL_REQUEST_PWA,
    CHANNEL_REQUEST_TELEGRAM,
    PairingCode,
    RemoteControlError,
    RemoteControlSnapshot,
    RemoteControlStart,
)
from fusion_cli.remote.tunnel import tailscale_https_url

from .fakes import make_config


class FakeHost:
    """Gerçek sunucu açmayan sahte: çağrıları kaydeder, hazır fotoğrafları döner."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail
        self.snapshots: list[RemoteControlSnapshot] = [
            RemoteControlSnapshot(True, "http://127.0.0.1:1", 0, "", 0.0)
        ]
        self.started = False
        self.code = "ABCD2345"
        self.telegram_code = ""
        self.needs_desktop_approval = False
        self.telegram_connected = False
        self.renewals: list[PairingCode] = [PairingCode(CHANNEL_REQUEST_PWA, "YENI2345", 20.0)]

    async def start(self, *, port: int, tunnel: bool, telegram: bool) -> RemoteControlStart:
        self.calls.append(f"start:{port}:{tunnel}:{telegram}")
        if self.fail:
            raise RemoteControlError("port kullanımda")
        self.started = True
        return RemoteControlStart(
            "http://127.0.0.1:1", self.code, 10.0, ("agent.run",), False, False
        )

    async def snapshot(self) -> RemoteControlSnapshot:
        return self.snapshots[-1]

    @staticmethod
    def changes(previous: RemoteControlSnapshot, current: RemoteControlSnapshot) -> list[str]:
        return ["fark"] if previous is not current else []

    async def approve_pending(self) -> bool:
        self.calls.append("approve")
        return True

    async def reject_pending(self) -> bool:
        self.calls.append("reject")
        return True

    async def new_code(self, channel: str = CHANNEL_REQUEST_PWA) -> tuple[str, float]:
        self.calls.append(f"code:{channel}")
        return "YENI2345", 20.0

    async def renew_codes(self, *, now: float) -> list[PairingCode]:
        self.calls.append("renew")
        return list(self.renewals) if now > 10.0 or "reject" in self.calls else []

    async def connect_telegram(self) -> bool:
        self.calls.append("telegram")
        self.telegram_connected = True
        self.telegram_code = "TGKD2345"
        return True

    async def stop(self) -> None:
        self.calls.append("stop")
        self.started = False


def _console() -> Console:
    return Console(record=True, width=120, force_terminal=False, color_system=None)


def _options(tmp_path: Path) -> cli_rc.RemoteControlOptions:
    return cli_rc.RemoteControlOptions(root=tmp_path, home=tmp_path, port=1, tunnel=True)


def test_qr_segno_yoksa_none_doner_ve_adres_kodla_yetinilir(monkeypatch: Any) -> None:
    monkeypatch.setitem(sys.modules, "segno", None)  # içe aktarma ImportError üretir
    assert cli_rc.qr_lines("http://127.0.0.1:8791") is None
    console = _console()
    cli_rc.print_start(
        console,
        RemoteControlStart(
            "http://127.0.0.1:8791",
            "ABCD2345",
            1.0,
            ("agent.run",),
            False,
            True,
            telegram_code="TGKD2345",
        ),
        port=8791,
        public_url="https://mac.tail1234.ts.net",
    )
    text = console.export_text()
    assert "ABCD2345" in text and "segno" in text and "Telegram botu bağlı" in text
    assert "/pair TGKD2345" in text and "https://mac.tail1234.ts.net" in text


def test_tunel_adresi_yoksa_qr_basilmaz_ve_telefon_icin_yol_gosterilir() -> None:
    """Ölçüldü (31 Ekim): QR yalnız `http://127.0.0.1:PORT` kodluyordu; telefon kendi
    localhost'una gidiyordu. Loopback için QR basılmaz; tünel adresi varsa kodla birlikte QR."""
    console = _console()
    start = RemoteControlStart(
        "http://127.0.0.1:8791", "ABCD2345", 1.0, ("agent.run",), False, False
    )
    cli_rc.print_start(console, start, port=8791, public_url="")
    text = console.export_text()
    assert "127.0.0.1" in text and "--adres" in text and "█" not in text
    assert (
        cli_rc.pairing_link("https://mac.ts.net/", "ABCD2345") == "https://mac.ts.net/?kod=ABCD2345"
    )
    console = _console()
    cli_rc.print_start(console, start, port=8791, public_url="https://mac.ts.net")
    assert "Telefon adresi: https://mac.ts.net" in console.export_text()


def test_tailscale_adresi_status_json_dan_okunur_yoksa_bos() -> None:
    sample = '{"BackendState":"Running","Self":{"DNSName":"mac.tail1234.ts.net."}}'
    assert tailscale_https_url(runner=lambda _args: sample) == "https://mac.tail1234.ts.net"
    assert tailscale_https_url(runner=lambda _args: '{"Self":{}}') == ""
    assert tailscale_https_url(runner=lambda _args: "bozuk") == ""

    def patlar(_args: list[str]) -> str:
        raise OSError("yok")

    assert tailscale_https_url(runner=patlar) == ""


async def test_komut_baslatir_durdurma_isaretine_kadar_izler_ve_kapatir(tmp_path: Path) -> None:
    host = FakeHost()
    stop = asyncio.Event()
    stop.set()
    console = _console()
    code = await cli_rc.run_remote_control(_options(tmp_path), console, host=host, stop=stop)  # type: ignore[arg-type]
    assert code == 0 and host.calls == ["start:1:True:False", "stop"]
    text = console.export_text()
    assert "Eşleştirme kodu: ABCD2345" in text and "durduruldu" in text


async def test_baslatma_hatasi_turkce_mesaj_ve_cikis_kodu_bir(tmp_path: Path) -> None:
    host = FakeHost(fail=True)
    console = _console()
    code = await cli_rc.run_remote_control(
        _options(tmp_path),
        console,
        host=host,  # type: ignore[arg-type]
        stop=asyncio.Event(),
    )
    assert code == 1 and "port kullanımda" in console.export_text() and host.calls[-1] == "stop"


IDLE = RemoteControlSnapshot(True, "http://127.0.0.1:1", 0, "", 0.0)
WAITING = RemoteControlSnapshot(True, "http://127.0.0.1:1", 0, "", 0.0, awaiting_device="Tablet")


async def evet(_console: Console, name: str) -> bool:
    return name == "Tablet"


async def hayir(_console: Console, _name: str) -> bool:
    return False


async def test_yoklama_turu_bekleyen_cihazi_sorar_onaylar_ve_dolan_kodu_yeniler() -> None:
    """Ölçüldü (31 Ekim): soru `Prompt.ask` ile yoklama döngüsünü bloklıyordu. Soru artık ayrı
    görevde yürür; tur cevabı bir sonraki yoklamada okur, bu arada fark satırları akar."""
    host = FakeHost()
    console = _console()
    acts = lambda: [c for c in host.calls if c != "renew"]  # noqa: E731 - yenileme her turda yoklanır
    host.snapshots = [WAITING]
    watch = cli_rc.Watch(IDLE)
    watch = await cli_rc.tick(host, console, watch, now=0.0, ask=evet)  # type: ignore[arg-type]
    assert watch.prompt is not None and watch.prompt_device == "Tablet" and acts() == []
    await asyncio.sleep(0)  # cevap görevi biter
    watch = await cli_rc.tick(host, console, watch, now=0.0, ask=evet)  # type: ignore[arg-type]
    assert acts() == ["approve"] and watch.prompt is None
    assert "onaylandı" in console.export_text()

    host.calls.clear()
    watch = await cli_rc.tick(host, console, cli_rc.Watch(IDLE), now=0.0, ask=hayir)  # type: ignore[arg-type]
    await asyncio.sleep(0)
    await cli_rc.tick(host, console, watch, now=0.0, ask=hayir)  # type: ignore[arg-type]
    assert acts() == ["reject"] and "YENI2345" in console.export_text()  # ret sonrası yeni kod

    host.calls.clear()
    host.snapshots = [IDLE]
    await cli_rc.tick(host, console, cli_rc.Watch(IDLE), now=11.0, ask=hayir)  # type: ignore[arg-type]
    assert host.calls == ["renew"] and "YENI2345" in console.export_text()  # dolan kod yenilenir


async def test_soru_askidayken_kod_duserse_cevap_yok_sayilir_ve_yeni_kod_basilir() -> None:
    """Süre dolması ile kullanıcı reddi ayrılır: cihaz artık beklemiyorsa cevap uygulanmaz."""
    host = FakeHost()
    console = _console()
    host.snapshots = [WAITING]
    watch = await cli_rc.tick(host, console, cli_rc.Watch(IDLE), now=0.0, ask=evet)  # type: ignore[arg-type]
    host.snapshots = [IDLE]  # kod 2 dakikada düştü: bekleyen cihaz kayboldu
    watch = await cli_rc.tick(host, console, watch, now=200.0, ask=evet)  # type: ignore[arg-type]
    text = console.export_text()
    assert "süresi doldu" in text and "Enter" in text and watch.prompt is not None
    assert set(host.calls) == {"renew"} and "reddedildi" not in text
    await asyncio.sleep(0)
    watch = await cli_rc.tick(host, console, watch, now=200.0, ask=evet)  # type: ignore[arg-type]
    assert watch.prompt is None and "approve" not in host.calls and "reject" not in host.calls


async def test_cevaplanmayan_soru_ctrl_c_ile_kapanisi_bekletmez(tmp_path: Path) -> None:
    """Ölçüldü (31 Ekim): `to_thread(Prompt.ask)` içindeki `input()` SIGINT almıyor, `asyncio.run`
    varsayılan executor'ı beklediği için Enter'a basılmadan süreç çıkmıyordu."""
    host = FakeHost()
    host.snapshots = [WAITING]
    stop = asyncio.Event()

    def asla(_console: Console, _name: str) -> asyncio.Future[bool]:
        loop = asyncio.get_running_loop()
        loop.call_later(0.05, stop.set)  # soru askıdayken Ctrl-C gelir
        return loop.create_future()  # hiç cevap gelmeyen soru

    code = await asyncio.wait_for(
        cli_rc.run_remote_control(
            cli_rc.RemoteControlOptions(root=tmp_path, home=tmp_path, port=1),
            _console(),
            host=host,  # type: ignore[arg-type]
            stop=stop,
            poll_seconds=0.01,
            ask=asla,
        ),
        timeout=5,
    )
    assert code == 0 and host.calls[-1] == "stop"


def test_terminal_sorusu_arka_plan_is_parcaciginda_sorulur_ve_cevabi_ileride_verir() -> None:
    """Gerçek soru: daemon iş parçacığı; döngü kapanırken beklenmez, cevap Future ile gelir."""

    async def scenario() -> bool:
        answers = iter(["e"])
        future = cli_rc._ask_device_approval(
            _console(), "Tablet", prompt=lambda *_a, **_k: next(answers)
        )
        assert not future.done()
        return await asyncio.wait_for(future, timeout=5)

    assert asyncio.run(scenario()) is True


def test_cli_yardim_komutu_tanitir() -> None:
    result = CliRunner().invoke(app_module.app, ["remote-control", "--help"])
    assert result.exit_code == 0
    assert (
        "--telegram" in result.stdout and "--kapsam" in result.stdout and "--adres" in result.stdout
    )


def test_onay_saat_araligi_disinda_komut_sunucu_acmadan_duser() -> None:
    """Ölçüldü (31 Ekim): `--onay-saat -5` sessizce yetkisiz geçiyor, 200 sunucu kalktıktan
    sonra düşüyordu. Typer min/max ile dinlemeden önce reddedilir."""
    for value in ("-5", "200"):
        result = CliRunner().invoke(app_module.app, ["remote-control", "--onay-saat", value])
        assert result.exit_code == 2, result.output
        assert "onay-saat" in result.output


async def test_repl_rc_komutu_kayitli_ve_sunucu_yokken_yol_gosterir(tmp_path: Path) -> None:
    registry = build_registry()
    assert registry.get("rc") is registry.get("remote-control") and "rc" in ASYNC_COMMANDS
    state = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    console = _console()
    await repl_rc.run(state, "durum", console)
    assert "çalışmıyor" in console.export_text()


async def test_repl_rc_alt_komutlari_sahte_sunucuyu_surer_ve_kapanista_durdurur(
    tmp_path: Path,
) -> None:
    state = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    host = FakeHost()
    state.remote_control = host  # type: ignore[assignment]
    console = _console()
    await repl_rc.run(state, "", console)
    assert "zaten çalışıyor" in console.export_text()
    await repl_rc.run(state, "kod", console)
    await repl_rc.run(state, "onayla", console)
    await repl_rc.run(state, "bilinmeyen", console)
    assert host.calls == ["code:pwa", "approve"] and "tanınmadı" in console.export_text()
    # Telegram alt komutu: köprüyü bağlar ve `/pair` kodunu basar; sonra `kod telegram` yeniler.
    await repl_rc.run(state, "telegram", console)
    await repl_rc.run(state, "kod telegram", console)
    assert host.calls[-2:] == ["telegram", f"code:{CHANNEL_REQUEST_TELEGRAM}"]
    assert "/pair TGKD2345" in console.export_text()
    # Durum: onay bekleyen cihaz REPL'de de görünür (Ölçüldü: `/rc durum` bunu göstermiyordu).
    host.snapshots = [WAITING]
    await repl_rc.run(state, "durum", console)
    text = console.export_text()
    assert "Tablet" in text and "/rc onayla" in text
    await repl_rc.shutdown(state)
    assert host.calls[-1] == "stop" and state.remote_control is None
    await repl_rc.shutdown(state)  # ikinci kapanış zararsız
    assert host.calls.count("stop") == 1
